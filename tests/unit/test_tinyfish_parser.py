"""Supplier-fact parser tests.

The parser must extract real, clearly-stated numbers and nothing else: a page
that does not state a value must never produce an observation.
"""

from __future__ import annotations

from integrations.tinyfish import parser
from integrations.tinyfish.parser import extract_facts

LISTING = """
Shree Ram Chakki Fresh Atta - Premium Whole Wheat Flour
Brand: Shree Ram. Pack size: 10 kg. MRP: Rs 249.
Unit price Rs 42.50 per kg. MOQ: 50 bags. Minimum order quantity 20 cartons.
Delivery in 4 days. Dispatch time 3 days. Price: Rs 1,299.50
Case of 12 x 500 g. Available in pack of 6.
"""


def _by_field(text, field):
    return [f for f in extract_facts(text) if f.field_name == field]


def _values(text, field):
    return [f.field_value for f in _by_field(text, field)]


def test_empty_text_yields_nothing():
    assert extract_facts("") == []
    assert extract_facts(None) == []


def test_prose_without_numbers_yields_nothing():
    assert extract_facts(
        "We supply the finest selection of imported groceries to hotels and bakeries."
    ) == []


def test_extracts_the_unit_price_stated_with_a_rupee_symbol():
    prices = _values(LISTING, parser.FIELD_UNIT_COST)
    assert "42.5" in prices
    assert "249" in prices


def test_unit_prices_are_tagged_inr():
    facts = _by_field(LISTING, parser.FIELD_UNIT_COST)
    assert all(f.currency == "INR" for f in facts)


def test_extracts_moq_from_several_phrasings():
    moqs = _values(LISTING, parser.FIELD_MOQ)
    assert "50" in moqs, "MOQ: 50 bags"
    assert "20" in moqs, "Minimum order quantity 20 cartons"


def test_extracts_pack_size():
    packs = _values(LISTING, parser.FIELD_PACK_SIZE)
    assert "10" in packs, "Pack size: 10 kg"
    assert "12" in packs, "Case of 12 x 500 g"
    assert "6" in packs, "Available in pack of 6"


def test_extracts_lead_time_in_days():
    lead = _values(LISTING, parser.FIELD_LEAD_TIME)
    assert "4" in lead, "Delivery in 4 days"
    assert "3" in lead, "Dispatch time 3 days"


def test_explicit_labels_outrank_bare_numbers():
    prices = _by_field(LISTING, parser.FIELD_UNIT_COST)
    labelled = next(f for f in prices if f.field_value == "42.5")
    assert labelled.confidence >= 0.8


def test_results_are_ordered_by_confidence():
    facts = extract_facts(LISTING)
    scores = [f.confidence for f in facts]
    assert scores == sorted(scores, reverse=True)


def test_every_fact_carries_its_evidence():
    for fact in extract_facts(LISTING):
        assert fact.evidence, f"{fact.field_name} has no evidence snippet"


def test_malformed_numbers_are_discarded():
    assert extract_facts("Price: Rs .,,.. and MOQ: abc and pack size: ??") == []


def test_zero_and_negative_values_are_discarded():
    assert _values("MRP: Rs 0 and MOQ: 0", parser.FIELD_UNIT_COST) == []
    assert _values("MOQ: 0", parser.FIELD_MOQ) == []


def test_absurd_lead_times_are_rejected():
    assert _values("Delivery time 900 days", parser.FIELD_LEAD_TIME) == []


def test_results_are_capped_per_field():
    text = "MOQ: 10 MOQ: 20 MOQ: 30 MOQ: 40 MOQ: 50 MOQ: 60"
    assert len(_by_field(text, parser.FIELD_MOQ)) <= 3


def test_only_supported_field_names_are_emitted():
    allowed = {
        parser.FIELD_UNIT_COST, parser.FIELD_MOQ,
        parser.FIELD_PACK_SIZE, parser.FIELD_LEAD_TIME,
    }
    assert {f.field_name for f in extract_facts(LISTING)} <= allowed


def test_values_are_plain_decimal_or_integer_strings():
    for fact in extract_facts(LISTING):
        stripped = fact.field_value.replace(".", "")
        assert stripped.isdigit(), fact.field_value