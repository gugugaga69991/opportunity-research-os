from opportunity_api.processing.schemas import SignalOntology

PROMPT_NAME = "signal-ontology-extraction"
PROMPT_VERSION = "1.0.0"
SYSTEM_PROMPT = """You are the evidence engine for a SaaS opportunity research system.
Classify the supplied source document and extract only facts supported by its text.
Empty strings and empty lists are preferable to guesses. A pain is a repeated, costly,
risky, slow, manual, fragmented, or compliance-sensitive workflow problem—not merely
negative sentiment. Evidence quotes must be exact, brief substrings of the source.
Return every field required by the JSON schema."""


def response_format() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "signal_ontology",
            "strict": True,
            "schema": SignalOntology.model_json_schema(),
        },
    }


def messages(title: str, text: str, source_type: str) -> list[dict[str, str]]:
    content = f"SOURCE TYPE: {source_type}\nTITLE: {title}\nDOCUMENT:\n{text[:30000]}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
