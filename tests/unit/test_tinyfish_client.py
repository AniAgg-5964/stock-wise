"""TinyFish REST client tests — every path runs against a stubbed transport."""

from __future__ import annotations

import json

import pytest

from domain.exceptions import ResearchNotConfiguredError, TinyFishError
from integrations.tinyfish.client import FETCH_ENDPOINT, SEARCH_ENDPOINT, TinyFishClient


class Recorder:
    """Stub transport that replays scripted responses and records requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({
            "method": method, "url": url, "headers": headers,
            "body": body, "timeout": timeout,
        })
        response = self.responses.pop(0) if self.responses else (200, b"{}")
        if isinstance(response, Exception):
            raise response
        return response


def _client(responses, **kwargs):
    transport = Recorder(responses)
    kwargs.setdefault("max_retries", 0)
    client = TinyFishClient("test-key", transport=transport, sleep=lambda _s: None, **kwargs)
    return client, transport


# --------------------------------------------------------------------- basics
def test_client_is_not_configured_without_a_key():
    client = TinyFishClient("")
    assert client.is_configured is False


def test_calls_without_a_key_raise_a_clear_error():
    client = TinyFishClient("")
    with pytest.raises(ResearchNotConfiguredError) as excinfo:
        client.search("atta")
    assert "TINYFISH_API_KEY" in str(excinfo.value)
    # ResearchNotConfiguredError must stay a TinyFishError so callers can catch one type.
    assert isinstance(excinfo.value, TinyFishError)


def test_blank_query_is_rejected_before_any_request():
    client, transport = _client([])
    with pytest.raises(TinyFishError):
        client.search("   ")
    assert transport.calls == []


# ---------------------------------------------------------------------- search
def test_search_parses_hits_and_sends_the_api_key():
    payload = json.dumps({
        "query": "atta",
        "results": [
            {"position": 1, "title": "Atta 10kg", "url": "https://example.com/a",
             "snippet": "cheap", "site_name": "example.com", "date": "2 hours ago"},
            {"position": 2, "title": "No url", "url": "", "snippet": "dropped"},
        ],
        "total_results": 2,
    }).encode()
    client, transport = _client([(200, payload)])

    hits = client.search("atta")

    assert [h.url for h in hits] == ["https://example.com/a"]
    assert hits[0].title == "Atta 10kg"
    assert hits[0].site_name == "example.com"
    assert hits[0].date == "2 hours ago"

    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["url"].startswith(SEARCH_ENDPOINT)
    assert "query=atta" in call["url"]
    assert call["headers"]["X-API-Key"] == "test-key"


def test_search_respects_the_limit():
    payload = json.dumps({"results": [
        {"url": f"https://e.com/{i}", "title": str(i)} for i in range(10)
    ]}).encode()
    client, _ = _client([(200, payload)])
    assert len(client.search("x", limit=3)) == 3


# ----------------------------------------------------------------------- fetch
def test_fetch_posts_urls_and_parses_pages():
    payload = json.dumps({
        "results": [{
            "url": "https://example.com/p", "final_url": "https://example.com/p",
            "title": "Page", "text": "body", "language": "en",
        }],
        "errors": [],
    }).encode()
    client, transport = _client([(200, payload)])

    pages = client.fetch(["https://example.com/p"])

    assert len(pages) == 1
    assert pages[0].ok is True
    assert pages[0].text == "body"

    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == FETCH_ENDPOINT
    assert call["headers"]["Content-Type"] == "application/json"
    assert json.loads(call["body"])["urls"] == ["https://example.com/p"]


def test_fetch_reports_per_url_errors_without_failing_the_batch():
    payload = json.dumps({
        "results": [{"url": "https://ok.com", "text": "fine"}],
        "errors": [{"url": "https://bad.com", "error": "target_http_error"}],
    }).encode()
    client, _ = _client([(200, payload)])

    pages = client.fetch(["https://ok.com", "https://bad.com"])

    by_url = {p.url: p for p in pages}
    assert by_url["https://ok.com"].ok is True
    assert by_url["https://bad.com"].ok is False
    assert "target_http_error" in by_url["https://bad.com"].error


def test_fetch_ignores_blank_urls():
    client, transport = _client([])
    assert client.fetch(["", "   "]) == []
    assert transport.calls == []


# --------------------------------------------------------------------- retries
def test_retries_a_rate_limited_request_then_succeeds():
    transport = Recorder([(429, b"{}"), (200, json.dumps({"results": []}).encode())])
    client = TinyFishClient("k", max_retries=2, transport=transport, sleep=lambda _s: None)

    assert client.search("x") == []
    assert len(transport.calls) == 2, "should have retried once"


def test_retries_a_transport_exception_then_succeeds():
    transport = Recorder([OSError("connection reset"),
                          (200, json.dumps({"results": []}).encode())])
    client = TinyFishClient("k", max_retries=2, transport=transport, sleep=lambda _s: None)

    assert client.search("x") == []
    assert len(transport.calls) == 2


def test_gives_up_after_the_retry_budget():
    transport = Recorder([OSError("dns"), OSError("dns"), OSError("dns")])
    client = TinyFishClient("k", max_retries=2, transport=transport, sleep=lambda _s: None)

    with pytest.raises(TinyFishError) as excinfo:
        client.search("x")
    assert "3 attempt(s)" in str(excinfo.value)
    assert len(transport.calls) == 3


def test_does_not_retry_a_client_error():
    transport = Recorder([(404, b"{}")])
    client = TinyFishClient("k", max_retries=2, transport=transport, sleep=lambda _s: None)

    with pytest.raises(TinyFishError):
        client.search("x")
    assert len(transport.calls) == 1


def test_error_message_explains_a_rejected_key():
    client, _ = _client([(401, b"{}")])
    with pytest.raises(TinyFishError) as excinfo:
        client.search("x")
    assert "401" in str(excinfo.value)
    assert "rejected" in str(excinfo.value)


def test_error_message_explains_an_exhausted_allowance():
    client, _ = _client([(402, b"{}")])
    with pytest.raises(TinyFishError) as excinfo:
        client.search("x")
    assert "allowance" in str(excinfo.value)


def test_unreadable_payload_is_reported_not_raised_raw():
    client, _ = _client([(200, b"<html>nope</html>")])
    with pytest.raises(TinyFishError) as excinfo:
        client.search("x")
    assert "unreadable" in str(excinfo.value)


def test_timeout_is_taken_from_config():
    client, transport = _client([(200, b'{"results": []}')], timeout_seconds=7)
    client.search("x")
    assert transport.calls[0]["timeout"] == 7