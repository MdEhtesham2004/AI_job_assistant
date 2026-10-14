import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ExternalServiceError, LimitExceededError
from app.integrations.ai import AiClient, AiResult, Message
from app.models.system import AiCall
from app.repositories.ai_calls import AiCallRepository
from app.repositories.profiles import UserSettingsRepository

# Output ceilings per task (Phase 14). Generous: gpt-oss counts its (low) reasoning tokens
# here too, and a cut-off answer is invalid JSON (= retry = more cost). Unlisted tasks use
# AI_MAX_OUTPUT_TOKENS. Typical real outputs today are 100-650 tokens.
TASK_MAX_TOKENS: dict[str, int] = {
    "linkedin_post": 1500,
    "reply_classify": 1500,
    "follow_up": 2000,
    "job_analyze": 3000,
    "application_email": 3000,
    "cover_letter": 4000,
    "resume_ats": 4000,
    "resume_linkedin": 4000,
}


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class AiService:
    """Every LLM call goes through here: budget check before, usage record after."""

    def __init__(self, session: AsyncSession, client: AiClient) -> None:
        self.session = session
        self.client = client
        self.calls = AiCallRepository(session)

    async def month_spend(self, user_id: uuid.UUID) -> Decimal:
        return await self.calls.cost_since(user_id, month_start())

    async def _check_budget(self, user_id: uuid.UUID) -> None:
        settings = await UserSettingsRepository(self.session, owner_id=user_id).get_or_create()
        spent = await self.month_spend(user_id)
        if spent >= settings.monthly_ai_budget_usd:
            raise LimitExceededError(
                f"Monthly AI budget of ${settings.monthly_ai_budget_usd} reached.",
                code="AI_BUDGET_EXCEEDED",
                details={"spent": str(spent), "budget": str(settings.monthly_ai_budget_usd)},
            )

    async def complete_json[OutputT: BaseModel](
        self,
        *,
        user_id: uuid.UUID | None,
        task_type: str,
        prompt_version: str,
        messages: list[Message],
        output: type[OutputT],
        model: str | None = None,
    ) -> AiResult[OutputT]:
        if user_id is not None:
            await self._check_budget(user_id)
        # End the transaction: no database connection is held open while the AI answers.
        await self.session.commit()
        try:
            result = await self.client.complete_json(
                messages=messages,
                output=output,
                model=model,
                max_tokens=TASK_MAX_TOKENS.get(task_type),
            )
        except ExternalServiceError:
            self.session.add(
                AiCall(
                    user_id=user_id,
                    task_type=task_type,
                    model=model or self.client.settings.ai_model_default,
                    prompt_version=prompt_version,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=Decimal(0),
                    latency_ms=0,
                    cached=False,
                    success=False,
                )
            )
            await self.session.commit()
            raise
        self.session.add(
            AiCall(
                user_id=user_id,
                task_type=task_type,
                model=result.model,
                prompt_version=prompt_version,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                cached=result.cached,
                success=True,
            )
        )
        await self.session.commit()
        return result
