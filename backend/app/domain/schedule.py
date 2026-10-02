"""Cron schedules for saved searches, evaluated in the user's time zone."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterError, croniter

CHECK_RUNS = 48  # how many upcoming runs are checked for the minimum interval


class ScheduleError(ValueError):
    pass


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def validate_cron(expression: str, min_interval_minutes: int) -> str:
    """Normalized expression; raises ScheduleError for invalid or too-frequent schedules."""
    expression = " ".join(expression.split())
    if len(expression.split(" ")) != 5:
        raise ScheduleError("Use a 5-part cron schedule, e.g. '0 8 * * *' (every day at 08:00).")
    try:
        iterator = croniter(expression, datetime(2026, 1, 5, tzinfo=UTC))
        runs = [iterator.get_next(datetime) for _ in range(CHECK_RUNS)]
    except (CroniterError, ValueError, KeyError) as exc:
        raise ScheduleError(f"Invalid schedule: {expression!r}.") from exc
    gaps = [later - earlier for earlier, later in zip(runs, runs[1:], strict=False)]
    if min(gaps) < timedelta(minutes=min_interval_minutes):
        raise ScheduleError(
            f"Saved searches can run at most once every {min_interval_minutes} minutes."
        )
    return expression


def next_run(expression: str, after: datetime, timezone: str | None) -> datetime:
    """Next run strictly after `after`, as an aware UTC datetime."""
    local_after = after.astimezone(_zone(timezone))
    upcoming: datetime = croniter(expression, local_after).get_next(datetime)
    return upcoming.astimezone(UTC)


def is_due(expression: str, last_run: datetime, now: datetime, timezone: str | None) -> bool:
    return next_run(expression, last_run, timezone) <= now
