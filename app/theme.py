"""StockWise — Theme, colours, and design tokens.

Single source of truth for the look and feel: colours, spacing, radii, typography
and status semantics. UI code imports ``StockWiseTheme as T`` and never hard-codes
raw hex values.

**Look and feel.** The app is for a neighbourhood shopkeeper, so the palette is
warm rather than clinical: a deep forest green for the brand, a cream page, and a
yellow accent used sparingly. Green signals *fresh stock, all good*; the cream
background keeps long reading sessions easy on the eyes. Every status colour is
warm-shifted to match instead of sitting on top of the warm ground as pure hues.

Two palettes are maintained — **light** (default) and **dark**. ``T.apply("dark")``
switches the active palette in place; every view reads ``T.*`` at build time, so a
re-render picks up the change. Token *names* never change between palettes.

Colour semantics: red = urgent, amber = warning, green = healthy, neutral = normal
information. Colour is always paired with a text label.

**Fonts.** ``Mukta`` (SIL Open Font License, bundled in ``assets/fonts``) is
loaded through ``page.fonts``. It was chosen because it covers both Latin and
Devanagari in one family, so English and Hindi need no fallback chain, and it
stays legible at the small sizes a dense data table needs. Flet 1.0 only supports
*static* font files, so the two weights are registered as two family names;
``FONT_FAMILY_BOLD`` is applied to large display text where synthetic bold would
otherwise look thin.
"""

from __future__ import annotations

import flet as ft


