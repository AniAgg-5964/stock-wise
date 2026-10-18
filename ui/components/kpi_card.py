"""StockWise — the KPI strip.

Headline metrics shown as **one panel**, not one tile per metric. Four bordered,
shadowed cards across the top of a screen is exactly what made the dashboard read
as a pile of boxes while wasting the most valuable space on it. Here the metrics
sit side by side inside a single surface, separated by whitespace and type — the
one rule that removes a surface rather than restyling it.

When the window is too narrow for four across, the metrics fall into a tidy 2x2
panel. That is a deliberate grid, not two oversized empty tiles, which is the
main reason the fallback is safe.

**Width budget.** A metric's value must fit on one line: it is ``no_wrap``, so an
over-long value is clipped rather than wrapped. On a 1240px window (the point at
which four become ``lg``) a metric cell is about 164px of text width, and Indian
currency amounts reach six digits (``₹1,23,456.00``). ``_value_size`` therefore
steps down with string length and ``value_fits`` guards the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T

#: Where four metrics become a single row. Below this they fall into 2x2. Kept
#: below the 1280px class of laptop, which used to miss the 4-up threshold and
#: render two enormous half-empty tiles.
KPI_BREAKPOINTS = {"xs": 0, "sm": 340, "lg": 1240}

#: Text width available to a metric value at the 4-up threshold:
#: 1240 - sidebar 248 - 2*content padding 28 - 3*gap 18 = 802 / 4 = 200,
#: less card padding 2*18 and cell padding 2*10 -> ~164.
_VALUE_BUDGET_PX = 164
#: Average glyph advance for Mukta, as a fraction of the font size.
_ADVANCE_RATIO = 0.52

_STRIP_PADDING = 18
_CELL_PADDING = 10


def _value_size(value: str) -> int:
    """Pick a display size that keeps long values (e.g. money) on one line."""
    length = len(value)
    if length <= 10:
        return T.FONT_METRIC
    if length <= 13:
        return T.FONT_METRIC - 4
    if length <= 16:
        return T.FONT_METRIC - 9
    if length <= 20:
        return T.FONT_METRIC - 13
    return T.FONT_METRIC - 16


def value_fits(value: str) -> bool:
    """Whether ``value`` renders on one line inside a 4-up metric cell."""
    return len(value) * _value_size(value) * _ADVANCE_RATIO <= _VALUE_BUDGET_PX


@dataclass
class KpiMetric:
    """One headline number. Values must be real — never fabricated."""

    title: str
    value: str
    caption: Optional[str] = None
    icon: str = ft.Icons.ANALYTICS_OUTLINED
    accent: Optional[str] = None
    delta_kind: str = "muted"
    on_click: Optional[Callable] = None
    _col: dict = field(default_factory=dict, repr=False)


_CAPTION_COLOR = {
    "up": "STATUS_HEALTHY",
    "down": "STATUS_CRITICAL",
    "info": "STATUS_INFO",
    "warn": "STATUS_WARNING",
    "muted": "TEXT_TERTIARY",
}


def _span_for(count: int) -> int:
    """Columns each metric occupies on a 12-column grid."""
    if count <= 1:
        return 12
    if count == 2:
        return 6
    if count == 3:
        return 4
    return 3


def _metric_cell(metric: KpiMetric, col: dict) -> ft.Control:
    accent = metric.accent or T.PRIMARY
    caption = metric.caption
    caption_color = getattr(T, _CAPTION_COLOR.get(metric.delta_kind, "TEXT_TERTIARY"))

    controls: list[ft.Control] = [
        ft.Row(
            spacing=6,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(metric.icon, size=14, color=accent),
                ft.Text(
                    metric.title,
                    size=T.FONT_SMALL,
                    color=T.TEXT_SECONDARY,
                    weight=ft.FontWeight.W_500,
                    no_wrap=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                ),
            ],
        ),
        ft.Text(
            metric.value,
            size=_value_size(metric.value),
            weight=ft.FontWeight.W_400,
            color=T.TEXT_PRIMARY,
            font_family=T.FONT_FAMILY_BOLD,
            no_wrap=True,
            max_lines=1,
        ),
    ]
    if caption:
        controls.append(
            ft.Text(
                caption,
                size=T.FONT_TINY,
                color=caption_color,
                weight=ft.FontWeight.W_500,
                no_wrap=True,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )

    # No border, no fill, no radius: the metric is not a surface.
    return ft.Container(
        col=col,
        padding=ft.Padding.symmetric(horizontal=_CELL_PADDING, vertical=2),
        on_click=metric.on_click,
        ink=metric.on_click is not None,
        content=ft.Column(spacing=2, controls=controls),
    )


def kpi_strip(metrics: list[KpiMetric], *, padding: int | None = None) -> ft.Control:
    """One panel holding every headline metric, reflowing as the window narrows."""
    if not metrics:
        return ft.Container(height=0)

    span = _span_for(len(metrics))
    col = {"xs": 12, "sm": 6, "lg": span}
    row = ft.ResponsiveRow(
        controls=[_metric_cell(m, col) for m in metrics],
        spacing=T.GAP,
        run_spacing=T.GAP_SMALL,
        breakpoints=dict(KPI_BREAKPOINTS),
    )
    return ft.Container(
        content=row,
        padding=ft.Padding.symmetric(
            horizontal=padding if padding is not None else _STRIP_PADDING, vertical=14
        ),
        bgcolor=T.BG_CARD,
        border_radius=T.RADIUS,
        border=ft.Border.all(1, T.BORDER),
    )