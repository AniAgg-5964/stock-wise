"""StockWise — Live supplier research panel (optional TinyFish stage).

Rendered inside the Supplier Research screen. Two distinct outcomes are kept
apart on purpose:

* **Add as supplier** — turns a search result into a real supplier record. This
  works purely from search metadata, so it succeeds even on the large marketplaces
  that refuse to be fetched.
* **Research** — fetches the page and extracts candidate facts (price, MOQ,
  pack size, lead time). Nothing updates a supplier until the user applies a fact.

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


def _site_cell(candidate) -> ft.DataCell:
    """Site name plus a one-line note about whether a fetch is worth trying.

    The inner Row must be tight: Flet lays DataCell content out with unbounded
    width, and a stretchy Row inside a cell silently blanks the whole table.
    """
    name = candidate.site_name or candidate.host
    note, colour = "", T.TEXT_TERTIARY
    if candidate.likely_blocked:
        note, colour = candidate.block_reason, T.STATUS_WARNING
    elif candidate.already_saved:
        note = "Already saved as a supplier"

    if not note:
        return text_cell(name, color=T.TEXT_SECONDARY)

    return ft.DataCell(
        ft.Row(spacing=10, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
               controls=[ft.Column(spacing=1, tight=True, controls=[
                   ft.Text(name, size=T.FONT_BODY, color=T.TEXT_SECONDARY,
                           weight=ft.FontWeight.W_500),
                   ft.Text(note, size=T.FONT_TINY, color=colour),
               ])])
    )


def build_research_panel(
    page: ft.Page, navigate: Callable[[str], None], products, suppliers
) -> ft.Control:
    """Build the research section (status, search, candidates, candidate facts)."""
    app = app_context
    research = app.research_service
    status = research.status()

    body_holder = ft.Column(spacing=T.GAP_SMALL)
    status_text = ft.Text("", size=T.FONT_TINY, color=T.TEXT_TERTIARY)
    state: dict = {
        "busy": False,
        "candidates": [],
        "last_query": None,
        # Kept mutable so a supplier added here is usable without leaving the screen.
        "suppliers": list(suppliers),
    }

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

    def _supplier_options() -> list[tuple[str, str]]:
        return [(str(s.id), s.name) for s in state["suppliers"]]

    def _effective_query() -> str | None:
        """The query the last search actually used, for provenance notes."""
        typed = (query_field.value or "").strip()
        if typed:
            return typed
        try:
            return research.build_query(_selected_product_id()) or None
        except StockWiseError:
            return None

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
                (find_button, {"xs": 12, "sm": 6, "lg": 3}),
            ]),
            status_text,
        ]

        candidates = state["candidates"]
        if candidates:
            unblocked = sum(1 for c in candidates if not c.likely_blocked)
            parts += [
                ft.Divider(height=1, color=T.BORDER_SUBTLE),
                ft.Row(spacing=10, controls=[
                    ft.Text("Candidate sources", size=T.FONT_SMALL, color=T.TEXT_SECONDARY,
                            weight=ft.FontWeight.W_600, expand=True),
                    ft.TextButton(
                        content=f"Research {unblocked} that may work",
                        icon=ft.Icons.TRAVEL_EXPLORE,
                        on_click=lambda e: _research_unblocked(),
                    ),
                ]),
                styled_table(
                    ["Site", "Page", "Why it matched", "", ""],
                    [
                        ft.DataRow(cells=[
                            _site_cell(candidate),
                            ft.DataCell(ft.TextButton(
                                content=candidate.title or candidate.url,
                                url=candidate.url,
                                tooltip=candidate.url,
                            )),
                            text_cell(candidate.snippet[:140], color=T.TEXT_TERTIARY),
                            action_cell(lambda e, c=candidate: _research(c),
                                        icon=ft.Icons.TRAVEL_EXPLORE,
                                        tooltip="Fetch this page and extract facts"),
                            action_cell(lambda e, c=candidate: _open_add_supplier(c),
                                        icon=ft.Icons.PERSON_ADD_ALT,
                                        tooltip="Save this as a supplier"),
                        ])
                        for candidate in candidates
                    ],
                    empty_message="No candidate sources yet.",
                ),
                ft.Text(
                    "A greyed note under a site means it usually refuses automated "
                    "fetches — you can still try it, and the batch button skips those.",
                    size=T.FONT_TINY, color=T.TEXT_TERTIARY,
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
                    blocked = sum(1 for c in outcome if c.likely_blocked)
                    message = f"Found {len(outcome)} candidate source(s)."
                    if blocked:
                        message += f" {blocked} usually refuse automated fetches."
                    _say(message)
                else:
                    found = len(getattr(outcome, "observations", []) or [])
                    skipped = "; ".join(getattr(outcome, "skipped", []) or [])[:220]
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
        state["last_query"] = _effective_query()
        _run(research.search,
             product_id=_selected_product_id(),
             query=(query_field.value or "").strip() or None)

    def _research(candidate) -> None:
        _run(research.research, url=candidate.url,
             product_id=_selected_product_id(), supplier_id=candidate.supplier_id)

    def _research_unblocked() -> None:
        """Fetch only the sources most likely to return usable content."""
        _run(research.research_candidates, state["candidates"],
             product_id=_selected_product_id(),
             query=state["last_query"], skip_blocked=True)

    def _open_add_supplier(candidate) -> None:
        """Turn a search result into a real supplier record."""
        draft = research.draft_supplier(candidate, query=state["last_query"])
        name_field = text_field("Supplier name", value=draft.name, expand=True)
        website_field = text_field("Website", value=draft.website_url, expand=True)
        notes_field = text_field("Notes", value=draft.notes, multiline=True, expand=True)

        context: list[ft.Control] = [
            ft.Text("Found on the page:", size=T.FONT_TINY, color=T.TEXT_TERTIARY),
            ft.Text(candidate.title or candidate.url, size=T.FONT_SMALL, color=T.TEXT_SECONDARY),
        ]
        if candidate.snippet:
            context.append(
                ft.Text(candidate.snippet[:220], size=T.FONT_TINY, color=T.TEXT_TERTIARY)
            )
        context.append(ft.Text(
            "The name is a guess from the website — change it if it is wrong.",
            size=T.FONT_TINY, color=T.TEXT_TERTIARY,
        ))

        notices: list[ft.Control] = []
        if draft.already_saved:
            notices.append(banner(
                f"'{draft.existing_supplier.name}' is already saved with this website. "
                "Add anyway only if this is a genuinely different branch.",
                "warning",
            ))

        def save(e) -> None:
            draft.name = name_field.value or ""
            draft.website_url = website_field.value or ""
            draft.notes = notes_field.value or ""
            page.pop_dialog()
            try:
                supplier = research.add_supplier_from_candidate(
                    draft, force=draft.already_saved
                )
            except StockWiseError as exc:
                notify_error(page, exc)
                return
            state["suppliers"].append(supplier)
            candidate.supplier_id = supplier.id
            notify(page, f"Added '{supplier.name}' to your suppliers", "success")
            _render()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Save this source as a supplier"),
            content=ft.Container(width=520, content=ft.Column(tight=True, spacing=T.GAP_SMALL, controls=[
                *notices,
                *context,
                ft.Divider(height=1, color=T.BORDER_SUBTLE),
                name_field,
                website_field,
                notes_field,
            ])),
            actions=[
                ft.TextButton(content="Cancel", on_click=lambda e: page.pop_dialog()),
                ft.Button(
                    content="Add anyway" if draft.already_saved else "Add supplier",
                    on_click=save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        ))

    def _apply_observation(obs) -> None:
        options = _supplier_options()
        if not options:
            notify(page, "Add a supplier first, then apply a fact to it", "warning")
            return

        # Prefer the supplier this fact actually came from, when we know it.
        default = str(obs.supplier_id) if obs.supplier_id else options[0][0]
        if obs.supplier_id and all(str(obs.supplier_id) != key for key, _ in options):
            default = options[0][0]

        supplier_dd = dropdown_field("Apply to supplier", options, value=default, width=360)

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