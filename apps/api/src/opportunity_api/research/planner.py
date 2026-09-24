from dataclasses import dataclass

from opportunity_api.models import OpportunityHypothesis, ResearchLane


@dataclass(frozen=True)
class PlannedTarget:
    query: str
    rationale: str


def _clean(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _deduplicate(targets: list[PlannedTarget]) -> list[PlannedTarget]:
    seen: set[str] = set()
    result: list[PlannedTarget] = []
    for target in targets:
        key = target.query.casefold()
        if key not in seen and len(target.query) >= 4:
            seen.add(key)
            result.append(target)
    return result


def plan_research(opportunity: OpportunityHypothesis) -> dict[ResearchLane, list[PlannedTarget]]:
    thesis = opportunity.thesis or {}
    task = thesis.get("task") or opportunity.core_workflow or opportunity.name
    industry = opportunity.industry
    buyer = opportunity.buyer_role
    user = opportunity.user_role
    icp = opportunity.icp
    problem = opportunity.problem
    software = (thesis.get("current_software") or [""])[0]
    trigger = thesis.get("trigger", "")
    return {
        ResearchLane.competition: _deduplicate(
            [
                PlannedTarget(_clean(task, "software", industry), "Find direct workflow software."),
                PlannedTarget(
                    _clean(problem, "software solution"), "Find problem-positioned vendors."
                ),
                PlannedTarget(
                    _clean(software, "alternatives pricing"), "Map incumbent alternatives."
                ),
                PlannedTarget(
                    _clean(task, "automation SaaS pricing"), "Find automation competitors."
                ),
                PlannedTarget(_clean(task, "open source free tool"), "Find free substitutes."),
            ]
        ),
        ResearchLane.economics: _deduplicate(
            [
                PlannedTarget(_clean(user, "salary", industry), "Estimate labor cost."),
                PlannedTarget(_clean(task, "outsourcing service pricing"), "Verify service spend."),
                PlannedTarget(
                    _clean(task, "consultant agency pricing"), "Find agency price evidence."
                ),
                PlannedTarget(_clean(problem, "cost case study"), "Find quantified pain costs."),
                PlannedTarget(_clean(task, "software pricing"), "Find existing software budgets."),
            ]
        ),
        ResearchLane.market: _deduplicate(
            [
                PlannedTarget(
                    _clean("number of", icp, "companies"), "Estimate exact-fit accounts."
                ),
                PlannedTarget(
                    _clean(industry, "business count statistics"), "Find primary market counts."
                ),
                PlannedTarget(
                    _clean(industry, task, "market trend"), "Assess workflow demand trend."
                ),
                PlannedTarget(
                    _clean(user, "jobs", industry), "Use related hiring as a demand proxy."
                ),
            ]
        ),
        ResearchLane.distribution: _deduplicate(
            [
                PlannedTarget(
                    _clean(industry, "company directory association"), "Find account lists."
                ),
                PlannedTarget(
                    _clean(buyer, industry, "association conference"), "Find buyer channels."
                ),
                PlannedTarget(
                    _clean(user, "professional community", industry), "Find user communities."
                ),
                PlannedTarget(
                    _clean(trigger, industry, "companies"), "Find trigger-based targeting."
                ),
            ]
        ),
        ResearchLane.contradiction: _deduplicate(
            [
                PlannedTarget(
                    _clean(task, "already automated"), "Test whether the workflow is solved."
                ),
                PlannedTarget(
                    _clean(software, task, "feature"), "Check incumbent feature coverage."
                ),
                PlannedTarget(
                    _clean(task, "free tool open source"), "Search for free displacement risk."
                ),
                PlannedTarget(_clean(problem, "not a problem"), "Seek explicit counter-evidence."),
                PlannedTarget(
                    _clean(task, "startup failed shutdown"), "Find failed attempts and causes."
                ),
            ]
        ),
    }


def actor_input(
    lane: ResearchLane,
    targets: list[PlannedTarget],
    max_documents: int,
    discovery_actor_id: str = "apify/google-search-scraper",
) -> dict:
    return {
        "mode": "search",
        "searchQueries": [target.query for target in targets],
        "discoveryActorId": discovery_actor_id,
        "maxResultsPerQuery": max(5, max_documents // max(len(targets), 1)),
        "maxItems": max_documents,
        "includeFullContent": True,
        "documentType": "research_document",
        "respectRobots": True,
        "researchLane": lane.value,
    }
