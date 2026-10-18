"""StockWise — Theme, colours, and design tokens.

Single source of truth for the look and feel: colours, spacing, radii, typography
and status semantics. UI code imports ``StockWiseTheme as T`` and never hard-codes
raw hex values.

**Look and feel.** Warm rather than clinical: a deep forest green for the brand, a
cream page, and a yellow accent used sparingly.

**Surface discipline** (the rules the whole UI is built on):

1. One surface per region. A card is the *only* surface; anything inside it is
   grouped with whitespace, a hairline rule, or type scale — never with another
   filled, bordered or rounded box.
2. Never two edges. A card gets a hairline border **or** a shadow, never both, and
   its contents get neither. A table inside a card has no border of its own.
3. Sharp radii. Cards 8, small blocks and inputs 6, and a true pill only on status
   chips, where the shape is a convention people read instantly.

That is why ``shadow()`` returns ``None`` in light mode. The hairline border *is*
the edge; a second edge is what made the app read as a pile of tiles.

Colour semantics: red = urgent, amber = warning, green = healthy, neutral = normal
information. Colour is always paired with a text label. The ledger uses neutral
rather than red for ordinary sales — red has to mean something.

Two palettes are maintained, **light** (default) and **dark**. ``T.apply("dark")``
switches in place; every view reads ``T.*`` at build time, so a re-render picks the
change up. Token *names* never change between palettes.

**Fonts.** ``Mukta`` (SIL Open Font License, bundled in ``assets/fonts``) covers
both Latin and Devanagari in one family, so English and Hindi need no fallback
chain. Flet 1.0 supports only *static* fonts, so the two weights are registered as
two family names; ``FONT_FAMILY_BOLD`` is used for large display text where
synthetic bold would look thin.
"""

from __future__ import annotations

import flet as ft


