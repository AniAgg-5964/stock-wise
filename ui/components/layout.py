"""StockWise — layout helpers (page headers, cards, sections).

Keeps spacing/typography consistent across views without repeating styling code.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T


def page_header(
    title: str,
    subtitle: Optional[str] = None,
    actions: Optional[list[ft.Control]] = None,
) -> ft.Control:
    """Standard page header (title + optional subtitle + right-aligned actions)."""
    left = ft.Column(
        spacing=2,
        expand=True,
        controls=[ft.Text(title, size=T.FONT_TITLE, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY)],
    )
    if subtitle:
        left.controls.append(ft.Text(subtitle, size=T.FONT_SMALL, color=T.TEXT_SECONDARY))

    controls: list[ft.Control] = [left]
    if actions:
        controls.append(ft.Row(spacing=T.GAP_SMALL, controls=actions, tight=True))
    return ft.Container(
        padding=ft.Padding.only(bottom=T.GAP),
        content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=controls),
    )


def card(content: ft.Control, *, padding: int | None = None, expand: bool = False,
         width: int | None = None) -> ft.Control:
    """A themed surface container."""
    return ft.Container(
        content=content,
        padding=padding if padding is not None else T.CARD_PADDING,
        bgcolor=T.BG_CARD,
        border_radius=T.RADIUS,
        border=ft.Border.all(1, T.BORDER_SUBTLE),
        expand=expand,
        width=width,
    )


def section(
    title: str,
    content: ft.Control,
    *,
    subtitle: Optional[str] = None,
    actions: Optional[list[ft.Control]] = None,
    expand: bool = False,
    height: int | None = None,
) -> ft.Control:
    """A titled card section."""
    heading_controls: list[ft.Control] = [
        ft.Column(
            spacing=1,
            expand=True,
            controls=[
                ft.Text(title, size=T.FONT_SUBTITLE, weight=ft.FontWeight.W_600, color=T.TEXT_PRIMARY),
                *( [ft.Text(subtitle, size=T.FONT_TINY, color=T.TEXT_TERTIARY)] if subtitle else [] ),
            ],
        )
    ]
    if actions:
        heading_controls.append(ft.Row(spacing=T.GAP_SMALL, controls=actions, tight=True))

    body = ft.Column(
        spacing=T.GAP,
        controls=[
            ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=heading_controls),
            content,
        ],
    )
    return card(body, expand=expand) if height is None else ft.Container(
        content=body, height=height, padding=T.CARD_PADDING, bgcolor=T.BG_CARD,
        border_radius=T.RADIUS, border=ft.Border.all(1, T.BORDER_SUBTLE), expand=expand,
    )


def scroll_column(controls: list[ft.Control], *, spacing: int = T.GAP) -> ft.Column:
    """A vertically scrolling column that fills its parent."""
    return ft.Column(controls=controls, spacing=spacing, scroll=ft.ScrollMode.AUTO, expand=True)


def money_text(value, *, size: int = T.FONT_BODY, color: str | None = None,
               weight: ft.FontWeight | None = None) -> ft.Text:
    from domain.money import format_money

    return ft.Text(
        format_money(value), size=size, color=color or T.TEXT_PRIMARY, weight=weight,
    )