class StockWiseTheme:
    # ------------------------------------------------------------------ palettes
    _LIGHT: dict[str, str] = {
        # Surfaces — warm, slightly creamy rather than clinical grey
        "PAGE_BG": "#F7F5EF",
        "BG_DARKEST": "#14261E",
        "BG_DARK": "#14261E",
        "BG_CARD": "#FFFFFF",
        "BG_INPUT": "#F2EFE7",
        "BG_HOVER": "#FAF8F2",
        "BORDER": "#E7E2D6",
        "BORDER_SUBTLE": "#F0ECE2",
        # Brand — deep forest green
        "PRIMARY": "#0B6B3A",
        "PRIMARY_HOVER": "#085530",
        "PRIMARY_SUBTLE": "#E4F0E8",
        "PRIMARY_TINT": "#EAF4EE",
        # Accent — warm yellow, used sparingly (badges, highlights, never body text)
        "ACCENT": "#F2B035",
        "ACCENT_TEXT": "#8A5A00",
        "TINT_ACCENT": "#FCF2DC",
        # Text
        "TEXT_PRIMARY": "#14261E",
        "TEXT_SECONDARY": "#5D6B62",
        "TEXT_TERTIARY": "#93A099",
        "TEXT_ON_PRIMARY": "#FFFFFF",
        # Status
        "STATUS_HEALTHY": "#1E8E4E",
        "STATUS_WARNING": "#D98324",
        "STATUS_CRITICAL": "#C6372D",
        "STATUS_INFO": "#1F6F8B",
        "STATUS_NEUTRAL": "#6B7A72",
        # Pastel status tints (chip / tile backgrounds)
        "TINT_HEALTHY": "#E6F3EA",
        "TINT_WARNING": "#FCF0E0",
        "TINT_CRITICAL": "#FBE9E7",
        "TINT_INFO": "#E7F1F5",
        "TINT_NEUTRAL": "#F0EEE8",
        # Sidebar — deep green, the one place the brand colour goes full strength
        "SIDEBAR_BG": "#0A4F2E",
        "SIDEBAR_TEXT": "#A8CDB6",
        "SIDEBAR_TEXT_ACTIVE": "#FFFFFF",
        "SIDEBAR_ACTIVE_BG": "#157A4A",
        "SIDEBAR_HOVER_BG": "#0E5D39",
        "SIDEBAR_BORDER": "#0E5D39",
        "SIDEBAR_MUTED": "#86B79D",
        "SIDEBAR_CARD_BG": "#0E5D39",
        # Top bar
        "TOPBAR_BG": "#FFFFFF",
        "TOPBAR_BORDER": "#EDE8DC",
        "SHADOW": "#14261E14",
    }

    _DARK: dict[str, str] = {
        "PAGE_BG": "#0E1512",
        "BG_DARKEST": "#0A100D",
        "BG_DARK": "#131C17",
        "BG_CARD": "#16211B",
        "BG_INPUT": "#1D2A22",
        "BG_HOVER": "#1E2C24",
        "BORDER": "#26362C",
        "BORDER_SUBTLE": "#1F2C25",
        "PRIMARY": "#35C46F",
        "PRIMARY_HOVER": "#46D67F",
        "PRIMARY_SUBTLE": "#173A26",
        "PRIMARY_TINT": "#1A3325",
        "ACCENT": "#F5C242",
        "ACCENT_TEXT": "#F5C242",
        "TINT_ACCENT": "#3A2F14",
        "TEXT_PRIMARY": "#E8EFEA",
        "TEXT_SECONDARY": "#A3B3A9",
        "TEXT_TERTIARY": "#6E7F75",
        "TEXT_ON_PRIMARY": "#0A100D",
        "STATUS_HEALTHY": "#35C46F",
        "STATUS_WARNING": "#E9A23B",
        "STATUS_CRITICAL": "#E8695C",
        "STATUS_INFO": "#5AA9C4",
        "STATUS_NEUTRAL": "#6E7F75",
        "TINT_HEALTHY": "#15301F",
        "TINT_WARNING": "#33260F",
        "TINT_CRITICAL": "#33191A",
        "TINT_INFO": "#152C36",
        "TINT_NEUTRAL": "#1F2C25",
        "SIDEBAR_BG": "#0A100D",
        "SIDEBAR_TEXT": "#7FA892",
        "SIDEBAR_TEXT_ACTIVE": "#FFFFFF",
        "SIDEBAR_ACTIVE_BG": "#17402A",
        "SIDEBAR_HOVER_BG": "#12291D",
        "SIDEBAR_BORDER": "#142B1F",
        "SIDEBAR_MUTED": "#5E8570",
        "SIDEBAR_CARD_BG": "#12291D",
        "TOPBAR_BG": "#0E1512",
        "TOPBAR_BORDER": "#1F2C25",
        "SHADOW": "#00000000",
    }

    # ------------------------------------------------- shared (palette-independent)
    mode: str = "light"

    # Bundled fonts (see module docstring). Two family names because Flet 1.0
    # registers one static file per family name.
    FONT_FAMILY = "Mukta"
    FONT_FAMILY_BOLD = "Mukta SemiBold"

    #: Fonts served from ``assets/fonts``; loaded into ``page.fonts`` at startup.
    FONT_FILES: dict[str, str] = {
        "Mukta": "/fonts/Mukta-Regular.ttf",
        "Mukta SemiBold": "/fonts/Mukta-SemiBold.ttf",
    }

    # Spacing / radii — roomier than a typical admin dashboard
    CONTENT_PADDING = 28
    CARD_PADDING = 22
    GAP = 18
    GAP_SMALL = 10
    GAP_TINY = 6
    RADIUS = 18
    RADIUS_SMALL = 12
    INPUT_RADIUS = 12
    CHIP_RADIUS = 12  # pill: the chip is ~22px tall, so this is effectively round
    SIDEBAR_WIDTH = 248
    SIDEBAR_WIDTH_COLLAPSED = 80
    TOPBAR_HEIGHT = 68

    # Typography (px) — larger than before: the old 11px micro-labels were the
    # single biggest reason the app read as cramped and hard to scan.
    FONT_HERO = 30
    FONT_DISPLAY = 32
    FONT_TITLE = 24
    FONT_SUBTITLE = 17
    FONT_BODY = 15
    FONT_SMALL = 13
    FONT_TINY = 12

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
        """A soft, warm card shadow (a no-op in dark mode).

        Wider blur and a warmer tint than a neutral grey shadow: on a cream page
        a grey shadow reads as dirt.
        """
        if cls.is_dark():
            return [
                ft.BoxShadow(
                    blur_radius=24,
                    spread_radius=0,
                    color=ft.Colors.with_opacity(0.30, "#000000"),
                    offset=ft.Offset(0, 6),
                )
            ]
        return [
            ft.BoxShadow(
                blur_radius=24,
                spread_radius=0,
                color=cls.SHADOW,
                offset=ft.Offset(0, 6),
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
            ft.ControlState.HOVERED: outline(cls.TEXT_TERTIARY),
            ft.ControlState.FOCUSED: outline(cls.PRIMARY),
        }

    @classmethod
    def get_flet_theme(cls) -> ft.Theme:
        """Build the Flet ``Theme`` for the active palette."""
        return ft.Theme(
            color_scheme_seed=cls.PRIMARY,
            font_family=cls.FONT_FAMILY,
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
