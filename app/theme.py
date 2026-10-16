"""StockWise — Theme, colours, and design tokens.

Single source of truth for the look and feel: colours, spacing, radii, typography
and status semantics. UI code imports ``StockWiseTheme as T`` and never hard-codes
raw hex values.

Two palettes are maintained — **light** (default, matching the product mockups:
light page, white cards, dark-navy sidebar) and **dark**. ``T.apply("dark")``
switches the active palette in place; every view reads ``T.*`` at build time, so a
re-render picks up the change. Token *names* never change between palettes.

Colour semantics: red = urgent, amber = warning, green = healthy, neutral = normal
information. Colour is always paired with a text label.
"""

from __future__ import annotations

import flet as ft


class StockWiseTheme:
    # ------------------------------------------------------------------ palettes
    _LIGHT: dict[str, str] = {
        # Surfaces
        "PAGE_BG": "#F4F6FB",
        "BG_DARKEST": "#0F172A",
        "BG_DARK": "#0F172A",
        "BG_CARD": "#FFFFFF",
        "BG_INPUT": "#F1F5F9",
        "BG_HOVER": "#F6F8FC",
        "BORDER": "#E3E8F0",
        "BORDER_SUBTLE": "#EEF2F7",
        # Brand
        "PRIMARY": "#2563EB",
        "PRIMARY_HOVER": "#1D4ED8",
        "PRIMARY_SUBTLE": "#E8EFFE",
        "PRIMARY_TINT": "#E8F0FE",
        "ACCENT": "#7C3AED",
        # Text
        "TEXT_PRIMARY": "#0F172A",
        "TEXT_SECONDARY": "#64748B",
        "TEXT_TERTIARY": "#94A3B8",
        "TEXT_ON_PRIMARY": "#FFFFFF",
        # Status
        "STATUS_HEALTHY": "#16A34A",
        "STATUS_WARNING": "#D97706",
        "STATUS_CRITICAL": "#DC2626",
        "STATUS_INFO": "#2563EB",
        "STATUS_NEUTRAL": "#64748B",
        # Pastel status tints (chip / tile backgrounds)
        "TINT_HEALTHY": "#E7F6EC",
        "TINT_WARNING": "#FEF3E2",
        "TINT_CRITICAL": "#FDEAEA",
        "TINT_INFO": "#E8F0FE",
        "TINT_NEUTRAL": "#EEF2F7",
        # Sidebar (dark navy in both modes)
        "SIDEBAR_BG": "#0F172A",
        "SIDEBAR_TEXT": "#94A3B8",
        "SIDEBAR_TEXT_ACTIVE": "#FFFFFF",
        "SIDEBAR_ACTIVE_BG": "#2563EB",
        "SIDEBAR_HOVER_BG": "#1E293B",
        "SIDEBAR_BORDER": "#1E293B",
        "SIDEBAR_MUTED": "#64748B",
        "SIDEBAR_CARD_BG": "#1E293B",
        # Top bar
        "TOPBAR_BG": "#FFFFFF",
        "TOPBAR_BORDER": "#E8EDF5",
        "SHADOW": "#0F172A14",
    }

    _DARK: dict[str, str] = {
        "PAGE_BG": "#0B0F1A",
        "BG_DARKEST": "#0B0F1A",
        "BG_DARK": "#111827",
        "BG_CARD": "#151B2B",
        "BG_INPUT": "#1B2233",
        "BG_HOVER": "#1F2940",
        "BORDER": "#262E44",
        "BORDER_SUBTLE": "#1C2335",
        "PRIMARY": "#6366F1",
        "PRIMARY_HOVER": "#4F46E5",
        "PRIMARY_SUBTLE": "#312E81",
        "PRIMARY_TINT": "#1E2743",
        "ACCENT": "#8B5CF6",
        "TEXT_PRIMARY": "#E5E7EB",
        "TEXT_SECONDARY": "#9CA3AF",
        "TEXT_TERTIARY": "#6B7280",
        "TEXT_ON_PRIMARY": "#FFFFFF",
        "STATUS_HEALTHY": "#22C55E",
        "STATUS_WARNING": "#F59E0B",
        "STATUS_CRITICAL": "#EF4444",
        "STATUS_INFO": "#3B82F6",
        "STATUS_NEUTRAL": "#6B7280",
        "TINT_HEALTHY": "#132A1C",
        "TINT_WARNING": "#2A2213",
        "TINT_CRITICAL": "#2A1516",
        "TINT_INFO": "#152238",
        "TINT_NEUTRAL": "#1C2335",
        "SIDEBAR_BG": "#0B0F1A",
        "SIDEBAR_TEXT": "#9CA3AF",
        "SIDEBAR_TEXT_ACTIVE": "#FFFFFF",
        "SIDEBAR_ACTIVE_BG": "#312E81",
        "SIDEBAR_HOVER_BG": "#151B2B",
        "SIDEBAR_BORDER": "#1C2335",
        "SIDEBAR_MUTED": "#6B7280",
        "SIDEBAR_CARD_BG": "#151B2B",
        "TOPBAR_BG": "#0B0F1A",
        "TOPBAR_BORDER": "#1C2335",
        "SHADOW": "#00000000",
    }

    # ------------------------------------------------- shared (palette-independent)
    mode: str = "light"

    # Spacing / radii
    CONTENT_PADDING = 24
    CARD_PADDING = 20
    GAP = 16
    GAP_SMALL = 8
    GAP_TINY = 4
    RADIUS = 14
    RADIUS_SMALL = 10
    INPUT_RADIUS = 10
    CHIP_RADIUS = 8
    SIDEBAR_WIDTH = 236
    SIDEBAR_WIDTH_COLLAPSED = 78
    TOPBAR_HEIGHT = 64

    # Typography (px)
    FONT_HERO = 26
    FONT_DISPLAY = 28
    FONT_TITLE = 22
    FONT_SUBTITLE = 16
    FONT_BODY = 14
    FONT_SMALL = 12
    FONT_TINY = 11

    # ------------------------------------------------------------- palette switching
    @classmethod
    def apply(cls, mode: str | None = None) -> None:
        """Activate the ``light`` or ``dark`` palette in place."""
        if mode in ("light", "dark"):
            cls.mode = mode
        palette = cls._LIGHT if cls.mode == "light" else cls._DARK
        for token, value in palette.items():
            setattr(cls, token, value)

    @classmethod
    def toggle(cls) -> str:
        """Flip palettes; returns the new mode."""
        cls.apply("dark" if cls.mode == "light" else "light")
        return cls.mode

    @classmethod
    def is_dark(cls) -> bool:
        return cls.mode == "dark"

    # --------------------------------------------------------------------- helpers
    @classmethod
    def status_color(cls, status: str) -> str:
        """Map a semantic status keyword to a colour."""
        mapping = {
            "healthy": cls.STATUS_HEALTHY,
            "in_stock": cls.STATUS_HEALTHY,
            "good": cls.STATUS_HEALTHY,
            "low": cls.STATUS_WARNING,
            "low_stock": cls.STATUS_WARNING,
            "near_expiry": cls.STATUS_WARNING,
            "at_risk": cls.STATUS_WARNING,
            "warning": cls.STATUS_WARNING,
            "critical": cls.STATUS_CRITICAL,
            "out_of_stock": cls.STATUS_CRITICAL,
            "expired": cls.STATUS_CRITICAL,
            "info": cls.STATUS_INFO,
            "neutral": cls.STATUS_NEUTRAL,
            "missing": cls.STATUS_NEUTRAL,
        }
        return mapping.get(status.lower(), cls.STATUS_INFO)

    @classmethod
    def tint_for(cls, status: str) -> str:
        """Map a semantic status keyword to its pastel background tint."""
        mapping = {
            "healthy": cls.TINT_HEALTHY,
            "in_stock": cls.TINT_HEALTHY,
            "good": cls.TINT_HEALTHY,
            "low": cls.TINT_WARNING,
            "low_stock": cls.TINT_WARNING,
            "near_expiry": cls.TINT_WARNING,
            "at_risk": cls.TINT_WARNING,
            "warning": cls.TINT_WARNING,
            "critical": cls.TINT_CRITICAL,
            "out_of_stock": cls.TINT_CRITICAL,
            "expired": cls.TINT_CRITICAL,
            "info": cls.TINT_INFO,
            "neutral": cls.TINT_NEUTRAL,
            "missing": cls.TINT_NEUTRAL,
        }
        return mapping.get(status.lower(), cls.TINT_INFO)

    @classmethod
    def shadow(cls) -> list[ft.BoxShadow] | None:
        """A soft card shadow (a no-op in dark mode)."""
        if cls.is_dark():
            return None
        return [
            ft.BoxShadow(
                blur_radius=18,
                spread_radius=0,
                color=cls.SHADOW,
                offset=ft.Offset(0, 4),
            )
        ]

    @classmethod
    def input_border(cls) -> dict:
        """The ``{ControlState: OutlineInputBorder}`` used by all text inputs."""
        def outline(color: str) -> ft.OutlineInputBorder:
            return ft.OutlineInputBorder(
                border_radius=ft.BorderRadius.all(cls.INPUT_RADIUS),
                side=ft.BorderSide(1, color),
            )

        return {
            ft.ControlState.DEFAULT: outline(cls.BORDER),
            ft.ControlState.FOCUSED: outline(cls.PRIMARY),
        }

    @classmethod
    def get_flet_theme(cls) -> ft.Theme:
        """Build the Flet ``Theme`` for the active palette."""
        return ft.Theme(
            color_scheme_seed=cls.PRIMARY,
            color_scheme=ft.ColorScheme(
                primary=cls.PRIMARY,
                on_primary=cls.TEXT_ON_PRIMARY,
                secondary=cls.ACCENT,
                on_secondary=cls.TEXT_ON_PRIMARY,
                surface=cls.BG_CARD,
                on_surface=cls.TEXT_PRIMARY,
                surface_container=cls.BG_INPUT,
                outline=cls.BORDER,
                outline_variant=cls.BORDER_SUBTLE,
                error=cls.STATUS_CRITICAL,
            ),
        )


# Activate the default palette so ``T.<TOKEN>`` exists from import time.
StockWiseTheme.apply("light")
