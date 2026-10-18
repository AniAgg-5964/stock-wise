"""TinyFish integration — transport-agnostic value objects.

These are plain dataclasses so the rest of the app never depends on the shape of
TinyFish's JSON payload; the client maps responses into them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchHit:
    """One ranked web-search result."""

    url: str
    title: str = ""
    snippet: str = ""
    site_name: str = ""
    position: int = 0
    date: str | None = None


@dataclass(frozen=True)
class FetchedPage:
    """A page returned by the Fetch API.

    ``error`` is set when that individual URL failed; the batch still succeeds so
    one bad URL never discards the pages that worked.
    """

    url: str
    text: str = ""
    final_url: str = ""
    title: str | None = None
    language: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class CandidateFact:
    """A supplier fact found in page text, with the evidence that produced it.

    ``confidence`` is a heuristic score in ``0.0..1.0`` describing how clearly the
    page stated the value — it is never a claim that the value is *correct*.
    """

    field_name: str
    field_value: str
    currency: str | None = None
    confidence: float = 0.0
    evidence: str = field(default="", repr=False)