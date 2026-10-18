"""StockWise — Live supplier research panel (optional TinyFish stage).

Rendered inside the Supplier Research screen. Every fact found on the web is
shown as a *candidate*; nothing updates a supplier, cost, MOQ or lead time until
the user picks the supplier and applies it.

Design notes:
* network calls run off the UI thread (``asyncio.to_thread``) so a slow page
  never freezes the window
* the UI never calls TinyFish directly — only ``SupplierResearchService``
* when the key is missing or research is switched off, the panel explains why
  and offers no controls that could send data anywhere
"""

from __future__ import annotations

import asyncio
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.theme import StockWiseTheme as T
from application.services.supplier_research_service import FIELD_LABELS
from domain.exceptions import StockWiseError
from ui.components.feedback import banner, notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.layout import flow_row, section
from ui.components.table import action_cell, chip_cell, styled_table, text_cell

NO_PRODUCT = "__none__"


def _confidence_color(confidence: float) -> str:
    if confidence >= 0.75:
        return T.STATUS_HEALTHY
    if confidence >= 0.5:
        return T.STATUS_WARNING
    return T.TEXT_TERTIARY


def _status_notice(status) -> list[ft.Control]:
    """Explain exactly why research is unavailable, in the user's terms."""
    if not status.configured:
        return [banner(
            "Live research is unavailable because no TinyFish API key is configured. "
            "Add TINYFISH_API_KEY to your .env file and restart StockWise. "
            "Everything else works without it.",
            "warning",
        )]
    if not status.enabled:
        return [banner(
            "Live research is switched off. Turn on 'Enable live web research' to "
            "search and fetch supplier pages. Nothing leaves this machine while it is off.",
            "info",
        )]
    return []


