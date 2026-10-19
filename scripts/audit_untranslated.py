"""Audit: which user-visible strings are still untranslated in Hindi mode?

Builds every route with the language set to Hindi, walks the control tree, and
reports any user-visible string containing no Devanagari. Those are strings the
i18n migration missed — they render as English inside a Hindi screen, which is
the failure mode ``tests/unit/test_i18n.py`` cannot see (that only checks a key
*exists*, not that a view uses it).

Product names, SKUs, supplier names, contacts, units and file paths are the
shop's own data and are **expected** to stay Latin; they are classified as DATA
and reported separately from real chrome.

    .venv\\Scripts\\python.exe scripts\\audit_untranslated.py [--data]
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import flet as ft  # noqa: E402

from app.bootstrap import app_context  # noqa: E402
from app.i18n import StockWiseLang as L  # noqa: E402
from ui.views.registry import build_view  # noqa: E402

ROUTES = ["/", "/inventory", "/sales", "/forecasting", "/reorder", "/expiry",
          "/suppliers", "/reports", "/data", "/settings"]

SHOW_DATA = "--data" in sys.argv

DEVA = range(0x0900, 0x0980)
# Anything a shopkeeper typed, or a value the app must not rewrite.
DATA_PATTERNS = (
    "csv", ".db", "models", "backups", "exports", "xgb-", "sku",
    "@", "DEMO-", "YYYY-MM-DD",
)


class Page:
    def update(self) -> None: ...
    client_storage: dict = {}


def _has_deva(s: str) -> bool:
    return any(ord(c) in DEVA for c in s)


def _ascii_letters(s: str) -> bool:
    return any(c.isalpha() and c.isascii() for c in s)


def _is_data(s: str) -> bool:
    low = s.lower()
    if any(p in low for p in DATA_PATTERNS):
        return True
    if any(c.isdigit() for c in s) and len(s.split()) <= 2:
        return True  # quantities, "4d", "15 pkt"
    return False


CHROME: dict[str, set[str]] = {}
DATA: dict[str, set[str]] = {}
_CUR = ["/"]
_FAILED: list[str] = []


def _report(value, where: str) -> None:
    if not isinstance(value, str):
        return
    s = value.strip()
    if len(s) < 2 or _has_deva(s) or not _ascii_letters(s):
        return
    bucket = DATA if _is_data(s) else CHROME
    bucket.setdefault(_CUR[0], set()).add(f"{s!r}  ({where})")


def _walk(node, seen) -> None:
    if not isinstance(node, ft.Control) or id(node) in seen:
        return
    seen.add(id(node))

    if isinstance(node, ft.Text):
        _report(node.value, "Text")
    elif isinstance(node, ft.DropdownOption):
        _report(node.text, "DropdownOption")
    elif isinstance(node, (ft.Button, ft.OutlinedButton, ft.TextButton,
                           ft.IconButton, ft.FilledButton)):
        c = getattr(node, "content", None)
        if isinstance(c, str):
            _report(c, type(node).__name__)
        _report(getattr(node, "tooltip", None), "tooltip")

    for attr in ("controls", "content", "leading", "trailing", "label", "options",
                 "title", "subtitle", "prefix", "suffix", "columns", "rows",
                 "actions", "cells", "error_text", "hint_text"):
        val = getattr(node, attr, None)
        if val is None:
            continue
        for item in (val if isinstance(val, (list, tuple)) else [val]):
            if isinstance(item, ft.Control):
                _walk(item, seen)
            elif isinstance(item, str) and attr in ("tooltip", "hint_text", "error_text"):
                _report(item, f"{type(node).__name__}.{attr}")


def main() -> int:
    app_context.initialize()
    prods = app_context.product_service.list_products(active_only=True)
    routes = ROUTES + [f"/product/{prods[0].id}", f"/product/{prods[1].id}"]
    L.apply("hi")
    try:
        for r in routes:
            _CUR[0] = r
            try:
                view = build_view(r, Page(), lambda _r: None)
            except Exception as exc:
                _FAILED.append(f"{r}: {type(exc).__name__}: {exc}")
                continue
            _walk(view, set())
    finally:
        L.apply("en")

    for route in routes:
        items = sorted(CHROME.get(route, ()))
        if not items:
            continue
        print(f"=== {route}  ({len(items)})")
        for i in items:
            print("   " + i)
    print(f"\nUNTRANSLATED CHROME: {sum(len(v) for v in CHROME.values())}")
    if _FAILED:
        print("\nBUILD FAILURES:")
        for f in _FAILED:
            print("   " + f)
    if SHOW_DATA:
        print("\n--- data (expected Latin) ---")
        for route in routes:
            items = sorted(DATA.get(route, ()))
            if items:
                print(f"=== {route}  ({len(items)})")
                for i in items:
                    print("   " + i)
    return 1 if (CHROME or _FAILED) else 0


if __name__ == "__main__":
    raise SystemExit(main())
