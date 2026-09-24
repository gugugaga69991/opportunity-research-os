from datetime import UTC, datetime

import pytest

from opportunity_api.jobs import build_idempotency_key, get_handler


def test_idempotency_key_is_stable_inside_minute() -> None:
    now = datetime(2026, 9, 24, 10, 15, 20, tzinfo=UTC)
    first = build_idempotency_key("process_signal_document", ["abc"], now=now)
    second = build_idempotency_key(
        "process_signal_document",
        ["abc"],
        now=now.replace(second=59),
    )
    assert first == second


def test_idempotency_key_changes_for_different_work() -> None:
    now = datetime(2026, 9, 24, 10, 15, tzinfo=UTC)
    first = build_idempotency_key("process_signal_document", ["abc"], now=now)
    second = build_idempotency_key("process_signal_document", ["xyz"], now=now)
    assert first != second


def test_unknown_handler_is_rejected() -> None:
    with pytest.raises(LookupError, match="Unknown job handler"):
        get_handler("not_a_real_job")
