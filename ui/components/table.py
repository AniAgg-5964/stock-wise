"""StockWise — table helpers built on Flet's ``DataTable``.

The ledger, the catalogue and the recommendation list are genuinely tabular, so
they stay a real ``DataTable``. Everything else in the app moved to cards; a grid
of boxes pretending to be a table is harder to scan than the grid itself.

Rows are clickable via an explicit trailing action cell — Flet's row selection
shows checkboxes, which is not what these tables mean.

**The table owns no edge.** It normally sits inside a ``card``, which already has
a hairline border and a radius, so the table has neither; a border on both is a
bordered rounded box inside a bordered rounded box. Column headings are a quiet
uppercase label rather than a filled grey band, which was yet another surface.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T
from app.i18n import t
from ui.components.status_chip import status_chip


def text_cell(value: str, *, color: str | None = None, weight: ft.FontWeight | None = None,
              size: int = T.FONT_BODY) -> ft.DataCell:
    return ft.DataCell(
        ft.Text(value, size=size, color=color or T.TEXT_PRIMARY,
                weight=weight or ft.FontWeight.NORMAL, no_wrap=True, max_lines=1)
    )


def chip_cell(label: str, status: str) -> ft.DataCell:
    return ft.DataCell(status_chip(label, status))


def entity_cell(
    name: str,
    subtitle: str | None = None,
    *,
    leading: ft.Control | None = None,
    width: int | None = None,
) -> ft.DataCell:
    """A cell with an optional leading tile and an optional second line.

    The inner ``Row`` must be ``tight``: Flet lays ``DataTable`` cells out with
    unbounded width, and a stretchy Row (or a bare ``Column``) inside a cell
    silently fails to render the whole table.
    """
    inner: list[ft.Control] = []
    if leading is not None:
        inner.append(leading)
    text_controls: list[ft.Control] = [
        ft.Text(name, size=T.FONT_BODY, color=T.TEXT_PRIMARY, weight=ft.FontWeight.W_500,
                no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    ]
    if subtitle:
        text_controls.append(
            ft.Text(subtitle, size=T.FONT_TINY, color=T.TEXT_TERTIARY,
                    no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        )
    inner.append(ft.Column(spacing=0, tight=True, controls=text_controls))
    row: ft.Control = ft.Row(
        spacing=10,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=inner,
    )
    return ft.DataCell(ft.Container(width=width, content=row) if width else row)


def action_cell(on_click: Callable, *, icon: str = ft.Icons.CHEVRON_RIGHT,
                tooltip: str = "Open") -> ft.DataCell:
    return ft.DataCell(
        ft.IconButton(icon, icon_size=18, icon_color=T.TEXT_SECONDARY, tooltip=tooltip,
                      on_click=on_click)
    )


def styled_table(
    labels: list[str],
    rows: list[ft.DataRow],
    *,
    column_spacing: int = 22,
    empty_message: str | None = None,
) -> ft.Control:
    """Build a themed DataTable, or an empty message when there are no rows."""
    if not rows:
        return ft.Container(
            padding=T.CARD_PADDING,
            alignment=ft.Alignment.CENTER,
            content=ft.Text(empty_message or t("table.no_records"), size=T.FONT_BODY, color=T.TEXT_TERTIARY),
        )
    table = ft.DataTable(
        columns=[
            ft.DataColumn(
                label=ft.Text(
                    lbl.upper(),
                    size=T.FONT_TINY,
                    weight=ft.FontWeight.W_600,
                    color=T.TEXT_TERTIARY,
                )
            )
            for lbl in labels
        ],
        rows=rows,
        # The card's white background shows through: no second surface.
        heading_row_color=T.BG_CARD,
        heading_row_height=40,
        # The edge belongs to the enclosing card.
        border=None,
        border_radius=None,
        horizontal_lines=ft.BorderSide(1, T.BORDER_SUBTLE),
        vertical_lines=ft.BorderSide(0, T.BORDER_SUBTLE),
        divider_thickness=0,
        column_spacing=column_spacing,
        data_row_min_height=48,
        data_row_max_height=64,
        data_row_color={
            ft.ControlState.HOVERED: ft.Colors.with_opacity(0.05, T.PRIMARY)
        },
    )
    return ft.Row([table], scroll=ft.ScrollMode.AUTO)