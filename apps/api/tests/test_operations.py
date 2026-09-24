from opportunity_api.models import CustomerInterview, OpportunityStatus, PortfolioState
from opportunity_api.operations.service import interview_patterns, portfolio_state


def test_portfolio_state_detects_saturation_before_simple_decline() -> None:
    state, reasons = portfolio_state(
        OpportunityStatus.thesis_ready,
        score_velocity=-4,
        competition_velocity=2,
        pain_velocity=0,
        invalidated=False,
        threshold=8,
    )
    assert state == PortfolioState.saturating
    assert "Competition" in reasons[0]


def test_portfolio_state_respects_invalidated_lifecycle() -> None:
    state, _ = portfolio_state(
        OpportunityStatus.killed,
        score_velocity=20,
        competition_velocity=0,
        pain_velocity=4,
        invalidated=False,
        threshold=8,
    )
    assert state == PortfolioState.invalidated


def test_interview_patterns_preserve_behavioral_counts() -> None:
    interviews = [
        CustomerInterview(
            buyer_or_user="buyer",
            budget_signal="approved budget",
            current_spend_usd=900,
            evidence_strength=0.8,
            tools_used=["Excel", "ERP"],
            complaints=["manual export"],
        ),
        CustomerInterview(
            buyer_or_user="user",
            budget_signal="",
            current_spend_usd=None,
            evidence_strength=0.6,
            tools_used=["Excel"],
            complaints=["manual export", "slow integration"],
        ),
    ]
    patterns = interview_patterns(interviews)
    assert patterns["interview_count"] == 2
    assert patterns["buyer_count"] == 1
    assert patterns["specific_spend_count"] == 1
    assert patterns["top_tools"][0] == ("excel", 2)
    assert patterns["top_complaints"][0] == ("manual export", 2)
