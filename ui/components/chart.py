"""StockWise — lightweight, dependency-free chart helpers.

Flet 1.0 ships no chart controls and no canvas, so charts are composed from plain
themed ``Container`` slices. They stay sharp at any width, follow the active
palette, and render identically in the desktop and web views.

``area_chart`` draws an interpolated area + line (optionally with a confidence
band and a history→forecast colour split); ``bar_chart`` remains for compact
per-day breakdowns.
"""

from __future__ import annotations

from typing import Callable, Sequence

import flet as ft

from app.theme import StockWiseTheme as T

_GRID_LINES = 4
_SUBSLICES = 4  # interpolation steps between two data points


def _short(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1000:
        return f"{value / 1000:.1f}k"
    if abs(value) >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


def _interpolate(values: Sequence[float], steps: int) -> list[float]:
    """Linear interpolation to ``(len(values) - 1) * steps + 1`` points."""
    if len(values) <= 1:
        return [float(values[0])] if values else []
    out: list[float] = []
    for i in range(len(values) - 1):
        a, b = float(values[i]), float(values[i + 1])
        for s in range(steps):
            out.append(a + (b - a) * (s / steps))
    out.append(float(values[-1]))
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
    smooth = _interpolate(values, _SUBSLICES)
    smooth_upper = _interpolate(upper_values, _SUBSLICES) if upper_values else None

    peak = max(smooth) if smooth else 1.0
    if smooth_upper:
        peak = max(peak, max(smooth_upper))
    peak = peak * 1.15 if peak > 0 else 1.0

    plot_height = height  # the whole plot area; labels are drawn in side columns

    def _in_forecast(index: int) -> bool:
        return forecast_from is not None and index >= forecast_from * _SUBSLICES

    slices: list[ft.Control] = []
    for i, value in enumerate(smooth):
        line_px = max(2, int(plot_height * (value / peak)))
        bar_color = forecast_line_color if _in_forecast(i) else line_color
        bar_fill = (
            ft.Colors.with_opacity(0.20, bar_color) if _in_forecast(i) else fill_color
        )
        controls: list[ft.Control] = [ft.Container(expand=True)]
        if smooth_upper is not None and _in_forecast(i):
            band_px = int(plot_height * ((smooth_upper[i] - value) / peak))
            if band_px > 0:
                controls.append(ft.Container(height=band_px, bgcolor=band_color))
        controls.append(
            ft.Container(
                height=line_px,
                bgcolor=bar_fill,
                border=ft.Border.only(top=ft.BorderSide(2, bar_color)),
            )
        )
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
