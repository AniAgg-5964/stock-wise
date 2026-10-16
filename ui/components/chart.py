"""StockWise — lightweight chart helpers.

Deliberately dependency-free: bars are plain themed ``Container``s so the chart
renders identically in the desktop and web Flet views without a charting plugin.
"""

from __future__ import annotations

from typing import Sequence

import flet as ft

from app.theme import StockWiseTheme as T


def _short(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    if value >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


def bar_chart(
    values: Sequence[float],
    labels: Sequence[str] | None = None,
    *,
    height: int = 190,
    accent: str = T.PRIMARY,
    forecast_from: int | None = None,
    forecast_accent: str = T.ACCENT,
    empty_message: str = "No data to chart",
) -> ft.Control:
    """A simple vertical bar chart.

    Bars before ``forecast_from`` use ``accent``; from that index onward they use
    ``forecast_accent`` (used to distinguish history from forecast).
    """
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
                            border_radius=ft.BorderRadius.only(top_left=4, top_right=4),
                            bgcolor=forecast_accent if is_forecast else accent,
                        ),
                        ft.Text(labels[i] if i < len(labels) else "", size=T.FONT_TINY,
                                color=T.TEXT_TERTIARY, text_align=ft.TextAlign.CENTER),
                    ],
                ),
            )
        )

    return ft.Row(spacing=2, controls=cells, vertical_alignment=ft.CrossAxisAlignment.END)


def chart_legend(items: Sequence[tuple[str, str]]) -> ft.Control:
    """A small legend: ``(label, colour)`` pairs."""
    return ft.Row(
        spacing=T.GAP,
        tight=True,
        controls=[
            ft.Row(
                spacing=6,
                tight=True,
                controls=[
                    ft.Container(width=10, height=10, border_radius=3, bgcolor=color),
                    ft.Text(label, size=T.FONT_TINY, color=T.TEXT_SECONDARY),
                ],
            )
            for label, color in items
        ],
    )
