"""StockWise — lightweight, dependency-free chart helpers.

Flet 1.0 ships no chart controls and no canvas, so charts are composed from plain
themed ``Container`` slices. They stay sharp at any width, follow the active
palette, and render identically in the desktop and web views.

``area_chart`` draws an interpolated area + line (optionally with a confidence
band and a history→forecast colour split); ``bar_chart`` remains for compact
per-day breakdowns.

**How the curve stays smooth.** Each slice is a column whose height is the curve's
value at that x, rounded to whole pixels, and slices sit side by side with no gap.
Two earlier choices made the line look broken: linear interpolation between points
showed the corners as hard steps, and drawing a border on the top of *every* slice
put a notch at each column boundary. So the curve is sampled with a Catmull-Rom
spline instead - neighbours then differ by a few pixels at most, which reads as a
slope rather than a step - and the line is a single constant-thickness ribbon laid
over the fill rather than a per-slice border.
"""

from __future__ import annotations

from typing import Callable, Sequence

import flet as ft

from app.theme import StockWiseTheme as T

_GRID_LINES = 4
_LINE_THICKNESS = 3
#: Cap on rendered slices. Each slice is ~3 Flet controls, so this is the knob
#: that keeps a long history from turning the dashboard into a control tree of
#: several thousand nodes.
_MAX_SLICES = 220
_MIN_STEPS_PER_SEGMENT = 1
_MAX_STEPS_PER_SEGMENT = 48


