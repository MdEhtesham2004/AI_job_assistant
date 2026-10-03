import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contacts import Blocklist, domain_of
from app.models.applications import Application
from app.models.enums import (
    ContactApproval,
    ContactSource,
    EmailDirection,
    EmailStatus,
    EmailType,
)
from app.models.jobs import Job
from app.models.outreach import Contact, DoNotContact, Email, EmailAttachment, OAuthAccount
from app.repositories.base import OwnedRepository
from app.repositories.jobs import _escape_like

GOOGLE = "google"


class OAuthAccountRepository(OwnedRepository[OAuthAccount]):
    model = OAuthAccount

    async def google(self, *, for_update: bool = False) -> OAuthAccount | None:
        query = self.scoped().where(OAuthAccount.provider == GOOGLE)
        if for_update:
            query = query.with_for_update()
        result: OAuthAccount | None = await self.session.scalar(query)
        return result


@dataclass(frozen=True)
class ContactFilters:
    approval: ContactApproval | None = None
    source: ContactSource | None = None
    job_id: uuid.UUID | None = None
    q: str | None = None


class ContactRepository(OwnedRepository[Contact]):
    model = Contact

    async def by_email(self, email: str) -> Contact | None:
        result: Contact | None = await self.session.scalar(
            self.scoped().where(Contact.email == email)
        )
        return result

    async def insert_new(self, values: dict[str, object]) -> Contact | None:
        """Insert unless the user already has this address (the first evidence is kept)."""
        contact_id = await self.session.scalar(
            insert(Contact)
            .values(user_id=self.owner_id, **values)
            .on_conflict_do_nothing(index_elements=["user_id", "email"])
            .returning(Contact.id)
        )
        return await self.session.get(Contact, contact_id) if contact_id else None

    async def page(
        self, filters: ContactFilters, *, limit: int, offset: int
    ) -> tuple[Sequence[tuple[Contact, Job | None]], int]:
        query = select(Contact, Job).outerjoin(Job, Job.id == Contact.job_id).where(self._owned())
        if filters.approval:
            query = query.where(Contact.approval == filters.approval)
        if filters.source:
            query = query.where(Contact.source == filters.source)
        if filters.job_id:
            query = query.where(Contact.job_id == filters.job_id)
        if filters.q:
            pattern = f"%{_escape_like(filters.q.strip())}%"
            query = query.where(
                or_(
                    Contact.email.ilike(pattern, escape="\\"),
                    Contact.name.ilike(pattern, escape="\\"),
                    Contact.company.ilike(pattern, escape="\\"),
                    Job.title.ilike(pattern, escape="\\"),
                )
            )
        total = await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = await self.session.execute(
            query.order_by(Contact.created_at.desc(), Contact.id).limit(limit).offset(offset)
        )
        return [(contact, job) for contact, job in rows.all()], total

    async def approval_counts(self) -> dict[str, int]:
        rows = await self.session.execute(
            select(Contact.approval, func.count()).where(self._owned()).group_by(Contact.approval)
        )
        counts = {value.value: 0 for value in ContactApproval}
        for approval, count in rows.all():
            counts[ContactApproval(approval).value] = count
        return counts


class DoNotContactRepository(OwnedRepository[DoNotContact]):
    model = DoNotContact

    async def blocklist(self) -> Blocklist:
        rows = (await self.session.scalars(self.scoped())).all()
        return Blocklist(
            emails=frozenset(r.email.lower() for r in rows if r.email),
            domains=frozenset(r.domain.lower() for r in rows if r.domain),
        )

    async def all(self) -> Sequence[DoNotContact]:
        rows = await self.session.scalars(self.scoped().order_by(DoNotContact.created_at.desc()))
        return rows.all()

    async def find(self, *, email: str | None, domain: str | None) -> DoNotContact | None:
        query = self.scoped()
        query = (
            query.where(DoNotContact.email == email)
            if email
            else query.where(DoNotContact.domain == domain)
        )
        result: DoNotContact | None = await self.session.scalar(query)
        return result

    async def blocks(self, email: str) -> bool:
        found = await self.session.scalar(
            select(func.count())
            .select_from(DoNotContact)
            .where(
                self._owned(),
                or_(DoNotContact.email == email, DoNotContact.domain == domain_of(email)),
            )
        )
        return bool(found)


@dataclass(frozen=True)
class OutboxFilters:
    statuses: tuple[EmailStatus, ...] = ()


