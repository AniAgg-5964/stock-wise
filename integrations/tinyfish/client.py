"""StockWise — TinyFish REST client.

Uses only the **free** TinyFish surfaces:

* Search — ``GET  https://api.search.tinyfish.ai?query=...``  (12k/day free)
* Fetch  — ``POST https://api.fetch.tinyfish.ai``              (1k/day free)

Authentication is a plain ``X-API-Key`` header. Transport is injectable so unit
tests exercise every code path without touching the network.

The metered Agent and Browser APIs are intentionally not implemented: supplier
research must stay inside the free daily allowance.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional, Protocol

from domain.exceptions import ResearchNotConfiguredError, TinyFishError
from integrations.tinyfish.schemas import FetchedPage, SearchHit

logger = logging.getLogger(__name__)

PROVIDER = "tinyfish"

SEARCH_ENDPOINT = "https://api.search.tinyfish.ai"
FETCH_ENDPOINT = "https://api.fetch.tinyfish.ai"

#: Statuses worth retrying (rate limit + transient server faults).
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class Transport(Protocol):
    """Minimal HTTP seam so tests can stub the network."""

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None,
                 timeout: int) -> tuple[int, bytes]: ...


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None,
                      timeout: int) -> tuple[int, bytes]:
    """Default transport built on the standard library (no new dependency)."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:  # non-2xx still carries a body
        return int(exc.code), exc.read() or b""
    # URLError / socket timeouts propagate and are retried by the caller.


class TinyFishClient:
    """Read-only client for TinyFish Search and Fetch."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout_seconds: int = 30,
        max_retries: int = 2,
        transport: Optional[Transport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self.timeout_seconds = int(timeout_seconds)
        self.max_retries = max(0, int(max_retries))
        self._transport = transport or _urllib_transport
        self._sleep = sleep

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    # ------------------------------------------------------------------ search
    def search(self, query: str, *, limit: int = 10) -> list[SearchHit]:
        """Run a web search and return ranked hits (never raises on empty)."""
        query = (query or "").strip()
        if not query:
            raise TinyFishError("Search needs a non-empty query")

        params = urllib.parse.urlencode({"query": query})
        status, payload = self._request("GET", f"{SEARCH_ENDPOINT}?{params}", None)

        if status != 200:
            raise TinyFishError(_describe_http_failure("Search", status, payload))
        data = _loads(payload, "Search")

        hits: list[SearchHit] = []
        for raw in data.get("results") or []:
            url = str(raw.get("url") or "").strip()
            if not url:
                continue
            hits.append(SearchHit(
                url=url,
                title=str(raw.get("title") or "").strip(),
                snippet=str(raw.get("snippet") or "").strip(),
                site_name=str(raw.get("site_name") or "").strip(),
                position=int(raw.get("position") or 0),
                date=(str(raw.get("date")).strip() if raw.get("date") else None),
            ))
        return hits[: max(1, int(limit))]

    # ------------------------------------------------------------------- fetch
    def fetch(self, urls: list[str], *, fmt: str = "markdown") -> list[FetchedPage]:
        """Fetch up to 10 URLs. Per-URL failures are returned, not raised."""
        cleaned = [u.strip() for u in urls if (u or "").strip()][:10]
        if not cleaned:
            return []

        body = json.dumps({"urls": cleaned, "format": fmt}).encode("utf-8")
        status, payload = self._request("POST", FETCH_ENDPOINT, body)

        if status != 200:
            raise TinyFishError(_describe_http_failure("Fetch", status, payload))
        data = _loads(payload, "Fetch")

        pages: list[FetchedPage] = []
        for raw in data.get("results") or []:
            pages.append(FetchedPage(
                url=str(raw.get("url") or ""),
                final_url=str(raw.get("final_url") or raw.get("url") or ""),
                title=raw.get("title"),
                text=str(raw.get("text") or ""),
                language=raw.get("language"),
            ))
        for raw in data.get("errors") or []:
            url, message = _flatten_error(raw)
            pages.append(FetchedPage(url=url, error=message))
        return pages

    # --------------------------------------------------------------- internal
    def _request(self, method: str, url: str, body: bytes | None) -> tuple[int, bytes]:
        if not self.is_configured:
            raise ResearchNotConfiguredError(
                "TinyFish is not configured. Set TINYFISH_API_KEY in your .env file."
            )

        headers = {"X-API-Key": self._api_key, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"

        attempts = self.max_retries + 1
        for attempt in range(attempts):
            last_attempt = attempt == attempts - 1
            try:
                status, payload = self._transport(method, url, headers, body, self.timeout_seconds)
            except Exception as exc:  # network / DNS / timeout — retryable
                if last_attempt:
                    raise TinyFishError(
                        f"TinyFish {method} failed after {attempts} attempt(s): {exc}"
                    ) from exc
                logger.warning("TinyFish %s attempt %s failed: %s", method, attempt + 1, exc)
            else:
                if status not in RETRYABLE_STATUS or last_attempt:
                    return status, payload
                logger.warning("TinyFish %s returned HTTP %s, retrying", method, status)

            self._sleep(min(2.0, 0.5 * (2 ** attempt)))

        raise TinyFishError(f"TinyFish {method} exhausted {attempts} attempt(s)")  # pragma: no cover


def _loads(payload: bytes, label: str) -> dict:
    try:
        data = json.loads(payload.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TinyFishError(f"TinyFish {label} returned an unreadable response") from exc
    if not isinstance(data, dict):
        raise TinyFishError(f"TinyFish {label} returned an unexpected payload")
    return data


def _describe_http_failure(label: str, status: int, payload: bytes) -> str:
    hint = {
        401: " — the API key was rejected",
        402: " — the free daily allowance is exhausted",
        403: " — the key lacks access to this API",
        429: " — rate limited, try again shortly",
    }.get(status, "")
    detail = ""
    try:
        body = json.loads(payload.decode("utf-8") or "{}")
        if isinstance(body, dict):
            detail = str(body.get("error") or body.get("message") or "")[:200]
    except Exception:  # pragma: no cover - best effort only
        detail = ""
    return f"TinyFish {label} failed with HTTP {status}{hint}{f': {detail}' if detail else ''}"


def _flatten_error(raw) -> tuple[str, str]:
    """Pull a (url, message) pair out of the API's per-URL error shape."""
    if isinstance(raw, dict):
        url = str(raw.get("url") or "")
        message = raw.get("error") or raw.get("message") or raw.get("code") or "fetch failed"
        return url, str(message)[:300]
    return "", str(raw)[:300]