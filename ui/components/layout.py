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
        controls=[
            ft.Text(title, size=T.FONT_HERO, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
        ],
    )
    if subtitle:
        left.controls.append(ft.Text(subtitle, size=T.FONT_SMALL, color=T.TEXT_SECONDARY))

    controls: list[ft.Control] = [left]
    if actions:
        controls.append(
            ft.Row(spacing=T.GAP_SMALL, controls=actions, tight=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER)
        )
    return ft.Container(
        padding=ft.Padding.only(bottom=T.GAP),
        content=ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=controls),
    )


def card(
    content: ft.Control,
    *,
    padding: int | None = None,
    expand: bool = False,
    width: int | None = None,
) -> ft.Control:
    """A themed surface card (white in light mode) with a soft shadow."""
    return ft.Container(
        content=content,
        padding=padding if padding is not None else T.CARD_PADDING,
        bgcolor=T.BG_CARD,
        border_radius=T.RADIUS,
        border=ft.Border.all(1, T.BORDER_SUBTLE),
        shadow=T.shadow(),
        expand=expand,
        width=width,
    )


def section(
    title: str,
    content: ft.Control,
    *,
    subtitle: Optional[str | ft.Control] = None,
    actions: Optional[list[ft.Control]] = None,
    expand: bool = False,
    height: int | None = None,
) -> ft.Control:
    """A titled card section. ``subtitle`` may be text or a live control."""
    if subtitle is None:
        subtitle_control: Optional[ft.Control] = None
    elif isinstance(subtitle, str):
        subtitle_control = ft.Text(subtitle, size=T.FONT_TINY, color=T.TEXT_TERTIARY)
    else:
        subtitle_control = subtitle
    heading_controls: list[ft.Control] = [
        ft.Column(
            spacing=1,
            expand=True,
            controls=[
                ft.Text(title, size=T.FONT_SUBTITLE, weight=ft.FontWeight.W_600, color=T.TEXT_PRIMARY),
                *([subtitle_control] if subtitle_control is not None else []),
            ],
        )
    ]
    if actions:
        heading_controls.append(
            ft.Row(spacing=T.GAP_SMALL, controls=actions, tight=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER)
        )

    body = ft.Column(
        spacing=T.GAP,
        controls=[
            ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=heading_controls),
            content,
        ],
    )
    if height is None:
        return card(body, expand=expand)
    return ft.Container(
        content=body, height=height, padding=T.CARD_PADDING, bgcolor=T.BG_CARD,
        border_radius=T.RADIUS, border=ft.Border.all(1, T.BORDER_SUBTLE),
        shadow=T.shadow(), expand=expand,
    )


def list_row(
    *,
    leading: Optional[ft.Control] = None,
    title: str,
    subtitle: Optional[str] = None,
    trailing: Optional[ft.Control] = None,
    on_click: Optional[Callable] = None,
) -> ft.Control:
    """A padded, hover-highlighted row used by alert / activity lists."""
    controls: list[ft.Control] = []
    if leading is not None:
        controls.append(leading)
    controls.append(
        ft.Column(
            spacing=1,
            expand=True,
            controls=[
                ft.Text(title, size=T.FONT_BODY, color=T.TEXT_PRIMARY, weight=ft.FontWeight.W_500),
                *([ft.Text(subtitle, size=T.FONT_TINY, color=T.TEXT_TERTIARY)] if subtitle else []),
            ],
        )
    )
    if trailing is not None:
        controls.append(trailing)
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=9),
        border_radius=T.RADIUS_SMALL,
        ink=on_click is not None,
        on_click=on_click,
        content=ft.Row(spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=controls),
    )


def icon_tile(icon: str, *, color: str, bgcolor: str | None = None, size: int = 40) -> ft.Control:
    """A rounded pastel icon tile (the small square icon used across the mockups)."""
    return ft.Container(
        width=size,
        height=size,
        border_radius=T.RADIUS_SMALL,
        bgcolor=bgcolor or ft.Colors.with_opacity(0.14, color),
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(icon, size=int(size * 0.5), color=color),
    )


def scroll_column(controls: list[ft.Control], *, spacing: int = T.GAP) -> ft.Column:
    """A vertically scrolling column that fills its parent."""
    return ft.Column(controls=controls, spacing=spacing, scroll=ft.ScrollMode.AUTO, expand=True)


# KPI cards reflow to fit narrow windows: 1 per row, then 2, then 4 on wide desktops.
KPI_BREAKPOINTS = {"xs": 0, "sm": 340, "lg": 1040}
KPI_COL = {"xs": 12, "sm": 6, "lg": 3}
KPI_COL_THREE = {"xs": 12, "sm": 6, "lg": 4}


def kpi_grid(cards: list[ft.Control]) -> ft.Control:
    """Lay KPI cards out so they wrap instead of being squeezed."""
    return ft.ResponsiveRow(
        controls=cards,
        spacing=T.GAP,
        run_spacing=T.GAP,
        breakpoints=dict(KPI_BREAKPOINTS),
    )


# Wide panels sit side by side on a desktop and stack on a narrow window.
PANEL_BREAKPOINTS = {"xs": 0, "lg": 1040}

# Filter/field rows: stack in narrow windows, share a line on wide desktops.
FILTER_BREAKPOINTS = {"xs": 0, "sm": 340, "lg": 1040}


def panel_grid(panels: list[tuple[ft.Control, int]]) -> ft.Control:
    """Arrange ``(control, span)`` pairs side by side, stacking when narrow.

    ``span`` is the number of a 12-column grid the panel occupies from the
    ``lg`` breakpoint up.
    """
    controls = [
        ft.Container(content=control, col={"xs": 12, "lg": span})
        for control, span in panels
    ]
    return ft.ResponsiveRow(
        controls=controls,
        spacing=T.GAP,
        run_spacing=T.GAP,
        breakpoints=dict(PANEL_BREAKPOINTS),
    )


def flow_row(
    items: list[ft.Control | tuple[ft.Control, dict]],
    *,
    col: dict | None = None,
    spacing: int | None = None,
) -> ft.Control:
    """A row of controls that flows onto the next line instead of overflowing.

    ``items`` is a list of controls, or ``(control, col)`` pairs to give an item
    its own grid span. Wrapping uses ``ResponsiveRow`` because ``ft.Row(wrap=True)``
    renders as a blank grey block in Flet 1.0.
    """
    default_col = col or {"xs": 12, "sm": 6, "lg": 3}
    wrapped: list[ft.Control] = []
    for item in items:
        control, item_col = item if isinstance(item, tuple) else (item, default_col)
        wrapped.append(ft.Container(content=control, col=item_col))
    gap = T.GAP_SMALL if spacing is None else spacing
    return ft.ResponsiveRow(
        controls=wrapped,
        spacing=gap,
        run_spacing=gap,
        breakpoints=dict(FILTER_BREAKPOINTS),
    )


def money_text(value, *, size: int = T.FONT_BODY, color: str | None = None,
               weight: ft.FontWeight | None = None) -> ft.Text:
    from domain.money import format_money

    return ft.Text(
        format_money(value), size=size, color=color or T.TEXT_PRIMARY, weight=weight,
    )
