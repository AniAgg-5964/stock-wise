"""StockWise — deterministic supplier-fact extraction.

Turns fetched page text into *candidate* facts (price, MOQ, pack size, lead
time). Deliberately rule-based rather than model-based:

* it is free — no metered API calls, and it runs offline in tests
* it is auditable — every fact carries the snippet that produced it
* it never invents — a field is only emitted when a pattern actually matched

Confidence describes how *explicitly the page stated the value*, never whether the
value is correct. Nothing here writes to the database; the service and the user
decide what gets used.
"""

from __future__ import annotations

import re

from integrations.tinyfish.schemas import CandidateFact

# Fields the reorder engine can actually use.
FIELD_UNIT_COST = "unit_cost"
FIELD_MOQ = "minimum_order_qty"
FIELD_PACK_SIZE = "pack_size"
FIELD_LEAD_TIME = "lead_time_days"

#: A number, optionally with Indian/US grouping. Wrapped in (?:...) because it is
#: an alternation and gets embedded inside larger patterns.
_NUM = r"(?:\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"

_RUPEE = r"(?:₹|rs\.?|inr)\s*"

_UNITS = (
    r"kg|kgs|kilogram|kilograms|g|gm|gms|gram|grams|ml|l|ltr|litre|litres|"
    r"litre|liter|pc|pcs|piece|pieces|unit|units|pack|packs|box|boxes|bag|bags|"
    r"dozen|dozens|dz|bottle|bottles|tube|tubes|brick|bricks|carton|cartons|sack|sacks"
)


def _to_number(text: str) -> str:
    """Strip grouping separators, keeping a plain decimal string.

    Returns ``""`` when the capture is not a clean number, so a malformed match
    can never reach a money column.
    """
    cleaned = (text or "").replace(",", "").strip()
    cleaned = re.sub(r"[^0-9.]", "", cleaned)
    if not cleaned or cleaned.count(".") > 1:
        return ""
    try:
        value = float(cleaned)
    except ValueError:
        return ""
    if value <= 0:
        return ""
    return f"{value:g}"


def _clean_int(text: str) -> str:
    cleaned = (text or "").replace(",", "").strip()
    digits = re.sub(r"[^0-9]", "", cleaned)
    if not digits:
        return ""
    try:
        value = int(digits)
    except ValueError:
        return ""
    return str(value) if 0 < value <= 1_000_000 else ""


def _evidence(text: str, match: re.Match) -> str:
    """The surrounding words that justify the value (for the audit trail)."""
    start = max(0, match.start() - 45)
    end = min(len(text), match.end() + 45)
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    return excerpt[:160]


# --- individual field extractors -------------------------------------------------
# Each returns (value, confidence). Confidence is high only when the page labelled
# the number explicitly.

def _unit_cost(text: str) -> list[CandidateFact]:
    facts: list[CandidateFact] = []

    # "MRP: Rs 249" / "Unit price INR 42.50"
    for pattern, confidence in (
        (rf"\bMRP\b[^0-9₹]{{0,12}}{_RUPEE}?\s*({_NUM})", 0.75),
        (rf"\bunit\s*price\b[^0-9₹]{{0,12}}{_RUPEE}?\s*({_NUM})", 0.85),
        (rf"\bprice\b\s*[:\-]?\s*{_RUPEE}\s*({_NUM})", 0.6),
        # "Rs 249 / kg", "₹42 per piece"
        (rf"{_RUPEE}\s*({_NUM})\s*(?:/|per\s+)\s*(?:{_UNITS})\b", 0.8),
        (rf"{_RUPEE}\s*({_NUM})\b(?!\s*(?:x|×|/))", 0.45),
    ):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = _to_number(match.group(1))
            if not value:
                continue
            facts.append(CandidateFact(
                field_name=FIELD_UNIT_COST, field_value=value, currency="INR",
                confidence=confidence, evidence=_evidence(text, match),
            ))
    return facts


def _moq(text: str) -> list[CandidateFact]:
    facts: list[CandidateFact] = []
    patterns = (
        (rf"\bM\.?O\.?Q\.?\b[^0-9]{{0,14}}({_NUM})", 0.9),
        (rf"\bminimum\s+order\s+(?:quantity|qty|amount)\b[^0-9]{{0,14}}({_NUM})", 0.85),
        (rf"\bmin(?:imum)?\.?\s*order\b[^0-9]{{0,14}}({_NUM})", 0.8),
    )
    for pattern, confidence in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = _clean_int(match.group(1))
            if not value:
                continue
            facts.append(CandidateFact(
                field_name=FIELD_MOQ, field_value=value,
                confidence=confidence, evidence=_evidence(text, match),
            ))
    return facts


def _pack_size(text: str) -> list[CandidateFact]:
    facts: list[CandidateFact] = []
    patterns = (
        (rf"\bpack(?:age)?\s*size\b[^0-9]{{0,10}}({_NUM})", 0.9),
        (rf"\bpack(?:ing)?\b[^0-9]{{0,6}}of\s*({_NUM})", 0.75),
        # "case of 12 x 500 g" — group 1 is the pack count.
        (rf"\b({_NUM})\s*(?:x|×)\s*{_NUM}\s*(?:{_UNITS})\b", 0.6),
    )
    for pattern, confidence in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # For the "12 x 500 g" pattern the leading capture is the pack count,
            # which is the number that maps to pack_size.
            value = _clean_int(match.group(1))
            if not value:
                continue
            facts.append(CandidateFact(
                field_name=FIELD_PACK_SIZE, field_value=value,
                confidence=confidence, evidence=_evidence(text, match),
            ))
    return facts


def _lead_time(text: str) -> list[CandidateFact]:
    facts: list[CandidateFact] = []
    patterns = (
        (rf"\b(?:delivery|dispatch|lead\s*time)\b[^0-9]{{0,16}}({_NUM})\s*(?:-|\s)?days?\b", 0.8),
        (rf"\b(?:takes?|ships?|dispatched?)\b[^0-9]{{0,10}}({_NUM})\s*(?:-|\s)?(?:business\s+)?days?\b", 0.6),
        (rf"\b({_NUM})\s*(?:-|\s)?days?\b[^.]{0,24}\b(?:delivery|dispatch|lead\s*time)\b", 0.7),
    )
    for pattern, confidence in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = _clean_int(match.group(1))
            if not value or int(value) > 365:
                continue
            facts.append(CandidateFact(
                field_name=FIELD_LEAD_TIME, field_value=value,
                confidence=confidence, evidence=_evidence(text, match),
            ))
    return facts


_EXTRACTORS = (_unit_cost, _moq, _pack_size, _lead_time)


def extract_facts(text: str, *, max_per_field: int = 3) -> list[CandidateFact]:
    """Extract candidate supplier facts from page text.

    Returns at most ``max_per_field`` facts per field, highest confidence first.
    """
    if not text:
        return []

    collected: list[CandidateFact] = []
    for extractor in _EXTRACTORS:
        collected.extend(extractor(text))

    # Keep the most confidently stated value per field; drop exact duplicates.
    best: dict[tuple[str, str], CandidateFact] = {}
    for fact in collected:
        key = (fact.field_name, fact.field_value)
        current = best.get(key)
        if current is None or fact.confidence > current.confidence:
            best[key] = fact

    by_field: dict[str, list[CandidateFact]] = {}
    for fact in best.values():
        by_field.setdefault(fact.field_name, []).append(fact)

    results: list[CandidateFact] = []
    for facts in by_field.values():
        facts.sort(key=lambda f: -f.confidence)
        results.extend(facts[:max_per_field])

    results.sort(key=lambda f: (-f.confidence, f.field_name))
    return results