class EmailRepository(OwnedRepository[Email]):
    model = Email

    async def outbound_for(
        self, application_id: uuid.UUID, email_type: EmailType = EmailType.APPLICATION
    ) -> Email | None:
        result: Email | None = await self.session.scalar(
            self.scoped().where(
                Email.application_id == application_id,
                Email.direction == EmailDirection.OUTBOUND,
                Email.email_type == email_type,
            )
        )
        return result

    async def get_for_update(self, email_id: uuid.UUID) -> Email | None:
        result: Email | None = await self.session.scalar(
            self.scoped().where(Email.id == email_id).with_for_update()
        )
        return result

    async def claim_for_sending(self, email_id: uuid.UUID, now: datetime) -> bool:
        """queued → sending, atomically. Only one worker can win (no double send)."""
        result = await self.session.execute(
            update(Email)
            .where(
                self._owned(),
                Email.id == email_id,
                Email.status == EmailStatus.QUEUED,
                Email.scheduled_for <= now,
            )
            .values(status=EmailStatus.SENDING, updated_at=now)
            .returning(Email.id)
        )
        return result.scalar_one_or_none() is not None

    async def outbox(
        self, filters: OutboxFilters, *, limit: int, offset: int
    ) -> tuple[Sequence[tuple[Email, Application, Job]], int]:
        query = (
            select(Email, Application, Job)
            .join(Application, Application.id == Email.application_id)
            .join(Job, Job.id == Application.job_id)
            .where(self._owned(), Email.direction == EmailDirection.OUTBOUND)
        )
        if filters.statuses:
            query = query.where(Email.status.in_(filters.statuses))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        order = func.coalesce(Email.sent_at, Email.scheduled_for, Email.updated_at)
        rows = await self.session.execute(
            query.order_by(order.desc(), Email.id).limit(limit).offset(offset)
        )
        return [(e, a, j) for e, a, j in rows.all()], total

    async def status_counts(self) -> dict[str, int]:
        rows = await self.session.execute(
            select(Email.status, func.count())
            .where(self._owned(), Email.direction == EmailDirection.OUTBOUND)
            .group_by(Email.status)
        )
        counts = {status.value: 0 for status in EmailStatus}
        for status, count in rows.all():
            counts[EmailStatus(status).value] = count
        return counts

    async def taken_slots(self, since: datetime) -> list[datetime]:
        """Send times used or reserved since `since` (for the cap and the gap)."""
        sent = await self.session.scalars(
            select(Email.sent_at).where(
                self._owned(),
                Email.direction == EmailDirection.OUTBOUND,
                Email.status.in_((EmailStatus.SENT, EmailStatus.BOUNCED)),
                Email.sent_at >= since,
            )
        )
        reserved = await self.session.scalars(
            select(Email.scheduled_for).where(
                self._owned(),
                Email.direction == EmailDirection.OUTBOUND,
                Email.status.in_((EmailStatus.QUEUED, EmailStatus.SENDING)),
                Email.scheduled_for.is_not(None),
            )
        )
        return [t for t in [*sent.all(), *reserved.all()] if t is not None]

    async def sent_today_count(self, since: datetime) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(Email)
                .where(
                    self._owned(),
                    Email.direction == EmailDirection.OUTBOUND,
                    Email.status.in_((EmailStatus.SENT, EmailStatus.BOUNCED)),
                    Email.sent_at >= since,
                )
            )
            or 0
        )

    async def last_sent_to(self, address: str, *, exclude: uuid.UUID) -> datetime | None:
        return await self.session.scalar(
            select(func.max(Email.sent_at)).where(
                self._owned(),
                Email.direction == EmailDirection.OUTBOUND,
                Email.status.in_((EmailStatus.SENT, EmailStatus.BOUNCED)),
                Email.to_address == address,
                Email.id != exclude,
            )
        )


class EmailAttachmentRepository(OwnedRepository[EmailAttachment]):
    model = EmailAttachment

    async def for_email(self, email_id: uuid.UUID) -> Sequence[EmailAttachment]:
        rows = await self.session.scalars(
            self.scoped()
            .where(EmailAttachment.email_id == email_id)
            .order_by(EmailAttachment.created_at, EmailAttachment.id)
        )
        return rows.all()

    async def for_emails(
        self, email_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[EmailAttachment]]:
        if not email_ids:
            return {}
        rows = await self.session.scalars(
            self.scoped().where(EmailAttachment.email_id.in_(email_ids))
        )
        grouped: dict[uuid.UUID, list[EmailAttachment]] = {}
        for row in rows.all():
            grouped.setdefault(row.email_id, []).append(row)
        return grouped


# Due-email lookups run across all users (Beat sweep), so they are plain functions.


async def due_emails(session: AsyncSession, now: datetime, limit: int = 100) -> Sequence[Email]:
    rows = await session.scalars(
        select(Email)
        .where(
            Email.direction == EmailDirection.OUTBOUND,
            Email.status == EmailStatus.QUEUED,
            Email.scheduled_for <= now,
        )
        .order_by(Email.scheduled_for)
        .limit(limit)
    )
    result: Sequence[Email] = rows.all()
    return result


async def stuck_sending(
    session: AsyncSession, older_than: datetime, limit: int = 50
) -> Sequence[Email]:
    rows = await session.scalars(
        select(Email)
        .where(
            Email.direction == EmailDirection.OUTBOUND,
            Email.status == EmailStatus.SENDING,
            Email.updated_at < older_than,
        )
        .limit(limit)
    )
    result: Sequence[Email] = rows.all()
    return result
