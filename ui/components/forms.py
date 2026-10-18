"""StockWise — form field helpers (themed TextField, Dropdown, search box)."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import flet as ft

from app.theme import StockWiseTheme as T


def text_field(
    label: str,
    *,
    value: str = "",
    hint: Optional[str] = None,
    width: int | None = None,
    expand: bool = False,
    multiline: bool = False,
    on_change: Optional[Callable] = None,
    on_submit: Optional[Callable] = None,
    autofocus: bool = False,
    dense: bool = False,
) -> ft.TextField:
    """A themed text field usable across all forms."""
    return ft.TextField(
        label=label,
        value=value,
        hint_text=hint,
        width=width,
        expand=expand,
        multiline=multiline,
        min_lines=2 if multiline else 1,
        on_change=on_change,
        on_submit=on_submit,
        autofocus=autofocus,
        dense=dense,
        bgcolor=T.BG_CARD,
        color=T.TEXT_PRIMARY,
        text_size=T.FONT_BODY,
        cursor_color=T.PRIMARY,
        label_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL),
        hint_style=ft.TextStyle(color=T.TEXT_TERTIARY, size=T.FONT_BODY),
        border=T.input_border(),
        focused_border_color=None,
    )


def search_field(
    hint: str = "Search\u2026",
    *,
    width: int | None = None,
    expand: bool = False,
    on_change: Optional[Callable] = None,
    on_submit: Optional[Callable] = None,
) -> ft.TextField:
    """A borderless pill search box (used in the top bar and toolbars)."""
    return ft.TextField(
        hint_text=hint,
        width=width,
        expand=expand,
        height=44,
        content_padding=ft.Padding.symmetric(horizontal=16),
        on_change=on_change,
        on_submit=on_submit,
        bgcolor=T.BG_INPUT,
        color=T.TEXT_PRIMARY,
        text_size=T.FONT_BODY,
        cursor_color=T.PRIMARY,
        hint_style=ft.TextStyle(color=T.TEXT_TERTIARY, size=T.FONT_BODY),
        prefix_icon=ft.Icons.SEARCH,
        prefix_style=ft.TextStyle(color=T.TEXT_TERTIARY),
        border=ft.OutlineInputBorder(
            border_radius=ft.BorderRadius.all(T.INPUT_RADIUS),
            side=ft.BorderSide(0, ft.Colors.TRANSPARENT),
        ),
    )


def dropdown_field(
    label: str,
    options: Sequence[tuple[str, str]],
    *,
    value: Optional[str] = None,
    width: int | None = None,
    expand: bool = False,
    on_select: Optional[Callable] = None,
    dense: bool = False,
) -> ft.Dropdown:
    """A themed dropdown. ``options`` is a sequence of ``(key, label)`` pairs."""
    return ft.Dropdown(
        label=label,
        value=value,
        width=width,
        expand=expand,
        dense=dense,
        on_select=on_select,
        options=[ft.DropdownOption(key=key, text=label) for key, label in options],
        bgcolor=T.BG_CARD,
        color=T.TEXT_PRIMARY,
        text_size=T.FONT_BODY,
        label_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL),
        border=T.input_border(),
    )
