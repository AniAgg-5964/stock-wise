"""StockWise — table helpers built on Flet's ``DataTable``.

Rows are clickable via an explicit trailing action cell (Flet's row selection
shows checkboxes, which we don't want).
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T
from ui.components.status_chip import status_chip


def text_cell(value: str, *, color: str | None = None, weight: ft.FontWeight | None = None,
              size: int = T.FONT_BODY) -> ft.DataCell:
    return ft.DataCell(
        ft.Text(value, size=size, color=color or T.TEXT_PRIMARY, weight=weight or ft.FontWeight.NORMAL)
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
        ft.Text(name, size=T.FONT_BODY, color=T.TEXT_PRIMARY, weight=ft.FontWeight.W_500)
    ]
    if subtitle:
        text_controls.append(ft.Text(subtitle, size=T.FONT_TINY, color=T.TEXT_TERTIARY))
    inner.append(ft.Column(spacing=1, tight=True, controls=text_controls))
    row: ft.Control = ft.Row(
        spacing=10,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=inner,
    )
    return ft.DataCell(ft.Container(width=width, content=row) if width else row)


def action_cell(on_click: Callable, *, icon: str = ft.Icons.CHEVRON_RIGHT, tooltip: str = "Open") -> ft.DataCell:
    return ft.DataCell(
        ft.IconButton(icon, icon_size=18, icon_color=T.TEXT_SECONDARY, tooltip=tooltip, on_click=on_click)
    )


def styled_table(
    labels: list[str],
    rows: list[ft.DataRow],
    *,
    column_spacing: int = 20,
    empty_message: str = "No records",
) -> ft.Control:
    """Build a themed DataTable, or an empty message when there are no rows."""
    if not rows:
        return ft.Container(
            padding=T.CARD_PADDING,
            alignment=ft.Alignment.CENTER,
            content=ft.Text(empty_message, size=T.FONT_SMALL, color=T.TEXT_TERTIARY),
        )
    table = ft.DataTable(
        columns=[ft.DataColumn(label=ft.Text(lbl.upper(), size=T.FONT_TINY, weight=ft.FontWeight.W_600,
                                             color=T.TEXT_TERTIARY)) for lbl in labels],
        rows=rows,
        heading_row_color=T.BG_INPUT,
        heading_row_height=44,
        border=ft.Border.all(1, T.BORDER_SUBTLE),
        border_radius=T.RADIUS_SMALL,
        horizontal_lines=ft.BorderSide(1, T.BORDER_SUBTLE),
        divider_thickness=0,
        column_spacing=column_spacing,
        data_row_min_height=46,
        data_row_max_height=64,
        data_row_color={ft.ControlState.HOVERED: ft.Colors.with_opacity(0.06, T.PRIMARY)},
    )
    return ft.Row([table], scroll=ft.ScrollMode.AUTO)
