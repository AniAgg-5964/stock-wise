"""StockWise — Reorder Center view.

Review periodic-review replenishment recommendations, understand exactly how each
was derived ("Why?"), and optionally record the order the owner decides to place.
Nothing is ordered automatically (PRD 8.1). No reorder math lives here \u2014 the
domain engine computes it and this screen only displays it.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.theme import StockWiseTheme as T
from app.i18n import t
from domain.exceptions import StockWiseError
from domain.money import format_money
from domain.reorder import ReorderRecommendation
from ui.components.empty_state import empty_state
from ui.components.feedback import banner, notify, notify_error
from ui.components.forms import text_field
from ui.components.kpi_card import KpiMetric, kpi_strip
from ui.components.layout import flow_row, page_header, scroll_column, section
from ui.components.table import action_cell, chip_cell, entity_cell, styled_table, text_cell

_URGENCY_STATUS = {
    "critical": "critical",
    "high": "low",
    "medium": "info",
    "low": "neutral",
}
def _urgency_labels() -> dict[str, str]:
    """Per call so a language switch reaches chips built after the switch."""
    return {
        "critical": t("urgency.critical"),
        "high": t("urgency.high"),
        "medium": t("urgency.medium"),
        "low": t("urgency.low"),
    }


def _urgency_chip(reco: ReorderRecommendation) -> ft.DataCell:
    return chip_cell(_urgency_labels().get(reco.urgency, reco.urgency), _URGENCY_STATUS.get(reco.urgency, "info"))


def _why_dialog(reco: ReorderRecommendation) -> ft.AlertDialog:
    def row(label: str, value: str) -> ft.Control:
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text(label, size=T.FONT_SMALL, color=T.TEXT_SECONDARY),
                ft.Text(value, size=T.FONT_SMALL, color=T.TEXT_PRIMARY, weight=ft.FontWeight.W_600),
            ],
        )

    r = reco.rationale()
    lines = [
        row("Protection period P = L + R",
            f"{reco.lead_time_days} + {reco.review_period_days} = {reco.protection_period_days} days"),
        row("Forecast demand over P", f"{reco.forecast_period_demand:g} {reco.unit}"),
        row("Safety stock (SS)", f"{reco.safety_stock:g} {reco.unit}"),
        row("Order-up-to target S", f"{reco.target_position:g} {reco.unit}"),
        row("Usable on hand", f"{reco.usable_on_hand:g}"),
        row("At risk of expiring", f"{reco.at_risk_expiry:g}"),
        row("Confirmed incoming", f"{reco.confirmed_incoming:g}"),
        row("Inventory position IP", f"{reco.inventory_position:g}"),
        row("Raw quantity (S \u2212 IP)", f"{reco.raw_qty:g}"),
        row("MOQ / pack size", f"{reco.minimum_order_qty} / {reco.pack_size}"),
        row("Suggested order", f"{reco.suggested_qty} {reco.unit}"),
        row("Estimated cost", format_money(reco.estimated_cost)),
    ]
    if reco.budget is not None:
        lines.append(row("Budget", format_money(reco.budget)))
        if reco.budget_capped_qty is not None:
            lines.append(row("Budget-capped quantity", f"{reco.budget_capped_qty} (\u2212{reco.shortfall})"))

    notes = [ft.Text(f"\u2022 {n}", size=T.FONT_SMALL, color=T.TEXT_SECONDARY) for n in reco.notes]

    return ft.AlertDialog(
        modal=True,
        title=ft.Text(f"Why order {reco.suggested_qty} \u00d7 {reco.product_name}?"),
        content=ft.Container(
            width=460,
            content=ft.Column(
                tight=True,
                spacing=T.GAP_SMALL,
                scroll=ft.ScrollMode.AUTO,
                controls=lines + [ft.Divider(height=1, color=T.BORDER_SUBTLE), *notes],
            ),
        ),
        actions=[ft.TextButton(content=t("action.close"), on_click=lambda e: e.page.pop_dialog())],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def build_reorder_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    products = list(app.product_service.list_products(active_only=True))

    if not products:
        return scroll_column([
            page_header(t("nav.reorder"), t("dashboard.reorder_subtitle")),
            ft.Container(
                expand=True, bgcolor=T.BG_CARD, border_radius=T.RADIUS,
                border=ft.Border.all(1, T.BORDER_SUBTLE),
                content=empty_state(t("empty.no_products"),
                                    "Add products and record sales to get reorder suggestions.",
                                    icon=ft.Icons.SHOPPING_CART_CHECKOUT_OUTLINED),
            ),
        ])

    state: dict = {"recos": []}
    kpi_holder = ft.Column(spacing=0)
    note_holder = ft.Column(spacing=T.GAP_SMALL)
    table_holder = ft.Column(spacing=0)

    budget_field = text_field("Budget (\u20b9, optional)", hint="e.g. 5000", width=220)

    def _budget() -> Decimal | None:
        text = (budget_field.value or "").strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    def _record_order(reco: ReorderRecommendation) -> None:
        try:
            po_id = app.reorder_service.create_purchase_order(reco)
            reco_id = app.reorder_service.save(reco)
            app.reorder_service.update_status(reco_id, "accepted", reviewed_qty=reco.suggested_qty)
        except StockWiseError as exc:
            notify_error(page, exc)
            return
        notify(page, f"Recorded order #{po_id} for {reco.suggested_qty} \u00d7 {reco.product_name}", "success")
        render()

    def render() -> None:
        try:
            recos = app.reorder_service.recommend_all(budget=_budget(), only_needs_order=True)
        except StockWiseError as exc:
            notify_error(page, exc)
            return
        state["recos"] = recos

        total_cost = sum((r.estimated_cost for r in recos), Decimal("0"))
        critical = sum(1 for r in recos if r.urgency in ("critical", "high"))
        expiry_flags = sum(1 for r in recos if r.expiry_review_required)

        kpi_holder.controls = [
            kpi_strip([
                KpiMetric(t("metric.needs_order"), str(len(recos)),
                          caption=t("cap.protection_period"),
                          icon=ft.Icons.PLAYLIST_ADD_CHECK),
                KpiMetric(t("metric.purchase_cost"), format_money(total_cost),
                          caption=t("cap.supplier_cost"),
                          icon=ft.Icons.PAYMENTS_OUTLINED, accent=T.ACCENT),
                KpiMetric(t("metric.urgent"), str(critical),
                          caption=t("cap.order_soon"), icon=ft.Icons.PRIORITY_HIGH,
                          accent=T.STATUS_CRITICAL if critical else T.STATUS_HEALTHY,
                          delta_kind="down" if critical else "muted"),
                KpiMetric(t("metric.expiry_flagged"), str(expiry_flags),
                          caption=t("cap.consider_markdown"),
                          icon=ft.Icons.EVENT_BUSY_OUTLINED,
                          accent=T.STATUS_WARNING if expiry_flags else T.STATUS_HEALTHY,
                          delta_kind="warn" if expiry_flags else "muted"),
            ])
        ]

        note_holder.controls = [
            banner(t("note.advisory"), "info")
        ] if recos else [
            banner(t("note.all_covered"), "success")
        ]

        rows: list[ft.DataRow] = []
        for reco in recos:
            rows.append(ft.DataRow(cells=[
                entity_cell(reco.product_name, reco.supplier_name or t("supplier.none_preferred")),
                _urgency_chip(reco),
                text_cell(f"{reco.suggested_qty} {reco.unit}"),
                text_cell(format_money(reco.estimated_cost)),
                text_cell(f"{reco.days_to_stockout:.1f} d" if reco.days_to_stockout is not None else "\u2014",
                          color=T.TEXT_SECONDARY),
                chip_cell("Expiry risk", "at_risk") if reco.expiry_review_required
                else text_cell("\u2014", color=T.TEXT_TERTIARY),
                action_cell(lambda e, r=reco: page.show_dialog(_why_dialog(r)),
                            icon=ft.Icons.HELP_OUTLINE, tooltip=t("why.title")),
                action_cell(lambda e, r=reco: _record_order(r),
                            icon=ft.Icons.CHECK_CIRCLE_OUTLINE, tooltip=t("action.record_order")),
            ]))

        table_holder.controls = [
            styled_table(
                [t("col.product"), t("col.urgency"), t("col.suggested"), t("col.est_cost"),
         t("col.stockout_in"), t("col.expiry"), "", ""],
                rows, empty_message=t("empty.no_reorder"),
            )
        ]
        page.update()

    header = page_header(
        t("nav.reorder"),
        t("dashboard.reorder_subtitle"),
        actions=[
            ft.OutlinedButton(content=t("action.generate"), icon=ft.Icons.REFRESH, on_click=lambda e: render()),
        ],
    )

    toolbar = flow_row([
        (budget_field, {"xs": 12, "sm": 6, "lg": 3}),
        (
            ft.Button(content=t("action.recalculate"), icon=ft.Icons.CALCULATE, on_click=lambda e: render()),
            {"xs": 12, "sm": 6, "lg": 3},
        ),
    ])

    render()

    return scroll_column([
        header,
        toolbar,
        note_holder,
        kpi_holder,
        section(t("nav.reorder"), table_holder),
    ])
