"""StockWise — Theme, colours, and design tokens.

Single source of truth for the dark "control centre" look: colours, spacing,
radii, typography sizes, and status colour semantics. UI code imports
``StockWiseTheme as T`` and never hard-codes raw hex values.

Colour semantics (from the UI/UX spec): red = urgent, amber = warning,
green = healthy, neutral = normal information. Always pair colour with a label.
"""

from __future__ import annotations

import flet as ft


class StockWiseTheme:
    # --- Surfaces ---
    BG_DARKEST = "#0B0F1A"
    BG_DARK = "#111827"
    BG_CARD = "#151B2B"
    BG_INPUT = "#1B2233"
    BG_HOVER = "#1F2940"
    BORDER = "#262E44"
    BORDER_SUBTLE = "#1C2335"

    # --- Brand ---
    PRIMARY = "#6366F1"
    PRIMARY_HOVER = "#4F46E5"
    PRIMARY_SUBTLE = "#312E81"
    ACCENT = "#8B5CF6"

    # --- Text ---
    TEXT_PRIMARY = "#E5E7EB"
    TEXT_SECONDARY = "#9CA3AF"
    TEXT_TERTIARY = "#6B7280"
    TEXT_ON_PRIMARY = "#FFFFFF"

    # --- Status semantics ---
    STATUS_HEALTHY = "#22C55E"   # green - in stock / good
    STATUS_WARNING = "#F59E0B"   # amber - low / near expiry
    STATUS_CRITICAL = "#EF4444"  # red - urgent / out of stock / expired
    STATUS_INFO = "#3B82F6"      # blue - neutral information
    STATUS_NEUTRAL = "#6B7280"   # grey - unknown / missing data

    # --- Spacing / radii ---
    CONTENT_PADDING = 24
    CARD_PADDING = 18
    GAP = 16
    GAP_SMALL = 8
    RADIUS = 12
    RADIUS_SMALL = 8
    INPUT_RADIUS = 8
    SIDEBAR_WIDTH = 232

    # --- Typography (px) ---
    FONT_DISPLAY = 28
    FONT_TITLE = 20
    FONT_SUBTITLE = 16
    FONT_BODY = 14
    FONT_SMALL = 12
    FONT_TINY = 11

    @classmethod
    def status_color(cls, status: str) -> str:
        """Map a semantic status keyword to a colour."""
        mapping = {
            "healthy": cls.STATUS_HEALTHY,
            "in_stock": cls.STATUS_HEALTHY,
            "low": cls.STATUS_WARNING,
            "low_stock": cls.STATUS_WARNING,
            "near_expiry": cls.STATUS_WARNING,
            "at_risk": cls.STATUS_WARNING,
            "critical": cls.STATUS_CRITICAL,
            "out_of_stock": cls.STATUS_CRITICAL,
            "expired": cls.STATUS_CRITICAL,
            "info": cls.STATUS_INFO,
            "neutral": cls.STATUS_NEUTRAL,
            "missing": cls.STATUS_NEUTRAL,
        }
        return mapping.get(status.lower(), cls.STATUS_INFO)

    @classmethod
    def get_flet_theme(cls) -> ft.Theme:
        """Build the Flet ``Theme`` used by the ``Page``."""
        return ft.Theme(
            color_scheme_seed=cls.PRIMARY,
            color_scheme=ft.ColorScheme(
                primary=cls.PRIMARY,
                on_primary=cls.TEXT_ON_PRIMARY,
                surface=cls.BG_CARD,
                on_surface=cls.TEXT_PRIMARY,
                outline=cls.BORDER,
            ),
        )
