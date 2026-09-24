from opportunity_api.intelligence.service import (
    _updated_centroid,
    corroboration_score,
    pending_signals_query,
)


def test_centroid_is_incremental_and_dimension_preserving() -> None:
    centroid, count = _updated_centroid(None, 0, [1.0, 0.0, 0.5])
    assert centroid == [1.0, 0.0, 0.5]
    assert count == 1
    centroid, count = _updated_centroid(centroid, count, [0.0, 1.0, 0.5])
    assert centroid == [0.5, 0.5, 0.5]
    assert count == 2


def test_centroid_ignores_missing_embeddings() -> None:
    centroid, count = _updated_centroid([0.5, 0.5], 3, None)
    assert centroid == [0.5, 0.5]
    assert count == 3


def test_corroboration_requires_source_and_evidence_diversity() -> None:
    weak = corroboration_score(1, 1, 5, 0.8)
    strong = corroboration_score(3, 3, 5, 0.8)
    assert round(weak, 3) == 0.513
    assert strong == 0.98
    assert strong > weak


def test_failed_intelligence_retries_are_bounded() -> None:
    statement = str(pending_signals_query(10, include_failed=True, retry_limit=3))
    assert "signals.intelligence_attempts <" in statement
