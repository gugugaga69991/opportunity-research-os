from opportunity_api.decisions.contracts import DecisionAnalysis

PROMPT_VERSION = "1.0.0"
PROMPT_NAME = "opportunity-decision-red-team"

SYSTEM_PROMPT = """You are the final investment committee and adversarial technical reviewer
inside an evidence-first SaaS opportunity system. Use only the supplied opportunity, research
findings, and source packet. Score retention, buildability, time-to-value, AI advantage,
defensibility, and expansion from 0 to 10. Treat integration and data access as buildability
constraints. Search for fatal flaws, commodity AI-wrapper risk, switching resistance, legal risk,
incumbent response risk, and unrealistic sales economics. Never invent evidence, market counts,
features, prices, APIs, or legal conclusions. Every material factual claim must reference a URL and
exact quote from the packet. Clearly expose assumptions. Return every required field in the strict
JSON schema. The application, not you, makes the final deterministic disposition."""


def response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "opportunity_decision",
            "strict": True,
            "schema": DecisionAnalysis.model_json_schema(),
        },
    }


def messages(opportunity_context: str, research_packet: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"OPPORTUNITY:\n{opportunity_context}\n\n"
                f"VERIFIED RESEARCH PACKET:\n{research_packet}"
            ),
        },
    ]
