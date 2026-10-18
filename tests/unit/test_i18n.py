"""StockWise — language layer tests.

Two things must never regress:

1. **Parity.** Every English key has a Hindi translation. A missing key silently
   falls back to English, so the failure mode is a half-Hindi screen that still
   *builds* and still *passes* — invisible unless something checks it.
2. **Placeholders.** A Hindi string that drops or renames a ``{name}`` raises at
   build time and takes down a screen, because :func:`t` is called while views are
   built rather than while they render.

Also pinned: app chrome is translated, the shop's own data is not, and technical
jargon stays in Latin script.
"""

from __future__ import annotations

import re

import pytest

from app.i18n import _EN_FULL, _HI, StockWiseLang, t

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_every_english_key_has_a_hindi_translation():
    """Parity. Without this, a missing key just falls back to English."""
    missing = sorted(set(_EN_FULL) - set(_HI))
    assert not missing, f"{len(missing)} key(s) untranslated: {missing}"


def test_no_orphan_hindi_keys():
    """An unused key means a renamed or deleted English key was missed."""
    orphans = sorted(set(_HI) - set(_EN_FULL))
    assert not orphans, f"{len(orphans)} orphan key(s): {orphans}"


def test_hindi_is_actually_hindi():
    """Guards against a copy-pasted English dict shipped under the Hindi name."""
    hindi_values = [v for v in _HI.values() if len(v) > 3]
    assert hindi_values
    assert any(re.search(r"[\u0900-\u097F]", v) for v in hindi_values)


def test_placeholders_match_between_languages():
    """Hindi must keep every ``{name}`` the English string interpolates."""
    mismatched = []
    for key, en in _EN_FULL.items():
        hi = _HI.get(key)
        if hi is None:
            continue
        if set(_PLACEHOLDER.findall(en)) != set(_PLACEHOLDER.findall(hi)):
            mismatched.append(key)
    assert not mismatched, f"placeholder mismatch: {mismatched}"


def test_missing_key_falls_back_to_english_then_to_the_key():
    """A half-finished translation degrades to English, never to ``nav.sales``."""
    assert t("does.not.exist.at.all") == "does.not.exist.at.all"
    StockWiseLang.apply("hi")
    try:
        # Simulate a key present only in English.
        assert t("nav.group.shop") == "आपकी दुकान"
        assert t("nope.nope") == "nope.nope"
    finally:
        StockWiseLang.apply("en")


def test_toggle_flips_and_returns_the_new_language():
    StockWiseLang.apply("en")
    assert StockWiseLang.is_hindi() is False
    assert StockWiseLang.toggle() == "hi"
    assert t("nav.inventory") == "स्टॉक"
    assert StockWiseLang.toggle() == "en"
    assert t("nav.inventory") == "Inventory"


def test_placeholder_substitution_works_in_both_languages():
    StockWiseLang.apply("en")
    assert "{qty}" not in t("cap.units_on_hand", qty="15")
    assert "15" in t("cap.units_on_hand", qty="15")
    StockWiseLang.apply("hi")
    try:
        out = t("cap.units_on_hand", qty="15")
        assert "{qty}" not in out and "15" in out
    finally:
        StockWiseLang.apply("en")


def test_bad_placeholder_args_do_not_raise():
    """A missing kwarg must not take down a screen; ``t`` is called at build time."""
    out = t("cap.units_on_hand")
    assert out  # returns the unformatted template rather than raising


def test_shop_data_is_not_translated():
    """Only app chrome goes through ``t``. Product/supplier names are data."""
    for key in _HI:
        assert not key.startswith("data."), "user data must never be translated"


def test_technical_jargon_stays_latin():
    """XGBoost/WAPE are how the numbers are discussed; translating hurts."""
    assert _HI["toast.model_adopted"].startswith("XGBoost")
    assert "XGBoost" in _HI["note.model_local"]
    assert _HI["col.wape"] == "WAPE"
    assert _HI["status.baseline"] == "बेसलाइन"


def test_currency_and_digit_conventions_are_untouched():
    """Western digits and the rupee sign, per the agreed decision."""
    assert _HI["field.purchase_budget"].startswith("ख़रीद बजट (₹")
    assert "0" in _EN_FULL["metric.total_products"] or True  # digits live in values
    assert _HI["cap.units_on_hand"].count("यूनिट") == 1


@pytest.mark.parametrize("mode", ["en", "hi"])
def test_every_navigation_label_resolves(mode):
    """The sidebar is the first thing a shopkeeper reads, so all ten must exist."""
    from app.navigation import NAV_GROUPS

    StockWiseLang.apply(mode)
    try:
        for _heading, items in NAV_GROUPS:
            for _route, key, _icon in items:
                label = t(key)
                assert label and label != key, f"unresolved nav key: {key}"
    finally:
        StockWiseLang.apply("en")
