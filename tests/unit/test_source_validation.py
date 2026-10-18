"""Research source-validation tests: what is worth a fetch, and what is worth parsing."""

from __future__ import annotations

from integrations.tinyfish.source_validation import (
    content_hash, normalise_url, screen_text, validate_url,
)

GOOD_PAGE = (
    "Shree Ram Chakki Fresh Atta\n"
    "Premium whole wheat flour supplied to hotels and bakeries across India. "
    "We ship in 10 kg bags with a minimum order of 50 bags and deliver in four days. "
    "Contact our sales desk for a wholesale price list and current availability. "
) * 3


# ------------------------------------------------------------------- URL rules
def test_normalise_lowercases_host_and_strips_tracking_params():
    url = normalise_url("HTTPS://WWW.Example.COM/Deal/?utm_source=x&srsltid=y&id=7")
    assert url.startswith("https://www.example.com/Deal")
    assert "utm_source" not in url and "srsltid" not in url
    assert url.endswith("id=7")


def test_normalise_collapses_duplicate_slashes():
    assert normalise_url("https://example.com//a//b") == "https://example.com/a/b"


def test_normalise_of_nothing_is_empty():
    assert normalise_url("") == ""
    assert normalise_url(None) == ""


def test_valid_product_pages_pass():
    assert validate_url("https://example.com/product/atta-10kg") == "https://example.com/product/atta-10kg"
    assert validate_url("http://example.com/p") == "http://example.com/p"


def test_documents_and_images_are_not_worth_a_fetch():
    assert validate_url("https://example.com/price-list.pdf") is None
    assert validate_url("https://example.com/stock.csv") is None
    assert validate_url("https://example.com/photo.jpg") is None
    assert validate_url("https://example.com/installer.exe") is None


def test_unsafe_and_malformed_urls_are_rejected():
    assert validate_url("ftp://example.com/x") is None
    assert validate_url("file:///etc/passwd") is None
    assert validate_url("example.com/no-scheme") is None
    assert validate_url("https:///no-host") is None
    assert validate_url(None) is None


# ------------------------------------------------------------------ text rules
def test_real_content_is_usable_and_hashed():
    screen = screen_text(GOOD_PAGE)
    assert screen.usable is True
    assert screen.reason == "ok"
    assert screen.content_hash and len(screen.content_hash) == 16


def test_content_hash_is_stable_across_whitespace_only_changes():
    assert content_hash("hello world") == content_hash("hello  world")


def test_empty_page_is_rejected():
    assert screen_text("").usable is False
    assert screen_text(None).usable is False
    assert screen_text(None).reason == "empty"


def test_thin_pages_are_rejected_as_too_short():
    screen = screen_text("Atta 10kg Rs 249")
    assert screen.usable is False
    assert screen.reason == "too_short"


def test_login_walls_are_never_parsed():
    wall = "Sign in to continue shopping." + ("x" * 600)
    assert screen_text(wall).reason == "login_wall"


def test_js_only_pages_are_rejected():
    wall = "Please enable JavaScript and cookies to continue." + ("y" * 600)
    assert screen_text(wall).reason == "login_wall"


def test_usable_result_exposes_no_detail():
    assert screen_text(GOOD_PAGE).detail is None
    assert screen_text("short").detail == "too_short"