def _short(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1000:
        return f"{value / 1000:.1f}k"
    if abs(value) >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


def _sample_steps(count: int) -> int:
    """Samples to place between each pair of data points.

    Chosen so the *total* number of rendered slices stays near ``_MAX_SLICES``
    however long the series is: a fixed sample count would be smooth for a
    21-point chart and ruinous for a 400-point one, since every slice is a
    handful of Flutter controls and the chart is rebuilt on each dashboard render.

    A series longer than the cap simply gets one column per data point - it
    cannot be drawn with fewer columns than it has points.
    """
    segments = count - 1
    if segments <= 0:
        return 1
    steps = round((_MAX_SLICES - 1) / segments)
    return max(_MIN_STEPS_PER_SEGMENT, min(_MAX_STEPS_PER_SEGMENT, steps))


def _curve_pixels(smooth: Sequence[float], plot_height: int, peak: float) -> list[int]:
    """Column height in whole pixels for each sampled point on the curve.

    Kept separate from the control building so the *geometry* can be tested
    directly: smoothness is a property of these numbers, and asserting on the
    Flet control tree instead would only prove the tree was built, not that the
    curve is continuous.
    """
    if peak <= 0:
        return [1] * len(smooth)
    return [max(1, int(round(plot_height * (value / peak)))) for value in smooth]


def _interpolate(values: Sequence[float], steps: int) -> list[float]:
    """Sample a Catmull-Rom spline through ``values``, endpoints held flat.

    Linear interpolation rendered every corner as a visible step. Catmull-Rom
    passes smoothly through each point and, with the first and last control
    points mirrored, leaves the curve flat where the data starts and ends instead
    of shooting off past the ends.
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [float(values[0])]

    pts = [float(v) for v in values]
    padded = [pts[0]] + pts + [pts[-1]]
    out: list[float] = []
    for i in range(n - 1):
        p0, p1, p2, p3 = padded[i], padded[i + 1], padded[i + 2], padded[i + 3]
        # Skip the duplicate first sample of every segment except the first.
        for s in range(steps + 1):
            if i > 0 and s == 0:
                continue
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(0.5 * (
                2 * p1
                + (-p0 + p2) * t
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
            ))
    return out


def _pick_labels(labels: Sequence[str], limit: int = 8) -> list[str]:
    if not labels:
        return []
    if len(labels) <= limit:
        return list(labels)
    step = max(1, round(len(labels) / limit))
    picked = list(labels[::step])
    if picked[-1] != labels[-1]:
        picked[-1] = labels[-1]
    return picked


def area_chart(
    values: Sequence[float],
    labels: Sequence[str] | None = None,
    *,
    height: int = 200,
    forecast_from: int | None = None,
    line_color: str | None = None,
    fill_color: str | None = None,
    forecast_line_color: str | None = None,
    upper: Sequence[float] | None = None,
    band_color: str | None = None,
    empty_message: str = "No data to chart",
    value_formatter: Callable[[float], str] | None = None,
) -> ft.Control:
    """An area + line chart with optional forecast split and confidence band."""
    values = [max(0.0, float(v)) for v in values]
    if not values:
        return ft.Container(
            height=height,
            alignment=ft.Alignment.CENTER,
            content=ft.Text(empty_message, size=T.FONT_SMALL, color=T.TEXT_TERTIARY),
        )

    line_color = line_color or T.PRIMARY
    fill_color = fill_color or ft.Colors.with_opacity(0.18, line_color)
    forecast_line_color = forecast_line_color or T.ACCENT
    band_color = band_color or ft.Colors.with_opacity(0.12, forecast_line_color)
    y_fmt = value_formatter or _short

    upper_values = [max(0.0, float(u)) for u in upper] if upper else None
    steps = _sample_steps(len(values))
    smooth = _interpolate(values, steps)
    smooth_upper = _interpolate(upper_values, steps) if upper_values else None

    peak = max(smooth) if smooth else 1.0
    if smooth_upper:
        peak = max(peak, max(smooth_upper))
    peak = peak * 1.15 if peak > 0 else 1.0

    plot_height = height  # the whole plot area; labels are drawn in side columns
    line_pixels = _curve_pixels(smooth, plot_height, peak)

    def _in_forecast(index: int) -> bool:
        # Each segment contributes exactly ``steps`` samples (the shared endpoint
        # is only emitted once), so this lands on the real data point.
        return forecast_from is not None and index >= forecast_from * steps

    slices: list[ft.Control] = []
    for i, value in enumerate(smooth):
        line_px = line_pixels[i]
        in_forecast = _in_forecast(i)
        bar_color = forecast_line_color if in_forecast else line_color
        bar_fill = ft.Colors.with_opacity(0.22, bar_color) if in_forecast else fill_color

        # Stack the band, then the fill, then a constant-thickness line ribbon on
        # top. The ribbon is what makes the curve read as one continuous line: a
        # border on each slice instead would notch the top edge at every column.
        controls: list[ft.Control] = [ft.Container(expand=True)]
        if smooth_upper is not None and in_forecast:
            band_px = int(plot_height * ((smooth_upper[i] - value) / peak))
            if band_px > 0:
                controls.append(
                    ft.Container(
                        height=band_px,
                        bgcolor=band_color,
                        border_radius=ft.BorderRadius.only(top_left=3, top_right=3),
                    )
                )
        fill_px = max(0, line_px - _LINE_THICKNESS)
        controls.append(
            ft.Container(
                height=fill_px,
                bgcolor=bar_fill,
                border_radius=(
                    ft.BorderRadius.only(top_left=3, top_right=3) if fill_px > 0 else None
                ),
            )
        )
        controls.append(ft.Container(height=_LINE_THICKNESS, bgcolor=bar_color))
        slices.append(
            ft.Container(
                expand=True,
                content=ft.Column(
                    spacing=0,
                    alignment=ft.MainAxisAlignment.END,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=controls,
                ),
            )
        )

    grid = ft.Container(
        top=0, left=0, right=0, bottom=0,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            spacing=0,
            controls=[
                ft.Container(height=1, bgcolor=T.BORDER_SUBTLE) for _ in range(_GRID_LINES + 1)
            ],
        ),
    )
    plot = ft.Container(
        top=0, left=0, right=0, bottom=0,
        content=ft.Row(spacing=0, controls=slices, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
    )

    y_axis = ft.Column(
        width=46,
        height=plot_height,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        horizontal_alignment=ft.CrossAxisAlignment.END,
        spacing=0,
        controls=[
            ft.Text(y_fmt(peak * (1 - i / _GRID_LINES)), size=T.FONT_TINY,
                    color=T.TEXT_TERTIARY, text_align=ft.TextAlign.RIGHT)
            for i in range(_GRID_LINES + 1)
        ],
    )

    body = ft.Row(
        spacing=T.GAP_SMALL,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[y_axis, ft.Stack(controls=[grid, plot], height=plot_height, expand=True)],
    )

    children: list[ft.Control] = [body]
    picked = _pick_labels(labels or [], limit=8)
    if picked:
        children.append(
            ft.Container(
                padding=ft.Padding.only(left=54),
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[ft.Text(lbl, size=T.FONT_TINY, color=T.TEXT_TERTIARY) for lbl in picked],
                ),
            )
        )

    return ft.Column(spacing=T.GAP_TINY, controls=children)


def bar_chart(
    values: Sequence[float],
    labels: Sequence[str] | None = None,
    *,
    height: int = 190,
    accent: str | None = None,
    forecast_from: int | None = None,
    forecast_accent: str | None = None,
    empty_message: str = "No data to chart",
) -> ft.Control:
    """A simple vertical bar chart (history vs forecast colour split)."""
    accent = accent or T.PRIMARY
    forecast_accent = forecast_accent or T.ACCENT
    values = [float(v) for v in values]
    if not values:
        return ft.Container(
            height=height,
            alignment=ft.Alignment.CENTER,
            content=ft.Text(empty_message, size=T.FONT_SMALL, color=T.TEXT_TERTIARY),
        )

    labels = list(labels or [""] * len(values))
    peak = max([abs(v) for v in values] + [0.5])
    bar_area = height - 34  # leave room for the value + day labels

    cells: list[ft.Control] = []
    for i, value in enumerate(values):
        is_forecast = forecast_from is not None and i >= forecast_from
        bar_h = max(3, int(bar_area * (value / peak))) if value > 0 else 3
        cells.append(
            ft.Container(
                expand=True,
                height=height,
                padding=ft.Padding.symmetric(horizontal=2),
                content=ft.Column(
                    spacing=2,
                    alignment=ft.MainAxisAlignment.END,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Text(_short(value), size=T.FONT_TINY, color=T.TEXT_TERTIARY,
                                text_align=ft.TextAlign.CENTER),
                        ft.Container(
                            height=bar_h,
                            border_radius=ft.BorderRadius.only(top_left=6, top_right=6),
                            bgcolor=ft.Colors.with_opacity(0.55, forecast_accent if is_forecast else accent),
                            border=ft.Border.only(
                                top=ft.BorderSide(2, forecast_accent if is_forecast else accent)
                            ),
                        ),
                        ft.Text(labels[i] if i < len(labels) else "", size=T.FONT_TINY,
                                color=T.TEXT_TERTIARY, text_align=ft.TextAlign.CENTER),
                    ],
                ),
            )
        )

    return ft.Row(spacing=2, controls=cells, vertical_alignment=ft.CrossAxisAlignment.END)


def chart_legend(items: Sequence[tuple[str, str]], *, dashed: Sequence[str] | None = None) -> ft.Control:
    """A small legend: ``(label, colour)`` pairs; ``dashed`` marks dashed entries."""
    dashed = set(dashed or ())
    entries: list[ft.Control] = []
    for label, color in items:
        if label in dashed:
            swatch = ft.Row(
                spacing=2, tight=True,
                controls=[
                    ft.Container(width=5, height=3, border_radius=2, bgcolor=color),
                    ft.Container(width=5, height=3, border_radius=2, bgcolor=color),
                ],
            )
        else:
            swatch = ft.Container(width=12, height=3, border_radius=2, bgcolor=color)
        entries.append(
            ft.Row(spacing=6, tight=True, controls=[
                swatch,
                ft.Text(label, size=T.FONT_TINY, color=T.TEXT_SECONDARY),
            ])
        )
    return ft.Row(spacing=T.GAP, tight=True, controls=entries)
