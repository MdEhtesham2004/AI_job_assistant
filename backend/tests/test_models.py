import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounts import User
from app.models.enums import ApprovalStatus, TaskStatus, UserRole
from app.models.system import AuditLog, Task


def _user(email: str = "person@example.com") -> User:
    return User(email=email, full_name="Test Person", hashed_password="x")


async def test_new_user_defaults_to_pending_user_role(session: AsyncSession) -> None:
    user = _user()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    assert user.id is not None
    assert user.role is UserRole.USER
    assert user.approval_status is ApprovalStatus.PENDING
    assert user.is_active is True
    assert user.is_superuser is False
    assert user.created_at is not None and user.updated_at is not None


async def test_email_is_unique_case_insensitively(session: AsyncSession) -> None:
    session.add(_user("Person@Example.com"))
    await session.commit()

    session.add(_user("person@example.com"))
    with pytest.raises(IntegrityError, match="uq_users_email"):
        await session.commit()


async def test_email_lookup_is_case_insensitive(session: AsyncSession) -> None:
    session.add(_user("Mixed.Case@Example.com"))
    await session.commit()

    found = await session.scalar(select(User).where(User.email == "mixed.case@example.com"))
    assert found is not None


async def test_database_rejects_unknown_enum_values(session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_users_user_role"):
        await session.execute(
            text(
                "INSERT INTO users (email, full_name, hashed_password, role) "
                "VALUES ('x@example.com', 'X', 'x', 'boss')"
            )
        )


async def test_task_progress_must_be_between_0_and_100(session: AsyncSession) -> None:
    session.add(Task(type="test", progress=101))
    with pytest.raises(IntegrityError, match="ck_tasks_progress_range"):
        await session.commit()


async def test_task_defaults(session: AsyncSession) -> None:
    task = Task(type="parse_resume")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    assert task.status is TaskStatus.QUEUED
    assert task.progress == 0
    assert task.payload == {}


async def test_deleting_a_user_keeps_audit_logs_anonymised(session: AsyncSession) -> None:
    user = _user()
    session.add(user)
    await session.flush()
    log = AuditLog(user_id=user.id, actor_type="user", action="test.action")
    task = Task(user_id=user.id, type="test")
    session.add_all([log, task])
    await session.commit()

    await session.delete(user)
    await session.commit()
    session.expunge_all()

    remaining_log = await session.get(AuditLog, log.id)
    assert remaining_log is not None and remaining_log.user_id is None
    assert await session.get(Task, task.id) is None  # tasks cascade with the user