def build_research_panel(
    page: ft.Page, navigate: Callable[[str], None], products, suppliers
) -> ft.Control:
    """Build the research section (status, search, candidates, candidate facts)."""
    app = app_context
    research = app.research_service
    status = research.status()

    body_holder = ft.Column(spacing=T.GAP_SMALL)
    status_text = ft.Text("", size=T.FONT_TINY, color=T.TEXT_TERTIARY)
    state: dict = {"busy": False, "candidates": []}

    def _say(message: str, colour: str = T.TEXT_TERTIARY) -> None:
        status_text.value = message
        status_text.color = colour
        try:
            status_text.update()
        except Exception:  # pragma: no cover - control not mounted yet
            pass

    def _safe_update() -> None:
        try:
            body_holder.update()
        except Exception:  # pragma: no cover - defensive
            pass

    def _selected_product_id() -> int | None:
        if product_dd.value and product_dd.value != NO_PRODUCT:
            return int(product_dd.value)
        return None

    def _product_label(product_id: int | None) -> str:
        if product_id is None:
            return ""
        product = app.product_service.get_product(product_id)
        return product.name if product else ""

    # ------------------------------------------------------------------ render
    def _render() -> None:
        if not status.can_run:
            body_holder.controls = _status_notice(status)
            _safe_update()
            return

        product_id = _selected_product_id()
        parts: list[ft.Control] = [
            flow_row([
                (product_dd, {"xs": 12, "sm": 6, "lg": 4}),
                (query_field, {"xs": 12, "sm": 6, "lg": 5}),
                (find_button, {"xs": 12, "sm": 12, "lg": 3}),
            ]),
            status_text,
        ]

        if state["candidates"]:
            parts += [
                ft.Divider(height=1, color=T.BORDER_SUBTLE),
                ft.Text("Candidate sources", size=T.FONT_SMALL, color=T.TEXT_SECONDARY,
                        weight=ft.FontWeight.W_600),
                styled_table(
                    ["Site", "Page", "Why it matched", ""],
                    [
                        ft.DataRow(cells=[
                            text_cell(candidate.site_name, color=T.TEXT_SECONDARY),
                            ft.DataCell(ft.TextButton(
                                content=candidate.title or candidate.url,
                                url=candidate.url,
                                tooltip=candidate.url,
                            )),
                            text_cell(candidate.snippet[:140], color=T.TEXT_TERTIARY),
                            action_cell(lambda e, c=candidate: _research(c),
                                        icon=ft.Icons.TRAVEL_EXPLORE,
                                        tooltip="Fetch this page and extract facts"),
                        ])
                        for candidate in state["candidates"]
                    ],
                ),
            ]

        if product_id is not None:
            observations = list(research.observations_for_product(product_id))
            parts += [
                ft.Divider(height=1, color=T.BORDER_SUBTLE),
                ft.Text(f"Candidate facts for {_product_label(product_id)}",
                        size=T.FONT_SMALL, color=T.TEXT_SECONDARY, weight=ft.FontWeight.W_600),
                styled_table(
                    ["Field", "Value", "Confidence", "State", "", ""],
                    [
                        ft.DataRow(cells=[
                            text_cell(FIELD_LABELS.get(obs.field_name, obs.field_name)),
                            text_cell(f"{obs.field_value} {obs.currency or ''}".strip()),
                            text_cell(f"{obs.confidence:.0%}",
                                      color=_confidence_color(obs.confidence)),
                            chip_cell("Applied" if obs.verified_by_user else "Unverified",
                                      "healthy" if obs.verified_by_user else "info"),
                            action_cell(lambda e, o=obs: _apply_observation(o),
                                        icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                                        tooltip="Apply to a supplier"),
                            action_cell(lambda e, o=obs: _reject_observation(o),
                                        icon=ft.Icons.CLOSE, tooltip="Discard this candidate"),
                        ])
                        for obs in observations
                    ],
                    empty_message="No candidate facts yet \u2014 research a source above.",
                ),
                ft.Text(
                    "Confidence reflects how explicitly the page stated the value, "
                    "not whether the value is correct. Always check before applying.",
                    size=T.FONT_TINY, color=T.TEXT_TERTIARY,
                ),
            ]

        body_holder.controls = parts
        _safe_update()

    # ------------------------------------------------------------------ actions
    def _run(func, *args, **kwargs) -> None:
        """Run a blocking service call off the UI thread, then re-render."""
        if state["busy"]:
            notify(page, "Still working on the previous request", "warning")
            return
        state["busy"] = True
        _say("Working\u2026")

        async def _worker() -> None:
            try:
                outcome = await asyncio.to_thread(func, *args, **kwargs)
                if isinstance(outcome, list):
                    state["candidates"] = outcome
                    _say(f"Found {len(outcome)} candidate source(s). Pick one to research.")
                else:
                    found = len(getattr(outcome, "observations", []) or [])
                    skipped = "; ".join(getattr(outcome, "skipped", []) or [])[:200]
                    if skipped:
                        _say(skipped, T.STATUS_WARNING)
                    elif outcome.cached:
                        _say(f"Reused cached facts ({found} candidate(s)).")
                    elif found:
                        _say(f"Extracted {found} candidate fact(s). Review, then apply.")
                    else:
                        _say("Nothing extractable on that page.")
            except StockWiseError as exc:
                notify_error(page, exc)
                _say(str(exc), T.STATUS_CRITICAL)
            except Exception as exc:  # pragma: no cover - unexpected
                notify_error(page, exc)
                _say(f"Unexpected error: {exc}", T.STATUS_CRITICAL)
            finally:
                state["busy"] = False
                _render()

        page.run_task(_worker)

    def _do_search(e=None) -> None:
        state["candidates"] = []
        _run(research.search,
             product_id=_selected_product_id(),
             query=(query_field.value or "").strip() or None)

    def _research(candidate) -> None:
        _run(research.research, url=candidate.url, product_id=_selected_product_id())

    def _apply_observation(obs) -> None:
        if not suppliers:
            notify(page, "Add a supplier first, then apply a fact to it", "warning")
            return
        supplier_dd = dropdown_field(
            "Apply to supplier", [(str(s.id), s.name) for s in suppliers],
            value=str(suppliers[0].id), width=360,
        )

        def confirm(e) -> None:
            page.pop_dialog()
            try:
                research.apply(obs.id, int(supplier_dd.value))
                notify(page, f"Applied {FIELD_LABELS.get(obs.field_name, obs.field_name)}",
                       "success")
                _render()
            except StockWiseError as exc:
                notify_error(page, exc)

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Apply '{obs.field_value}' to a supplier?"),
            content=ft.Container(width=400, content=ft.Column(tight=True, spacing=T.GAP_SMALL, controls=[
                supplier_dd,
                ft.Text(
                    f"{FIELD_LABELS.get(obs.field_name, obs.field_name)} \u00b7 "
                    f"confidence {obs.confidence:.0%} \u00b7 found on a web page",
                    size=T.FONT_TINY, color=T.TEXT_TERTIARY,
                ),
            ])),
            actions=[
                ft.TextButton(content="Cancel", on_click=lambda e: page.pop_dialog()),
                ft.Button(content="Apply", on_click=confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def _reject_observation(obs) -> None:
        try:
            research.reject(obs.id)
            notify(page, "Candidate discarded", "success")
            _render()
        except StockWiseError as exc:
            notify_error(page, exc)

    def _toggle(e) -> None:
        research.set_enabled(bool(e.control.value))
        notify(page, "Live research " + ("enabled" if e.control.value else "disabled"), "success")
        _render()

    # ----------------------------------------------------------------- controls
    product_dd = dropdown_field(
        "Product to research",
        [(str(p.id), p.name) for p in products] or [(NO_PRODUCT, "No products yet")],
        value=str(products[0].id) if products else NO_PRODUCT,
        on_select=lambda e: _render(),
    )
    query_field = text_field("Or search for\u2026", hint="e.g. bulk rice supplier", width=320)
    find_button = ft.Button(content="Find suppliers", icon=ft.Icons.SEARCH, on_click=_do_search)

    toggle = ft.Switch(
        label="Enable live web research",
        value=status.enabled,
        label_text_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL),
        on_change=_toggle,
    )

    _render()

    return section(
        "Live supplier research",
        ft.Column(spacing=T.GAP_SMALL, controls=[toggle, body_holder]),
        subtitle="TinyFish Search + Fetch (free tier) \u00b7 facts stay advisory until you apply them",
    )