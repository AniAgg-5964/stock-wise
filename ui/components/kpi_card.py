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
from app.viewport import StockWiseViewport

#: Text width available to a metric value once four sit across. Derived from a
#: 1240px window: 1240 - sidebar 248 - 2*content padding 28 = 936 of content,
#: less 3 gaps of 18 leaves 882/4 = 220 per cell, less strip padding 2*18 and
#: cell padding 2*10 -> ~164.
_VALUE_BUDGET_PX = 164
#: Average glyph advance for Mukta, as a fraction of the font size.
_ADVANCE_RATIO = 0.52

_STRIP_PADDING = 18
_CELL_PADDING = 10

#: Content width at which four metrics fit that budget. Derived rather than
#: guessed, so the threshold cannot drift away from ``_VALUE_BUDGET_PX``: each
#: cell needs the budget plus its own padding plus the strip's padding, and four
#: cells plus three gaps have to fit. = 4 * (164+20+18) + 3*18 = 934.
#:
#: This is a *content* width, and that is the whole point. It used to be a
#: ``ResponsiveRow`` breakpoint of 1240, which the Flet docs never define as
#: either a page or a container width. Under Flutter's container-relative
#: evaluation that meant four-across only engaged at a ~1544px window, so a 1366
#: or 1440 laptop — what most shops have — never got it. The shell now measures
#: the viewport (``app.viewport``) and passes the real number.
KPI_FOUR_UP_WIDTH = 4 * (_VALUE_BUDGET_PX + 2 * _CELL_PADDING + 2 * _STRIP_PADDING) \
    + 3 * T.GAP


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


def _span_for(count: int, *, width: int | None) -> int:
    """Columns each metric occupies on the 12-column grid.

    ``width`` is the measured content width, or ``None`` when the shell has not
    reported one yet. ``None`` is treated as a normal desktop window rather than
    as zero, so the first paint before any resize event looks like every window
    after it.
    """
    if count <= 1:
        return 12
    if width is not None and width < KPI_FOUR_UP_WIDTH:
        return 6  # deliberate 2x2, never four clipped cells
    if count == 2:
        return 6
    if count == 3:
        return 4
    return 3


def _metric_cell(metric: KpiMetric, span: int) -> ft.Control:
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
        col=span,
        padding=ft.Padding.symmetric(horizontal=_CELL_PADDING, vertical=2),
        on_click=metric.on_click,
        ink=metric.on_click is not None,
        content=ft.Column(spacing=2, controls=controls),
    )


def kpi_strip(
    metrics: list[KpiMetric],
    *,
    padding: int | None = None,
    available_width: int | None = None,
) -> ft.Control:
    """One panel holding every headline metric, reflowing as the window narrows.

    ``available_width`` is the measured content width; when it is omitted the
    value published by ``app.viewport`` is used. The span is then decided in
    Python against that number, so the layout does not depend on how Flet
    resolves ``ResponsiveRow`` breakpoints.
    """
    if not metrics:
        return ft.Container(height=0)

    width = available_width if available_width is not None else StockWiseViewport.get()
    span = _span_for(len(metrics), width=width)
    row = ft.ResponsiveRow(
        controls=[_metric_cell(m, span) for m in metrics],
        spacing=T.GAP,
        run_spacing=T.GAP_SMALL,
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