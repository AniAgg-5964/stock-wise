"""StockWise — form field helpers (themed TextField and Dropdown)."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import flet as ft

from app.theme import StockWiseTheme as T


def _outline(color: str) -> ft.OutlineInputBorder:
    return ft.OutlineInputBorder(
        border_radius=ft.BorderRadius.all(T.INPUT_RADIUS),
        side=ft.BorderSide(1, color),
    )


def _border() -> dict:
    return {
        ft.ControlState.DEFAULT: _outline(T.BORDER),
        ft.ControlState.FOCUSED: _outline(T.PRIMARY),
    }


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
        bgcolor=T.BG_INPUT,
        color=T.TEXT_PRIMARY,
        text_size=T.FONT_BODY,
        cursor_color=T.PRIMARY,
        label_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL),
        border=_border(),
    )


def dropdown_field(
    label: str,
    options: Sequence[tuple[str, str]],
    *,
    value: Optional[str] = None,
    width: int | None = None,
    expand: bool = False,
    on_select: Optional[Callable] = None,
) -> ft.Dropdown:
    """A themed dropdown. ``options`` is a sequence of ``(key, label)`` pairs."""
    return ft.Dropdown(
        label=label,
        value=value,
        width=width,
        expand=expand,
        on_select=on_select,
        options=[ft.DropdownOption(key=key, text=label) for key, label in options],
        bgcolor=T.BG_INPUT,
        color=T.TEXT_PRIMARY,
        text_size=T.FONT_BODY,
        label_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL),
        border=_border(),
    )
