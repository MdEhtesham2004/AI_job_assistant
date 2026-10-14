import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import cli
from app.core.config import Settings
from app.core.errors import ValidationAppError
from app.core.security import verify_password
from app.models.accounts import User
from app.models.enums import ApprovalStatus, UserRole
from app.models.system import AuditLog
from app.services.admin_seed import AdminSeedService

PASSWORD = "a-strong-password-123"


async def test_creates_an_approved_admin(session: AsyncSession) -> None:
    result = await AdminSeedService(session).ensure_admin(
        email="admin@example.com", full_name="Admin", password=PASSWORD
    )

    user = result.user
    assert result.created is True
    assert user.role is UserRole.ADMIN
    assert user.approval_status is ApprovalStatus.APPROVED
    assert user.is_superuser is True and user.is_active is True
    assert user.approved_at is not None
    assert user.hashed_password != PASSWORD
    assert verify_password(PASSWORD, user.hashed_password)


async def test_running_twice_promotes_without_changing_the_password(
    session: AsyncSession,
) -> None:
    service = AdminSeedService(session)
    first = await service.ensure_admin(email="admin@example.com", full_name="A", password=PASSWORD)
    second = await service.ensure_admin(
        email="ADMIN@example.com", full_name="B", password="another-password-456"
    )

    assert second.created is False
    assert second.user.id == first.user.id
    assert verify_password(PASSWORD, second.user.hashed_password)
    assert await session.scalar(select(func.count()).select_from(User)) == 1


async def test_promotes_an_existing_pending_user(session: AsyncSession) -> None:
    session.add(User(email="someone@example.com", full_name="Someone", hashed_password="x"))
    await session.commit()

    result = await AdminSeedService(session).ensure_admin(
        email="someone@example.com", full_name="Someone", password=PASSWORD
    )

    assert result.created is False
    assert result.user.role is UserRole.ADMIN
    assert result.user.approval_status is ApprovalStatus.APPROVED


async def test_writes_an_audit_log_entry(session: AsyncSession) -> None:
    result = await AdminSeedService(session).ensure_admin(
        email="admin@example.com", full_name="Admin", password=PASSWORD
    )

    log = await session.scalar(select(AuditLog).where(AuditLog.entity_id == result.user.id))
    assert log is not None
    assert log.action == "user.seed_admin"
    assert log.data == {"created": True}


@pytest.mark.parametrize(
    ("email", "password"),
    [("not-an-email", PASSWORD), ("admin@example.com", "short")],
)
async def test_rejects_invalid_input(session: AsyncSession, email: str, password: str) -> None:
    with pytest.raises(ValidationAppError):
        await AdminSeedService(session).ensure_admin(
            email=email, full_name="Admin", password=password
        )


def test_cli_create_admin_uses_env_password(
    settings: Settings,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: settings)  # never touch the dev database
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)

    exit_code = cli.main(["create-admin", "--email", "cli@example.com", "--full-name", "CLI"])

    assert exit_code == 0
    assert "Created admin: cli@example.com" in capsys.readouterr().out
