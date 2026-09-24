from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter


def next_scheduled_at(expression: str, timezone: str, after: datetime) -> datetime:
    if after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    local_after = after.astimezone(ZoneInfo(timezone))
    next_local = croniter(expression, local_after).get_next(datetime)
    return next_local.astimezone(UTC)
