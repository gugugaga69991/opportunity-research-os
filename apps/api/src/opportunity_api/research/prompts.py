from opportunity_api.models import ResearchLane
from opportunity_api.research.contracts import CONTRACTS

PROMPT_VERSION = "1.0.0"

LANE_INSTRUCTIONS = {
    ResearchLane.competition: (
        "Map direct, adjacent, service, free, and internal alternatives. "
        "Do not infer pricing or features without evidence."
    ),
    ResearchLane.economics: (
        "Verify labor cost, time cost, error cost, current software/service spend, "
        "budget ownership, and willingness-to-pay signals."
    ),
    ResearchLane.market: (
        "Estimate exact-fit reachable accounts from bottom-up evidence. Reject "
        "generic market-size reports that do not match the ICP."
    ),
    ResearchLane.distribution: (
        "Find concrete directories, communities, associations, events, triggers, "
        "buyer discoverability, and realistic sales friction."
    ),
    ResearchLane.contradiction: (
        "Act as an adversary. Search for incumbent coverage, free solutions, weak "
        "urgency, low budget, switching resistance, and failed startups."
    ),
}

SYSTEM_PROMPT = """You are a specialist researcher inside an evidence-first SaaS opportunity system.
Use only the supplied research documents. Never invent a company, price, market count, feature,
quote, or URL. Unknown values must remain empty, null, or unknown as permitted by the schema.
Every material conclusion needs a short exact quote and URL from the packet. Distinguish facts
from estimates, explain estimation methods, and lower confidence when coverage is weak.
Return every required field in the strict JSON schema."""


def prompt_name(lane: ResearchLane) -> str:
    return f"specialist-research-{lane.value}"


def response_format(lane: ResearchLane) -> dict:
    contract = CONTRACTS[lane]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"{lane.value}_research",
            "strict": True,
            "schema": contract.model_json_schema(),
        },
    }


def messages(lane: ResearchLane, opportunity_context: str, document_packet: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n\nLANE INSTRUCTION:\n{LANE_INSTRUCTIONS[lane]}",
        },
        {
            "role": "user",
            "content": (
                f"OPPORTUNITY:\n{opportunity_context}\n\nRESEARCH PACKET:\n{document_packet}"
            ),
        },
    ]
