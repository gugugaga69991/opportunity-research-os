import hashlib
import html
import re
import unicodedata

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[\w'-]+", re.UNICODE)
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)


def normalize_text(value: str) -> str:
    value = html.unescape(value or "").translate(ZERO_WIDTH)
    value = TAG_RE.sub(" ", value)
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("“", '"').replace("”", '"').replace("’", "'")
    return SPACE_RE.sub(" ", value).strip()


def exact_content_hash(title: str, text: str) -> str:
    stable = f"{normalize_text(title).casefold()}\n{normalize_text(text).casefold()}"
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def tokenise(value: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(normalize_text(value))]


def simhash64(value: str) -> str:
    weights = [0] * 64
    tokens = tokenise(value)
    features = tokens + [" ".join(tokens[index : index + 3]) for index in range(len(tokens) - 2)]
    for feature in features:
        number = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            weights[bit] += 1 if number & (1 << bit) else -1
    result = sum(1 << bit for bit, weight in enumerate(weights) if weight >= 0)
    return f"{result:016x}"


def hamming_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def detect_language(value: str) -> str:
    sample = normalize_text(value).casefold()
    if re.search(r"[\u0900-\u097f]", sample):
        return "hi"
    if re.search(r"[\u4e00-\u9fff]", sample):
        return "zh"
    if re.search(r"[\u0400-\u04ff]", sample):
        return "ru"
    if re.search(r"[\u0600-\u06ff]", sample):
        return "ar"
    english_hits = sum(f" {word} " in f" {sample} " for word in ("the", "and", "to", "of", "is"))
    return "en" if english_hits >= 1 or sample.isascii() else "und"


def evidence_spans(text: str, claims: list[dict[str, str]]) -> list[dict]:
    spans: list[dict] = []
    folded = text.casefold()
    for claim in claims:
        quote = normalize_text(claim.get("quote", ""))[:500]
        start = text.find(quote)
        if start < 0:
            start = folded.find(quote.casefold())
        verified = start >= 0 and bool(quote)
        spans.append(
            {
                "field": claim.get("field", ""),
                "quote": quote,
                "start": start if verified else -1,
                "end": start + len(quote) if verified else -1,
                "verified": verified,
            }
        )
    return spans