class StockWiseTheme:
    # ------------------------------------------------------------------ palettes
    _LIGHT: dict[str, str] = {
        # Surfaces — warm cream rather than clinical grey. The page sits a step
        # below the cards so the cards read as raised without needing a shadow.
        "PAGE_BG": "#F5F3ED",
        "BG_DARKEST": "#15201A",
        "BG_DARK": "#15201A",
        "BG_CARD": "#FFFFFF",
        "BG_INPUT": "#F3F1EA",
        "BG_HOVER": "#F8F6F1",
        # Hairlines. BORDER is the card edge and must be visible at 1px on cream;
        # BORDER_SUBTLE is only ever used *inside* a card.
        "BORDER": "#DCD6C8",
        "BORDER_SUBTLE": "#EBE7DC",
        # Brand — deep forest green
        "PRIMARY": "#0C5C36",
        "PRIMARY_HOVER": "#094A2B",
        "PRIMARY_SUBTLE": "#DCE9E1",
        "PRIMARY_TINT": "#E9F1EC",
        # Accent — warm yellow, used sparingly (badges, highlights, never body text)
        "ACCENT": "#DE9A2E",
        "ACCENT_TEXT": "#7A5100",
        "TINT_ACCENT": "#FAEFD6",
        # Text. Secondary and tertiary were darkened so long readings hold up:
        # the old values were too close to the cream background.
        "TEXT_PRIMARY": "#15201A",
        "TEXT_SECONDARY": "#55625A",
        "TEXT_TERTIARY": "#7C8A81",
        "TEXT_ON_PRIMARY": "#FFFFFF",
        # Status
        "STATUS_HEALTHY": "#1B7F45",
        "STATUS_WARNING": "#C8741C",
        "STATUS_CRITICAL": "#BC2F26",
        "STATUS_INFO": "#1C657F",
        "STATUS_NEUTRAL": "#64726A",
        # Pastel status tints (chip / tile backgrounds)
        "TINT_HEALTHY": "#E4F1E8",
        "TINT_WARNING": "#FBEEDD",
        "TINT_CRITICAL": "#FAE6E4",
        "TINT_INFO": "#E4EEF2",
        "TINT_NEUTRAL": "#EEECE5",
        # Sidebar — deep green, the one place the brand colour runs full strength
        "SIDEBAR_BG": "#0A4A2B",
        "SIDEBAR_TEXT": "#A9CDB8",
        "SIDEBAR_TEXT_ACTIVE": "#FFFFFF",
        "SIDEBAR_ACTIVE_BG": "#13733F",
        "SIDEBAR_HOVER_BG": "#0D5733",
        "SIDEBAR_BORDER": "#0D5733",
        "SIDEBAR_MUTED": "#7FB193",
        "SIDEBAR_CARD_BG": "#0D5733",
        # Top bar
        "TOPBAR_BG": "#FFFFFF",
        "TOPBAR_BORDER": "#DCD6C8",
        "SHADOW": "#15201A14",
    }

    _DARK: dict[str, str] = {
        "PAGE_BG": "#0C120F",
        "BG_DARKEST": "#080C0A",
        "BG_DARK": "#111815",
        "BG_CARD": "#17201B",
        "BG_INPUT": "#1E2721",
        "BG_HOVER": "#1F2A23",
        "BORDER": "#2C3931",
        "BORDER_SUBTLE": "#222D27",
        "PRIMARY": "#3FCB7C",
        "PRIMARY_HOVER": "#54D98C",
        "PRIMARY_SUBTLE": "#16351F",
        "PRIMARY_TINT": "#18301F",
        "ACCENT": "#E8B04A",
        "ACCENT_TEXT": "#E8B04A",
        "TINT_ACCENT": "#362B12",
        "TEXT_PRIMARY": "#EAF1EC",
        "TEXT_SECONDARY": "#AAB9B0",
        "TEXT_TERTIARY": "#78887F",
        "TEXT_ON_PRIMARY": "#08110C",
        "STATUS_HEALTHY": "#3FCB7C",
        "STATUS_WARNING": "#DF9A38",
        "STATUS_CRITICAL": "#E26A5E",
        "STATUS_INFO": "#5BA6C1",
        "STATUS_NEUTRAL": "#78887F",
        "TINT_HEALTHY": "#15301F",
        "TINT_WARNING": "#31230E",
        "TINT_CRITICAL": "#331819",
        "TINT_INFO": "#142B34",
        "TINT_NEUTRAL": "#1E2721",
        "SIDEBAR_BG": "#080C0A",
        "SIDEBAR_TEXT": "#84AC95",
        "SIDEBAR_TEXT_ACTIVE": "#FFFFFF",
        "SIDEBAR_ACTIVE_BG": "#123C24",
        "SIDEBAR_HOVER_BG": "#0F2819",
        "SIDEBAR_BORDER": "#14291C",
        "SIDEBAR_MUTED": "#5D8269",
        "SIDEBAR_CARD_BG": "#0F2819",
        "TOPBAR_BG": "#0C120F",
        "TOPBAR_BORDER": "#222D27",
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

    # Spacing / radii. Radii are deliberately small — see the surface rules above.
    CONTENT_PADDING = 28
    CARD_PADDING = 20
    GAP = 18
    GAP_SMALL = 10
    GAP_TINY = 6
    RADIUS = 8
    RADIUS_SMALL = 6
    INPUT_RADIUS = 6
    CHIP_RADIUS = 14  # pill: the chip is ~26px tall, so this is effectively round
    SIDEBAR_WIDTH = 248
    SIDEBAR_WIDTH_COLLAPSED = 80
    TOPBAR_HEIGHT = 68

    #: Beyond this the content stops stretching. Without it a wide monitor turns
    #: every card into a wide empty band.
    MAX_CONTENT_WIDTH = 1560

    # Typography (px). The metric size is separate from FONT_DISPLAY because the
    # KPI strip packs four of them across and has to stay dense.
    FONT_HERO = 26
    FONT_DISPLAY = 28
    FONT_METRIC = 28
    FONT_TITLE = 22
    FONT_SUBTITLE = 16
    FONT_BODY = 14
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
            # A completed sale is normal information, not a failure. Showing it
            # in red made the whole ledger look like an error screen.
            "sale": cls.STATUS_NEUTRAL,
            "purchase": cls.STATUS_NEUTRAL,
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
            "sale": cls.TINT_NEUTRAL,
            "purchase": cls.TINT_NEUTRAL,
        }
        return mapping.get(status.lower(), cls.TINT_INFO)

    @classmethod
    def shadow(cls) -> list[ft.BoxShadow] | None:
        """``None`` in light mode: the hairline border is the card edge.

        A shadow *and* a border is two edges, which is what made the app read as
        a stack of tiles. Dark mode is the exception — against a near-black page a
        border alone does not separate a surface, so a single soft shadow carries
        the elevation instead.
        """
        if not cls.is_dark():
            return None
        return [
            ft.BoxShadow(
                blur_radius=14,
                spread_radius=0,
                color=ft.Colors.with_opacity(0.32, "#000000"),
                offset=ft.Offset(0, 3),
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