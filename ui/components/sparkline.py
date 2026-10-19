"""Compact information graphics.

Flet 1.0 ships no canvas, so — like ``chart.py`` — these are plain themed
containers. What makes them worth having is not decoration: a bare number hides
the thing a shopkeeper actually needs to judge. A meter says *how close* a
product is to its reorder point, and a row of micro-bars says whether next week's
demand is flat or spiky, which a single "55.5" total cannot.

**Neither adds a query.** Every view that uses these already loads the numbers it
renders here, so the graphics cost controls, not database time. That is
deliberate: the navigation work that took the ten-screen tour from 18s to 1s was
easy to give away by asking for per-product demand history to draw 15 sparklines.

**Neither is a surface.** A meter is a track and a fill; a sparkline is a row of
bars. No border, no panel behind it, no radius on the track — the surrounding
card already supplies the edge, and a second one here would break the rule the
whole UI is built on.
"""

from __future__ import annotations

from typing import Sequence

import flet as ft

from app.theme import StockWiseTheme as T

#: A micro-bar chart is a shape, not a chart to read values off, so it is capped
#: well below the 220 slices a full chart allows. Seven days fits comfortably.
_MAX_MICRO_BARS = 12
_MIN_BAR_PX = 2
#: Gap between micro-bars. Fixed rather than a margin so the bar widths can be
#: computed exactly and the whole sparkline fits its declared width.
_BAR_GAP_PX = 2


def _downsample(values: Sequence[float], limit: int) -> list[float]:
    """Reduce to at most ``limit`` bars, keeping peaks.

    Averaging buckets would flatten exactly the spikes a shopkeeper needs to see,
    so each bucket keeps its maximum.
    """
    if len(values) <= limit:
        return [float(v) for v in values]
    step = len(values) / limit
    out: list[float] = []
    for i in range(limit):
        start = int(i * step)
        end = max(start + 1, int((i + 1) * step))
        out.append(max(float(v) for v in values[start:end]))
    return out


def meter(
    value: float,
    maximum: float,
    *,
    color: str,
    width: int = 64,
    height: int = 6,
    track: str | None = None,
) -> ft.Control:
    """A thin horizontal bar showing how full something is.

    ``value`` and ``maximum`` are in the same units — usable stock against the
    reorder point, or days left against the window. Both are clamped, so a bad
    value renders as an over- or under-filled track rather than a bar that
    overflows its cell.

    The fill keeps a visible stub even at zero, because "empty" and "nothing to
    see here" should not look identical.
    """
    try:
        ratio = 0.0 if maximum <= 0 else float(value) / float(maximum)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        ratio = 0.0
    ratio = max(0.0, min(1.0, ratio))
    radius = ft.BorderRadius.all(height / 2)
    return ft.Container(
        width=width,
        height=height,
        border_radius=radius,
        bgcolor=track or ft.Colors.with_opacity(0.12, T.TEXT_TERTIARY),
        content=ft.Container(
            width=max(height, int(round(width * ratio))),
            height=height,
            border_radius=radius,
            bgcolor=color,
        ),
    )


def mini_bars(
    values: Sequence[float],
    *,
    width: int = 68,
    height: int = 20,
    color: str | None = None,
    muted: bool = False,
) -> ft.Control:
    """A compact bar sparkline, sized in whole pixels.

    Returns a fixed-size ``Container`` whose bars have **explicit widths**. Flet 1.0
    lays ``DataTable`` cell content out with unbounded width, and a stretchy row in
    a cell silently renders the whole table blank — so nothing here uses
    ``expand``, and the bar widths are computed from ``width`` instead of being
    flexed to fill it.
    """
    vals = _downsample(values, _MAX_MICRO_BARS)
    bar_color = color or T.PRIMARY
    if muted or not vals:
        return ft.Container(width=width, height=height)

    peak = max(vals)
    scale = True
    if peak <= 0:
        # An all-zero week is information too, but there is no peak to scale
        # against, so every bar takes the floor height instead of dividing by
        # zero. A product with no forecast yet is a normal state, not an error.
        bar_color = ft.Colors.with_opacity(0.18, T.TEXT_TERTIARY)
        scale = False

    count = len(vals)
    gap = _BAR_GAP_PX
    bar_w = max(_MIN_BAR_PX, (width - gap * (count - 1)) // count)

    def _bar_height(v: float) -> int:
        if not scale:
            return _MIN_BAR_PX
        return max(_MIN_BAR_PX, int(round((height - _MIN_BAR_PX) * (v / peak))))

    bars = [
        ft.Container(
            width=bar_w,
            height=_bar_height(v),
            border_radius=ft.BorderRadius.all(1.5),
            bgcolor=bar_color,
        )
        for v in vals
    ]
    return ft.Container(
        width=width,
        height=height,
        alignment=ft.Alignment.CENTER_LEFT,
        content=ft.Row(
            spacing=gap,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=bars,
        ),
    )