"""Task runner: status, progress, retries, results, notifications, AI usage records."""

import uuid
from decimal import Decimal
from pathlib import Path

import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.db.session import create_session_factory
from app.models.accounts import User, UserSettings
from app.models.enums import TaskStatus
from app.models.system import AiCall, Notification, Task
from app.workers.runner import Outcome, run_task
from tests.fakes import FAKE_PDF, FakeGotenberg, chat_response, fake_services


async def _user_with_task(session: AsyncSession, task_type: str) -> tuple[User, Task]:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com", full_name="Worker Test", hashed_password="x"
    )
    session.add(user)
    await session.flush()
    task = Task(user_id=user.id, type=task_type)
    session.add(task)
    await session.commit()
    return user, task


async def _run(task: Task, settings: Settings, engine: AsyncEngine, services) -> Outcome:  # type: ignore[no-untyped-def]
    result = await run_task(
        task.id, settings, services=services, session_factory=create_session_factory(engine)
    )
    return result.outcome


async def test_test_pdf_succeeds_and_stores_the_file(
    session: AsyncSession, engine: AsyncEngine, settings: Settings, tmp_path: Path
) -> None:
    user, task = await _user_with_task(session, "test_pdf")
    services = fake_services(settings, tmp_path)

    outcome = await _run(task, settings, engine, services)

    assert outcome is Outcome.SUCCEEDED
    await session.refresh(task)
    assert task.status is TaskStatus.SUCCEEDED
    assert task.progress == 100
    assert task.attempts == 1
    assert task.finished_at is not None
    file_info = task.result["file"]
    assert file_info["name"] == "test.pdf"
    assert file_info["key"].startswith(f"users/{user.id}/tasks/")
    assert await services.storage.read(file_info["key"]) == FAKE_PDF
    assert "Worker Test" in services.gotenberg.rendered[0]

    notification = await session.scalar(select(Notification).where(Notification.user_id == user.id))
    assert notification is not None
    assert notification.title == "Test PDF finished"
    assert notification.link == "/tasks"


async def test_failing_task_retries_then_fails(
    session: AsyncSession, engine: AsyncEngine, settings: Settings, tmp_path: Path
) -> None:
    user, task = await _user_with_task(session, "test_failure")
    services = fake_services(settings, tmp_path)

    outcomes = [await _run(task, settings, engine, services) for _ in range(4)]

    assert outcomes == [Outcome.RETRY, Outcome.RETRY, Outcome.RETRY, Outcome.FAILED]
    await session.refresh(task)
    assert task.status is TaskStatus.FAILED
    assert task.attempts == 4  # 1 try + 3 retries
    assert "always fails" in task.error
    notification = await session.scalar(select(Notification).where(Notification.user_id == user.id))
    assert notification.severity.value == "error"


async def test_external_outage_is_retried(
    session: AsyncSession, engine: AsyncEngine, settings: Settings, tmp_path: Path
) -> None:
    _, task = await _user_with_task(session, "test_pdf")
    services = fake_services(settings, tmp_path, gotenberg=FakeGotenberg(fail=True))

    result = await run_task(
        task.id, settings, services=services, session_factory=create_session_factory(engine)
    )

    assert result.outcome is Outcome.RETRY
    assert result.retry_in == 10
    await session.refresh(task)
    assert task.status is TaskStatus.QUEUED
    assert "Retrying in 10s" in task.error


async def test_finished_tasks_are_not_run_twice(
    session: AsyncSession, engine: AsyncEngine, settings: Settings, tmp_path: Path
) -> None:
    _, task = await _user_with_task(session, "test_pdf")
    services = fake_services(settings, tmp_path)

    await _run(task, settings, engine, services)
    second = await _run(task, settings, engine, services)

    assert second is Outcome.SKIPPED
    assert len(services.gotenberg.rendered) == 1


async def test_unknown_task_type_fails_without_retry(
    session: AsyncSession, engine: AsyncEngine, settings: Settings, tmp_path: Path
) -> None:
    _, task = await _user_with_task(session, "no_such_type")

    outcome = await _run(task, settings, engine, fake_services(settings, tmp_path))

    assert outcome is Outcome.FAILED


@respx.mock
async def test_ai_test_records_usage_and_cost(
    session: AsyncSession, engine: AsyncEngine, settings: Settings, tmp_path: Path
) -> None:
    respx.post("https://ai.test/v1/chat/completions").mock(
        return_value=chat_response({"ok": True, "message": "Working."}, cost=0.0002)
    )
    user, task = await _user_with_task(session, "ai_test")

    outcome = await _run(task, settings, engine, fake_services(settings, tmp_path))

    assert outcome is Outcome.SUCCEEDED
    await session.refresh(task)
    assert task.result["answer"] == {"ok": True, "message": "Working."}
    call = await session.scalar(select(AiCall).where(AiCall.user_id == user.id))
    assert call.task_type == "ai_test"
    assert call.cost_usd == Decimal("0.000200")
    assert call.success is True


async def test_ai_budget_stops_calls(
    session: AsyncSession, engine: AsyncEngine, settings: Settings, tmp_path: Path
) -> None:
    user, task = await _user_with_task(session, "ai_test")
    session.add(UserSettings(user_id=user.id, monthly_ai_budget_usd=Decimal("0.01")))
    session.add(
        AiCall(
            user_id=user.id,
            task_type="x",
            model="m",
            prompt_version="v",
            input_tokens=1,
            output_tokens=1,
            cost_usd=Decimal("0.02"),
            latency_ms=1,
            cached=False,
            success=True,
        )
    )
    await session.commit()

    outcome = await _run(task, settings, engine, fake_services(settings, tmp_path))

    assert outcome is Outcome.FAILED
    await session.refresh(task)
    assert "budget" in task.error
