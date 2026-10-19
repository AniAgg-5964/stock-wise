"""StockWise — Expiry management view.

Lists batches by expiry (soonest first), estimates how much of each batch is
likely to expire unsold (FEFO-aware), separates already-expired stock, and lets
the user write off a batch as waste. Expired stock is never sellable.

The "at risk" figure is an *estimate from the forecast*, not recorded waste.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.config import Config
from app.theme import StockWiseTheme as T
from app.i18n import t
from domain.exceptions import StockWiseError
from domain.money import format_money
from ui.components.empty_state import empty_state
from ui.components.feedback import notify, notify_error
from ui.components.forms import text_field
from ui.components.kpi_card import KpiMetric, kpi_strip
from ui.components.layout import page_header, scroll_column, section
from ui.components.table import action_cell, chip_cell, styled_table, text_cell


def _days_left(expiry: str | None) -> int | None:
    if not expiry:
        return None
    try:
        target = date.fromisoformat(str(expiry)[:10])
    except ValueError:
        return None
    return (target - date.today()).days


def _daily_forecast(app, product_id: int, horizon: int = 90) -> list[float]:
    """Daily demand for a product: stored forecast if present, else recent average."""
    latest = app.forecast_service.latest(product_id)
    values = [p.predicted_qty for p in latest.points] if (latest and latest.points) else []
    if not values:
        avg = app.forecast_service.average_daily_demand(product_id)
        return [float(avg)] * horizon
    if len(values) < horizon:
        mean = sum(values) / len(values)
        values = values + [mean] * (horizon - len(values))
    return [float(v) for v in values]


def _batch_risk(app, product_id: int) -> dict[int, float]:
    """Estimate unsold quantity per batch using FEFO demand allocation.

    Demand consumes the earliest-expiring batch first, so a batch expiring soon
    is only at risk for what earlier batches could not absorb.
    """
    batches = [b for b in app.inventory_service.get_batches(product_id) if b.expiry_date]
    if not batches:
        return {}
    batches.sort(key=lambda b: str(b.expiry_date))
    daily = _daily_forecast(app, product_id)

    risk: dict[int, float] = {}
    consumed = 0.0
    for batch in batches:
        left = _days_left(batch.expiry_date)
        if left is None:
            continue
        if left < 0:
            risk[batch.id] = float(batch.quantity_remaining)  # already unusable
            continue
        demand_until = sum(daily[:left])
        available = max(0.0, demand_until - consumed)
        allocated = min(float(batch.quantity_remaining), available)
        consumed += allocated
        risk[batch.id] = max(0.0, float(batch.quantity_remaining) - allocated)
    return risk


def build_expiry_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    window = int(float(app.settings.get("near_expiry_window_days", str(Config.NEAR_EXPIRY_WINDOW_DAYS)) or 7))

    expiring = list(app.inventory_service.expiring_batches(window))
    expired = list(app.inventory_service.expired_batches())

    risk_cache: dict[int, dict[int, float]] = {}

    def risk_for(batch) -> float:
        if batch.product_id not in risk_cache:
            risk_cache[batch.product_id] = _batch_risk(app, batch.product_id)
        return risk_cache[batch.product_id].get(batch.id, float(batch.quantity_remaining))

    def build_rows(batches, *, expired_rows: bool):
        rows = []
        for batch in batches:
            product = app.product_service.get_product(batch.product_id)
            name = product.name if product else f"Product {batch.product_id}"
            left = _days_left(batch.expiry_date)
            if expired_rows:
                label, status = t("status.expired"), "expired"
                left_text = (t("expiry.days_ago", days=abs(left)) if left is not None else "\u2014")
            else:
                label, status = t("status.near_expiry"), "near_expiry"
                left_text = f"{left}d" if left is not None else "\u2014"
            at_risk = risk_for(batch)
            risk_cell = (
                chip_cell(t("expiry.at_risk_qty", qty=f"{at_risk:g}"), "at_risk")
                if at_risk > 0
                else text_cell("0", color=T.TEXT_TERTIARY)
            )
            rows.append(ft.DataRow(cells=[
                text_cell(name),
                text_cell(batch.batch_code or f"#{batch.id}", color=T.TEXT_SECONDARY),
                text_cell(batch.expiry_date or "\u2014", color=T.TEXT_SECONDARY),
                text_cell(left_text, color=T.TEXT_SECONDARY),
                text_cell(f"{batch.quantity_remaining:g}"),
                risk_cell,
                text_cell(format_money((batch.unit_cost or Decimal("0")) * Decimal(str(batch.quantity_remaining))),
                          color=T.TEXT_SECONDARY),
                chip_cell(label, status),
                action_cell(lambda e, b=batch, p=product: _open_waste(page, navigate, b, p),
                            icon=ft.Icons.DELETE_OUTLINE, tooltip=t("action.record_waste")),
            ]))
        return rows

    expiring_panel = section(
        t("panel.expiring_window", days=window),
        styled_table([t("col.product"), t("col.batch"), t("col.expiry"), t("col.days_left"),
                      t("col.remaining"), t("col.at_risk"), t("col.value"), t("field.status"), ""],
                     build_rows(expiring, expired_rows=False),
                     empty_message=t("empty.no_expiring_body")),
        subtitle=t("note.fefo"),
    )
    expired_panel = section(
        t("metric.already_expired"),
        styled_table([t("col.product"), t("col.batch"), t("col.expiry"), t("col.days_over"),
                      t("col.remaining"), t("col.at_risk"), t("col.value"), t("field.status"), ""],
                     build_rows(expired, expired_rows=True),
                     empty_message=t("empty.no_expired")),
        subtitle=t("note.write_off"),
    )

    units_expiring = sum(b.quantity_remaining for b in expiring)
    units_expired = sum(b.quantity_remaining for b in expired)
    value_at_risk = sum(
        risk_for(b) * float(b.unit_cost or 0) for b in (expiring + expired)
    )

    kpis = kpi_strip([
        KpiMetric(t("metric.batches_expiring"), str(len(expiring)), icon=ft.Icons.EVENT_BUSY_OUTLINED,
                  accent=T.STATUS_WARNING, caption=t("cap.within_days", days=window),
                  delta_kind="warn" if expiring else "muted"),
        KpiMetric(t("metric.units_expiring"), f"{units_expiring:g}", icon=ft.Icons.INVENTORY_2_OUTLINED,
                  accent=T.STATUS_WARNING, caption=t("cap.still_usable")),
        KpiMetric(t("metric.value_at_risk"), format_money(value_at_risk),
                  icon=ft.Icons.CURRENCY_RUPEE, accent=T.STATUS_CRITICAL,
                  caption=t("cap.likely_unrealised")),
        KpiMetric(t("metric.already_expired"), f"{units_expired:g} units",
                  icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                  accent=T.STATUS_CRITICAL if units_expired else T.STATUS_HEALTHY,
                  caption=t("cap.not_sellable"),
                  delta_kind="down" if units_expired else "muted"),
    ])

    header = page_header(
        t("nav.expiry"),
        t("expiry.summary", batches=len(expiring), expired=len(expired),
                                units=units_expiring + units_expired),
        actions=[ft.OutlinedButton(content=t("action.refresh"), icon=ft.Icons.REFRESH,
                                   on_click=lambda e: navigate("/expiry"))],
    )

    if not expiring and not expired:
        return scroll_column([
            header,
            kpis,
            empty_state(t("empty.no_expiring"), "No batches are near or past their expiry date.",
                        icon=ft.Icons.EVENT_AVAILABLE_OUTLINED),
        ])

    return scroll_column([header, kpis, expiring_panel, expired_panel])


def _open_waste(page: ft.Page, navigate: Callable[[str], None], batch, product) -> None:
    app = app_context
    quantity = text_field(t("field.quantity_waste"), value=f"{batch.quantity_remaining:g}")
    reason = text_field(t("field.reason_waste"), value=t("status.expired"))
    product_name = product.name if product else f"Product {batch.product_id}"

    def save(e) -> None:
        try:
            app.inventory_service.record_waste(
                batch.product_id, float((quantity.value or "").strip() or 0),
                reason=(reason.value or "").strip(), batch_id=batch.id,
            )
            page.pop_dialog()
            notify(page, t("toast.waste_recorded"), "success")
            navigate("/expiry")
        except (StockWiseError, ValueError) as exc:
            notify_error(page, exc)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"Write off \u2014 {product_name}"),
        content=ft.Container(width=380, content=ft.Column(tight=True, spacing=T.GAP_SMALL,
                                                         controls=[quantity, reason])),
        actions=[
            ft.TextButton(content=t("action.cancel"), on_click=lambda e: page.pop_dialog()),
            ft.Button(content=t("action.record_waste"), on_click=save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)
