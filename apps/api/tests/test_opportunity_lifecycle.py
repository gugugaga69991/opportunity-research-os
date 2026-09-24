from opportunity_api.models import OpportunityStatus
from opportunity_api.opportunities.service import can_transition


def test_lifecycle_allows_sequential_progress_and_rejection() -> None:
    assert can_transition(OpportunityStatus.clustered, OpportunityStatus.screened)
    assert can_transition(OpportunityStatus.screened, OpportunityStatus.researching)
    assert can_transition(OpportunityStatus.researching, OpportunityStatus.thesis_ready)
    assert can_transition(OpportunityStatus.clustered, OpportunityStatus.killed)
    assert can_transition(OpportunityStatus.clustered, OpportunityStatus.watchlist)


def test_lifecycle_prevents_unsupported_jumps() -> None:
    assert not can_transition(OpportunityStatus.clustered, OpportunityStatus.build)
    assert not can_transition(OpportunityStatus.screened, OpportunityStatus.pilot)
    assert not can_transition(OpportunityStatus.build, OpportunityStatus.clustered)
    assert can_transition(OpportunityStatus.killed, OpportunityStatus.watchlist)
