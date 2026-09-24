from datetime import UTC, datetime, timedelta

import pytest

from opportunity_api.config import Settings
from opportunity_api.decisions.scoring import WEIGHTS
from opportunity_api.learning.service import (
    freshness_values,
    pearson,
    proposed_weights,
)
from opportunity_api.models import OpportunityStatus, ScoreDimension


def test_pearson_detects_direction_and_constant_series() -> None:
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [6, 4, 2]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) == 0.0


def test_calibration_weights_remain_normalized_and_bounded() -> None:
    correlations = {
        dimension: (1.0 if dimension == ScoreDimension.willingness_to_pay else -0.2)
        for dimension in ScoreDimension
    }
    proposed, recommendations = proposed_weights(correlations, 0.02)
    assert sum(proposed.values()) == pytest.approx(1.0)
    assert len(recommendations) == len(ScoreDimension)
    for dimension in ScoreDimension:
        assert abs(proposed[dimension.value] - WEIGHTS[dimension]) <= 0.020001
    assert (
        proposed[ScoreDimension.willingness_to_pay.value]
        > WEIGHTS[ScoreDimension.willingness_to_pay]
    )


def test_stale_high_score_opportunity_gets_high_refresh_priority() -> None:
    now = datetime.now(UTC)
    freshness, next_check, priority = freshness_values(
        now - timedelta(days=30),
        90,
        OpportunityStatus.thesis_ready,
        Settings(),
        now,
    )
    assert freshness == 0.0
    assert next_check < now
    assert priority == pytest.approx(0.9)


def test_pilot_uses_short_freshness_window() -> None:
    now = datetime.now(UTC)
    freshness, next_check, _ = freshness_values(
        now,
        75,
        OpportunityStatus.pilot,
        Settings(),
        now,
    )
    assert freshness == 1.0
    assert next_check == now + timedelta(days=14)
