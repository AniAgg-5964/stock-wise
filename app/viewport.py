"""StockWise — the live content width.

Flet's ``ResponsiveRow`` picks a column span from a breakpoint table, and the docs
describe those as "minimum widths" without saying whether they are measured
against the *page* or against the *parent container*. Flutter evaluates layout
builders against the constraints a container actually receives, which for every
row in this app is the content column — a full window width minus the sidebar and
the content padding. Betting on that is how ``KPI_BREAKPOINTS["lg"] = 1240``
ended up meaning a 1544px window: a 1366 or 1440 laptop, which is what most shops
actually have, never reached four-across and fell into the 2x2 fallback.

So the shell measures the viewport itself and publishes the **content** width
here, and components read it directly instead of inferring it from a breakpoint
table. That makes the layout arithmetic explicit and unit-testable, and it makes
the documented width budget in ``kpi_card`` mean what it says.

Mirrors the ``StockWiseTheme`` singleton pattern: a single ``set`` from the shell
on startup and on every resize, and reads from anywhere below.
"""

from __future__ import annotations


class StockWiseViewport:
    #: Pixel width available to the content column, or ``None`` before the first
    #: measurement. ``None`` means "not known yet", never "unbounded".
    content: int | None = None

    @classmethod
    def set(cls, width: int | None) -> None:
        cls.content = width

    @classmethod
    def get(cls) -> int | None:
        return cls.content