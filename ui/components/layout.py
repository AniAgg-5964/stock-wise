"""StockWise — layout helpers (page headers, cards, sections).

Keeps spacing and typography consistent across views without repeating styling
code, and owns the app's surface rules: ``card`` is the only surface, it carries a
hairline border and no shadow, and its contents group with ``hairline`` or plain
whitespace rather than with another filled, bordered or rounded box.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T
from app.viewport import StockWiseViewport


def page_header(
    title: str,
    subtitle: Optional[str] = None,
    actions: Optional[list[ft.Control]] = None,
) -> ft.Control:
    """Standard page header (title + optional subtitle + right-aligned actions)."""
    left = ft.Column(
        spacing=3,
        expand=True,
        controls=[
            # Hero title uses the real SemiBold file, not a synthetic bold.
            ft.Text(title, size=T.FONT_HERO, weight=ft.FontWeight.W_400,
                    color=T.TEXT_PRIMARY, font_family=T.FONT_FAMILY_BOLD),
        ],
    )
    if subtitle:
        left.controls.append(ft.Text(subtitle, size=T.FONT_BODY, color=T.TEXT_SECONDARY))

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
    bgcolor: str | None = None,
    radius: int | None = None,
) -> ft.Control:
    """The one surface in the app: a card with a hairline border and no shadow.

    Two edges (a border *and* a shadow) is what made the old UI read as a pile of
    tiles, so the border carries the edge alone. Nothing inside a card should
    draw its own border, fill or radius — group with whitespace or ``hairline``.

    ``bgcolor`` exists for the rare card that should read as a callout (a hero or
    an impact panel) rather than as ordinary content.
    """
    return ft.Container(
        content=content,
        padding=padding if padding is not None else T.CARD_PADDING,
        bgcolor=bgcolor or T.BG_CARD,
        border_radius=radius if radius is not None else T.RADIUS,
        border=ft.Border.all(1, T.BORDER),
        expand=expand,
        width=width,
    )


def hairline(*, inset: int = 0) -> ft.Control:
    """A 1px rule for grouping content *inside* a card.

    Preferred over wrapping the group in another box, which is how the app ended
    up with nine competing surfaces on the dashboard.
    """
    return ft.Container(
        height=1,
        bgcolor=T.BORDER_SUBTLE,
        margin=ft.Margin.symmetric(horizontal=inset),
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
    def _heading_title(text: str, size: int) -> ft.Text:
        # Large headings use the real SemiBold file rather than asking the Regular
        # for a synthetic bold, which looks thin at display sizes.
        family = T.FONT_FAMILY_BOLD if size >= T.FONT_SUBTITLE else T.FONT_FAMILY
        weight = ft.FontWeight.W_400 if family == T.FONT_FAMILY_BOLD else ft.FontWeight.W_600
        return ft.Text(text, size=size, weight=weight, color=T.TEXT_PRIMARY, font_family=family)

    heading_controls: list[ft.Control] = [
        ft.Column(
            spacing=1,
            expand=True,
            controls=[
                _heading_title(title, T.FONT_SUBTITLE),
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
        border_radius=T.RADIUS, border=ft.Border.all(1, T.BORDER),
        expand=expand,
    )


def list_row(
    *,
    leading: Optional[ft.Control] = None,
    title: str,
    subtitle: Optional[str] = None,
    trailing: Optional[ft.Control] = None,
    on_click: Optional[Callable] = None,
    divider: bool = False,
) -> ft.Control:
    """A flat row for alert / activity lists.

    Rows used to each be a filled, rounded box stacked inside a card — six boxes
    in one panel, none of them important. A row is a row: no fill, no radius, and
    a hairline separating it from the next. ``divider`` draws that rule.
    """
    controls: list[ft.Control] = []
    if leading is not None:
        controls.append(leading)
    controls.append(
        ft.Column(
            spacing=1,
            expand=True,
            controls=[
                ft.Text(title, size=T.FONT_BODY, color=T.TEXT_PRIMARY, weight=ft.FontWeight.W_500),
                *([ft.Text(subtitle, size=T.FONT_SMALL, color=T.TEXT_SECONDARY)] if subtitle else []),
            ],
        )
    )
    if trailing is not None:
        controls.append(trailing)
    return ft.Container(
        padding=ft.Padding.only(
            left=10, right=4, top=10, bottom=0 if divider else 10
        ),
        border=(
            ft.Border.only(bottom=ft.BorderSide(1, T.BORDER_SUBTLE))
            if divider else None
        ),
        ink=on_click is not None,
        on_click=on_click,
        content=ft.Row(spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=controls),
    )


def icon_tile(icon: str, *, color: str, bgcolor: str | None = None, size: int = 42) -> ft.Control:
    """A rounded pastel icon tile (the small square icon used across the mockups)."""
    return ft.Container(
        width=size,
        height=size,
        border_radius=T.RADIUS_SMALL,
        bgcolor=bgcolor or ft.Colors.with_opacity(0.16, color),
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(icon, size=int(size * 0.5), color=color),
    )


def scroll_column(controls: list[ft.Control], *, spacing: int = T.GAP) -> ft.Column:
    """A vertically scrolling column that fills its parent."""
    return ft.Column(controls=controls, spacing=spacing, scroll=ft.ScrollMode.AUTO, expand=True)


# Headline metrics are no longer one card each. ``kpi_strip`` (ui/components/
# kpi_card.py) renders every metric inside a single panel and owns its own
# breakpoints, so there is deliberately no KPI layout left in this module.


# Wide panels sit side by side on a desktop and stack on a narrow window. This is
# a *content* width (see ``app/viewport.py``), not a window width: a two-up panel
# here holds a DataTable, which needs roughly 600px a side to avoid horizontal
# overflow, so two of those plus the gap between them.
PANEL_TWO_UP_WIDTH = 2 * 600 + T.GAP

# Filter/field rows: three across on a wide desktop, two when narrower. Matched
# to the panel width so fixed-width fields always fit their column.
FILTER_WIDE_WIDTH = 1200


def _side_by_side(width: int | None, threshold: int) -> bool:
    """Whether ``width`` of content is wide enough for a multi-column row.

    ``None`` (the shell has not reported a viewport yet) counts as wide so the
    first paint matches a normal desktop window rather than stacking and then
    jumping.
    """
    return width is None or width >= threshold


def panel_grid(panels: list[tuple[ft.Control, int]], *,
               available_width: int | None = None) -> ft.Control:
    """Arrange ``(control, span)`` pairs side by side, stacking when narrow.

    ``span`` is the number of a 12-column grid the panel occupies when there is
    room for it; a panel that asked for all 12 keeps them stacked either way.
    """
    width = available_width if available_width is not None else StockWiseViewport.get()
    wide = _side_by_side(width, PANEL_TWO_UP_WIDTH)
    controls = [
        ft.Container(content=control, col=span if wide else 12)
        for control, span in panels
    ]
    return ft.ResponsiveRow(
        controls=controls,
        spacing=T.GAP,
        run_spacing=T.GAP,
    )


def flow_row(
    items: list[ft.Control | tuple[ft.Control, dict]],
    *,
    col: dict | None = None,
    spacing: int | None = None,
    available_width: int | None = None,
) -> ft.Control:
    """A row of controls that flows onto the next line instead of overflowing.

    ``items`` is a list of controls, or ``(control, col)`` pairs to give an item
    its own grid span. The ``lg`` span is used when there is room for the row and
    the ``sm`` span when there is not, so an explicit pair stays meaningful on a
    narrow window. Wrapping uses ``ResponsiveRow`` because ``ft.Row(wrap=True)``
    renders as a blank grey block in Flet 1.0.
    """
    default_col = col or {"xs": 12, "sm": 6, "lg": 3}
    width = available_width if available_width is not None else StockWiseViewport.get()
    wide = _side_by_side(width, FILTER_WIDE_WIDTH)

    wrapped: list[ft.Control] = []
    for item in items:
        control, item_col = item if isinstance(item, tuple) else (item, default_col)
        if wide:
            span = int(item_col.get("lg", item_col.get("sm", 12)))
        else:
            span = int(item_col.get("sm", item_col.get("xs", 12)))
        wrapped.append(ft.Container(content=control, col=span))
    gap = T.GAP_SMALL if spacing is None else spacing
    return ft.ResponsiveRow(
        controls=wrapped,
        spacing=gap,
        run_spacing=gap,
    )


#: Below this the window cannot fit the sidebar plus a usable content column, so
#: capping the content would leave it narrower than the window for no benefit.
_MIN_CONTENT_WIDTH = 320


def content_width(viewport_width: float | None, *, sidebar_width: int) -> int | None:
    """Pixel width the content column should occupy, or ``None`` for "fill".

    Flet 1.0 exposes no ``ConstrainedBox``, so ``T.MAX_CONTENT_WIDTH`` is applied
    by giving the content container an explicit width and centring it in a row.
    On a wide monitor this is what stops every card from becoming a wide empty
    band; below the threshold it returns ``None`` so the content simply fills,
    which is the behaviour for every window the app is actually used at.

    ``None`` must never become a ``width`` of ``None`` inside that row: a Row
    hands its children unbounded width, so the view's tables would overflow
    instead of being capped.
    """
    if not viewport_width:
        return None
    available = viewport_width - sidebar_width - 2 * T.CONTENT_PADDING
    if available <= _MIN_CONTENT_WIDTH:
        return None
    return int(min(available, T.MAX_CONTENT_WIDTH))


def money_text(value, *, size: int = T.FONT_BODY, color: str | None = None,
               weight: ft.FontWeight | None = None) -> ft.Text:
    from domain.money import format_money

    return ft.Text(
        format_money(value), size=size, color=color or T.TEXT_PRIMARY, weight=weight,
    )
