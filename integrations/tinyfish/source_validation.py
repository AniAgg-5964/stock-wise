"""StockWise — decide which research sources are worth fetching and parsing.

Kept separate from the client so the rules are unit-testable without a network:
URL screening happens *before* spending a fetch, and text screening happens
*before* trusting extracted numbers.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

#: Extensions that are never worth a research fetch (not readable product pages).
BLOCKED_EXTENSIONS = frozenset({
    ".pdf", ".csv", ".xls", ".xlsx", ".zip", ".rar", ".7z", ".gz",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".mp4", ".mp3",
    ".exe", ".dmg", ".apk", ".doc", ".docx", ".ppt", ".pptx",
})

ALLOWED_SCHEMES = frozenset({"http", "https"})

#: A page shorter than this is almost always a stub, not a product listing.
MIN_CONTENT_CHARS = 400

#: Hosts that commonly serve a bot wall to anything that is not a logged-in human
#: browser. TinyFish's free Fetch API is not a headless browser, so these usually
#: refuse a fetch outright — which is why most Indian B2B marketplace listings
#: come back empty.
#:
#: This list is **advisory only**. It never blocks a page: sites change their
#: defences, and the user may know better than we do. It exists so we can warn
#: *before* spending a fetch, and so batch actions can prioritise better targets.
KNOWN_BOT_HOSTILE_HOSTS = frozenset({
    "indiamart.com", "tradeindia.com", "exportersindia.com", "dir.indiamart.com",
    "amazon.in", "amazon.com", "flipkart.com", "meesho.com", "snapdeal.com",
    "jiomart.com", "bigbasket.com", "blinkit.com", "zepto.com", "swiggy.com",
    "alibaba.com", "aliexpress.com", "made-in-china.com", "globalsources.com",
    "ebay.com", "etsy.com", "walmart.com", "target.com", "ebay.co.in",
})

#: How far back to look when learning which hosts have already refused us.
FAILED_HOST_LOOKBACK_DAYS = 30

#: Phrases that mean "we got a wall, not a page" — never parse facts from these.
_WALL_MARKERS = (
    "sign in to continue",
    "log in to continue",
    "please log in",
    "enable javascript and cookies",
    "verify you are human",
    "are you a robot",
    "access denied",
    "403 forbidden",
    "subscribe to continue",
    "create a free account to",
    "you have reached your limit",
)


@dataclass(frozen=True)
class ScreenResult:
    """Outcome of screening a fetched page."""

    usable: bool
    reason: str = "ok"
    content_hash: str | None = None

    @property
    def detail(self) -> str | None:
        return None if self.usable else self.reason


def normalise_url(url: str | None) -> str:
    """Trim tracking noise and canonicalise the scheme casing."""
    if not url:
        return ""
    cleaned = url.strip()
    parts = urlparse(cleaned)
    if not parts.scheme:
        return ""
    path = re.sub(r"/{2,}", "/", parts.path)
    # Drop the common tracking parameters only; keep anything meaningful.
    kept = [
        (k, v) for k, v in parse_qsl(parts.query)
        if not k.lower().startswith(("utm_", "srsltid"))
    ]
    return urlunparse((parts.scheme.lower(), parts.netloc.lower(), path, "", urlencode(kept), ""))


def validate_url(url: str | None) -> str | None:
    """Return a fetchable, normalised URL, or ``None`` with the reason logged.

    Callers treat ``None`` as "do not spend a fetch on this".
    """
    normalised = normalise_url(url)
    if not normalised:
        return None

    parts = urlparse(normalised)
    if parts.scheme not in ALLOWED_SCHEMES:
        return None
    if not parts.netloc:
        return None

    path_lower = parts.path.lower()
    if any(path_lower.endswith(ext) for ext in BLOCKED_EXTENSIONS):
        return None
    return normalised


def content_hash(text: str) -> str:
    """Stable short hash of page content, used to spot unchanged pages.

    Whitespace runs are collapsed first so a page that only reflows (re-rendered
    markup, different line wrapping) still hashes to the same value.
    """
    normalised = re.sub(r"\s+", " ", text or "").strip()
    return hashlib.sha256(normalised.encode("utf-8", "replace")).hexdigest()[:16]


def screen_text(text: str | None, *, min_chars: int = MIN_CONTENT_CHARS) -> ScreenResult:
    """Decide whether extracted page text is real content worth parsing."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ScreenResult(usable=False, reason="empty")

    lowered = cleaned.lower()[:4000]
    for marker in _WALL_MARKERS:
        if marker in lowered:
            return ScreenResult(usable=False, reason="login_wall")

    if len(cleaned) < min_chars:
        return ScreenResult(usable=False, reason="too_short")

    return ScreenResult(usable=True, reason="ok", content_hash=content_hash(cleaned))


# ------------------------------------------------------------------- host rules
def host_of(url: str | None) -> str:
    """Return the bare host of ``url``: lower-cased, no scheme, port or ``www.``.

    Accepts a bare domain (``indiamart.com``) as well as a full URL, because
    supplier records are hand-typed and users rarely include a scheme.
    """
    if not url:
        return ""
    candidate = url.strip()
    parts = urlparse(candidate if "//" in candidate else f"//{candidate}")
    host = (parts.netloc or "").split("@")[-1].split(":")[0].strip().lower()
    return host[4:] if host.startswith("www.") else host


def is_known_bot_hostile(url: str | None) -> bool:
    """True when this host — or a parent of it — usually refuses automated fetches.

    Matches on parent domains too, so ``in.indiamart.com`` is caught by
    ``indiamart.com``. Advisory: callers warn and reprioritise, never refuse.
    """
    host = host_of(url)
    if not host:
        return False
    return any(
        host == known or host.endswith(f".{known}")
        for known in KNOWN_BOT_HOSTILE_HOSTS
    )