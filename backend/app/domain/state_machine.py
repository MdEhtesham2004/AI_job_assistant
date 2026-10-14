"""Application lifecycle (Phase 0 §6.3). Every status change goes through `check()`."""

from app.models.enums import ApplicationChannel, ApplicationStatus, StatusChangeSource

S = ApplicationStatus

TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    S.READY_TO_APPLY: frozenset({S.WAITING_FOR_APPROVAL, S.APPLIED, S.WITHDRAWN}),
    S.WAITING_FOR_APPROVAL: frozenset({S.APPROVED, S.REJECTED_BY_USER, S.READY_TO_APPLY}),
    S.APPROVED: frozenset({S.SENDING, S.WAITING_FOR_APPROVAL}),
    S.SENDING: frozenset({S.APPLIED, S.FAILED}),
    S.FAILED: frozenset({S.WAITING_FOR_APPROVAL, S.WITHDRAWN}),
    S.REJECTED_BY_USER: frozenset({S.READY_TO_APPLY}),
    # FAILED: the email bounced (Phase 13) — system only, like every FAILED.
    S.APPLIED: frozenset(
        {S.RESPONDED, S.INTERVIEW, S.REJECTED, S.OFFER, S.NO_RESPONSE, S.WITHDRAWN, S.FAILED}
    ),
    S.RESPONDED: frozenset({S.INTERVIEW, S.REJECTED, S.OFFER, S.WITHDRAWN}),
    S.INTERVIEW: frozenset({S.OFFER, S.REJECTED, S.WITHDRAWN}),
    S.NO_RESPONSE: frozenset({S.RESPONDED, S.INTERVIEW, S.REJECTED, S.OFFER, S.WITHDRAWN}),
    S.OFFER: frozenset(),
    S.REJECTED: frozenset(),
    S.WITHDRAWN: frozenset(),
}

TERMINAL = frozenset(status for status, targets in TRANSITIONS.items() if not targets)

# Only the email pipeline (Phase 12) may enter these: a person never "sends" by hand.
SYSTEM_ONLY = frozenset({S.SENDING, S.FAILED})
# The email approval steps make no sense for portal/referral applications.
EMAIL_ONLY = frozenset({S.WAITING_FOR_APPROVAL, S.APPROVED, S.SENDING, S.FAILED})
# Phase 12: drafting, approving and rejecting an email happen in the Outbox, together
# with the email itself — never as a bare status change.
OUTBOX_STEPS = frozenset({S.WAITING_FOR_APPROVAL, S.APPROVED, S.REJECTED_BY_USER})
IN_OUTBOX = frozenset({S.WAITING_FOR_APPROVAL, S.APPROVED})


class TransitionError(ValueError):
    pass


def check(
    current: ApplicationStatus,
    target: ApplicationStatus,
    *,
    channel: ApplicationChannel,
    source: StatusChangeSource,
    outbox: bool = False,
) -> None:
    """Raise TransitionError unless `current → target` is allowed for this channel/source.

    `outbox=True` marks changes made by the email service (draft, approve, reject).
    """
    if target not in TRANSITIONS[current]:
        raise TransitionError(f"An application cannot go from {current.value} to {target.value}.")
    if source is StatusChangeSource.USER and target in SYSTEM_ONLY:
        raise TransitionError(f"{target.value} is set by the email sender, not by hand.")
    if channel is not ApplicationChannel.EMAIL and target in EMAIL_ONLY:
        raise TransitionError(f"{target.value} only applies to email applications.")
    if (
        source is StatusChangeSource.USER
        and not outbox
        and (target in OUTBOX_STEPS or current in IN_OUTBOX)
    ):
        raise TransitionError("Draft, approve or reject the email in the Outbox.")
    if (
        target is S.APPLIED
        and current is S.READY_TO_APPLY
        and channel is ApplicationChannel.EMAIL
        and source is StatusChangeSource.USER
    ):
        raise TransitionError("Email applications are marked applied when the email is sent.")


def user_options(
    current: ApplicationStatus, channel: ApplicationChannel
) -> list[ApplicationStatus]:
    """Statuses a person may choose next (what the UI offers)."""
    options: list[ApplicationStatus] = []
    for target in TRANSITIONS[current]:
        try:
            check(current, target, channel=channel, source=StatusChangeSource.USER)
        except TransitionError:
            continue
        options.append(target)
    order = list(ApplicationStatus)
    return sorted(options, key=order.index)
