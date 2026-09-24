from opportunity_api.processing.normalization import (
    detect_language,
    evidence_spans,
    exact_content_hash,
    hamming_distance,
    normalize_text,
    simhash64,
)


def test_normalization_is_stable() -> None:
    raw = "<p>  We’re\u200b spending &amp; hours. </p>"
    assert normalize_text(raw) == "We're spending & hours."
    assert exact_content_hash(" TITLE ", raw) == exact_content_hash(
        "title", "We're spending & hours."
    )


def test_simhash_and_language_detection() -> None:
    fingerprint = simhash64("The team manually copies invoices into the accounting system")
    assert len(fingerprint) == 16
    assert hamming_distance(fingerprint, fingerprint) == 0
    assert detect_language("The team is spending hours on the process") == "en"
    assert detect_language("टीम हर दिन यह काम करती है") == "hi"


def test_evidence_claims_are_verified_against_source() -> None:
    text = "The finance team spends four hours reconciling invoices every Friday."
    spans = evidence_spans(
        text,
        [
            {"field": "time_spent", "quote": "four hours"},
            {"field": "current_spend", "quote": "$10,000"},
        ],
    )
    assert spans[0] == {
        "field": "time_spent",
        "quote": "four hours",
        "start": 24,
        "end": 34,
        "verified": True,
    }
    assert spans[1]["verified"] is False
    assert spans[1]["start"] == -1
