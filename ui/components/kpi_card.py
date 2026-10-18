"""StockWise — KPI card component.

A compact metric card used across the dashboard and detail screens. Values must
always come from real data (database/services) — never fabricated.

**Layout.** The icon sits beside the *label* rather than beside the number. That
is not just a look: on a 1366px window a 4-up row leaves roughly 208px of text
width per card, and Indian currency amounts reach six digits (``₹1,23,456.00``).
With a 40px tile parked next to the number, that same value no longer fits at
any display size. Stacking the card instead gives the number the full width and
reads more like the impact cards a shopkeeper is used to.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T

#: Width the value text actually gets in a 4-up row on the smallest supported
#: window (1366px): 1366 - sidebar 248 - 2*content padding 28 - 3*grid gap 18
#: - 2*card padding 22 = 208px. The icon sits on the label row precisely so the
#: value keeps this whole width.
_VALUE_BUDGET_PX = 208
#: Average glyph advance for Mukta, as a fraction of the font size.
_ADVANCE_RATIO = 0.55


def _value_size(value: str) -> int:
    """Pick a display size that keeps long values (e.g. money) on one line.

    Steps down with the string length rather than trusting every value to fit
    ``_VALUE_BUDGET_PX``.
    """
    length = len(value)
    if length <= 10:
        return T.FONT_DISPLAY
    if length <= 13:
        return T.FONT_DISPLAY - 5
    if length <= 16:
        return T.FONT_DISPLAY - 9
    if length <= 20:
        return T.FONT_DISPLAY - 12
    return T.FONT_DISPLAY - 14


def value_fits(value: str) -> bool:
    """Whether ``value`` renders on one line inside a 4-up KPI card."""
    return len(value) * _value_size(value) * _ADVANCE_RATIO <= _VALUE_BUDGET_PX


def kpi_card(
    title: str,
    value: str,
    *,
    subtitle: Optional[str] = None,
    icon: str = ft.Icons.ANALYTICS_OUTLINED,
    accent: str | None = None,
    on_click: Optional[Callable] = None,
    delta: Optional[str] = None,
    delta_kind: str = "muted",
    col=None,
) -> ft.Control:
    """Build a single KPI card: labelled icon, large value, optional caption.

    Pass ``col`` when placing cards in a ``ResponsiveRow`` so they reflow.
    """
    accent = accent or T.PRIMARY
    caption = delta if delta is not None else subtitle
    caption_color = {
        "up": T.STATUS_HEALTHY,
        "down": T.STATUS_CRITICAL,
        "info": T.STATUS_INFO,
        "warn": T.STATUS_WARNING,
        "muted": T.TEXT_TERTIARY,
    }.get(delta_kind, T.TEXT_TERTIARY)

    controls: list[ft.Control] = [
        ft.Row(
            spacing=7,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(icon, size=15, color=accent),
                ft.Text(
                    title,
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
        # ``no_wrap`` keeps money values such as ₹29,209.00 on a single line; the
        # size steps down for longer strings so they still fit the card.
        ft.Text(
            value,
            size=_value_size(value),
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
                size=T.FONT_SMALL,
                color=caption_color,
                weight=ft.FontWeight.W_500,
                no_wrap=True,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )

    return ft.Container(
        expand=col is None,
        col=col,
        padding=ft.Padding.symmetric(horizontal=T.CARD_PADDING, vertical=18),
        bgcolor=T.BG_CARD,
        border_radius=T.RADIUS,
        border=ft.Border.all(1, T.BORDER_SUBTLE),
        shadow=T.shadow(),
        on_click=on_click,
        ink=on_click is not None,
        content=ft.Column(spacing=4, controls=controls),
    )
