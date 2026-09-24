from datetime import UTC, datetime

from opportunity_api.collection.scheduling import next_scheduled_at


def test_schedule_respects_source_timezone() -> None:
    result = next_scheduled_at(
        "0 9 * * *",
        "Asia/Kolkata",
        datetime(2026, 8, 14, 0, 0, tzinfo=UTC),
    )
    assert result == datetime(2026, 8, 14, 3, 30, tzinfo=UTC)
