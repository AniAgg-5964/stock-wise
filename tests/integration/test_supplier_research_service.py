"""Supplier research service tests (integration, fully offline).

Uses a fake TinyFish client so the whole flow — search, fetch, screen, extract,
cache, verify, apply, reject — is exercised without a network call.
"""

from __future__ import annotations

import pytest

from application.services.supplier_research_service import (
    SETTING_ENABLED, SupplierResearchService,
)
from domain.entities import Product, ProductSupplier, Supplier, SupplierObservation
from domain.exceptions import (
    NotFoundError, ResearchNotConfiguredError, TinyFishError, ValidationError,
)
from integrations.tinyfish.schemas import FetchedPage, SearchHit

PAGE_TEXT = (
    "Shree Ram Chakki Fresh Atta\n"
    "Premium whole wheat flour for hotels and bakeries. Pack size: 10 kg. "
    "MOQ: 50 bags. Unit price Rs 42.50 per kg. Delivery in 4 days. "
    "We supply across India with reliable weekly dispatch and a dedicated sales desk. "
) * 3


class FakeClient:
    """Stands in for TinyFishClient; records calls and replays scripted pages."""

    def __init__(self, *, configured=True, hits=None, pages=None):
        self.is_configured = configured
        self.hits = hits if hits is not None else [
            SearchHit(url="https://example.com/atta", title="Atta 10kg",
                      snippet="wholesale", site_name="example.com", position=1),
            SearchHit(url="https://blocked.com/p", title="Blocked",
                      snippet="", site_name="blocked.com", position=2),
            SearchHit(url="https://example.com/list.pdf", title="PDF",
                      snippet="", site_name="example.com", position=3),
        ]
        self.pages = pages if pages is not None else {
            "https://example.com/atta": FetchedPage(
                url="https://example.com/atta", final_url="https://example.com/atta",
                title="Atta 10kg", text=PAGE_TEXT,
            ),
            "https://blocked.com/p": FetchedPage(
                url="https://blocked.com/p", error="target_http_error",
            ),
        }
        self.search_calls: list = []
        self.fetch_calls: list = []

    def search(self, query, *, limit=10):
        self.search_calls.append({"query": query, "limit": limit})
        return self.hits[:limit]

    def fetch(self, urls, *, fmt="markdown"):
        self.fetch_calls.append(list(urls))
        return [self.pages.get(u, FetchedPage(url=u, error="not_found")) for u in urls]


def _service(ctx, client=None, **kwargs):
    return SupplierResearchService(
        ctx.external_sources, ctx.supplier_observations, ctx.suppliers, ctx.products,
        ctx.audit, ctx.settings, client if client is not None else FakeClient(), **kwargs,
    )


def _rebind(research, client):
    """Same repositories and settings, different client (to observe caching)."""
    return SupplierResearchService(
        research.sources, research.observations, research.suppliers, research.products,
        research.audit, research.settings, client,
        cache_minutes=research.cache_minutes,
        max_fetches_per_action=research.max_fetches_per_action,
    )


@pytest.fixture
def enabled(ctx):
    research = _service(ctx)
    research.set_enabled(True)
    return research


@pytest.fixture
def product(ctx):
    return ctx.product_service.create_product(Product(
        sku="SKU-A", name="Wheat Flour Atta", category="Staples",
        unit="kg", brand="Shree Ram",
    ))


# ------------------------------------------------------------------ lifecycle
def test_research_starts_switched_off(ctx):
    status = _service(ctx).status()
    assert status.enabled is False
    assert status.can_run is False
    assert status.reason


def test_enabling_research_is_audited(ctx):
    research = _service(ctx)
    research.set_enabled(True)
    assert research.status().can_run is True
    assert ctx.settings.get(SETTING_ENABLED) == "1"

    types = [e["event_type"] for e in ctx.db.query_all(
        "SELECT event_type FROM audit_events WHERE event_type = 'supplier_research_toggled'"
    )]
    assert types


def test_search_is_refused_while_switched_off(ctx, product):
    with pytest.raises(TinyFishError) as excinfo:
        _service(ctx).search(product_id=product.id)
    assert "switched off" in str(excinfo.value)


def test_search_is_refused_without_a_key(ctx, product):
    research = _service(ctx, FakeClient(configured=False))
    research.set_enabled(True)
    with pytest.raises(ResearchNotConfiguredError):
        research.search(product_id=product.id)


def test_unconfigured_status_names_the_env_var(ctx):
    status = _service(ctx, FakeClient(configured=False)).status()
    assert status.configured is False
    assert "TINYFISH_API_KEY" in status.reason


# --------------------------------------------------------------------- search
def test_query_is_built_from_real_product_data(enabled, product):
    query = enabled.build_query(product.id)
    assert "Shree Ram" in query and "Wheat Flour Atta" in query


def test_query_for_a_missing_product_raises(enabled):
    with pytest.raises(NotFoundError):
        enabled.build_query(99999)


def test_search_persists_sources_and_drops_unfetchable_urls(enabled, product):
    candidates = enabled.search(product_id=product.id, limit=5)

    urls = [c.url for c in candidates]
    assert "https://example.com/atta" in urls
    # blocked.com is fine, but a PDF and a bare host must be filtered out.
    assert "https://example.com/list.pdf" not in urls
    assert all(c.source_id for c in candidates)
    assert enabled.sources.count() == len(candidates)


def test_search_records_the_query_used(enabled, product):
    enabled.search(product_id=product.id)
    stored = enabled.sources.list_by_query(enabled.build_query(product.id))
    assert stored and stored[0].parse_status == "discovered"


def test_search_uses_a_free_text_query_when_given(enabled, ctx):
    client = FakeClient()
    research = _rebind(enabled, client)
    research.search(query="bulk rice supplier")

    assert client.search_calls[0]["query"] == "bulk rice supplier"
    # Two of the three canned hits are fetchable URLs; the PDF is screened out.
    assert research.sources.count() == 2


def test_blank_free_text_query_without_a_product_is_rejected(enabled):
    with pytest.raises(ValidationError):
        enabled.search(query="   ")


# ------------------------------------------------------------------- research
def test_research_extracts_and_stores_candidate_facts(enabled, product):
    result = enabled.research(url="https://example.com/atta", product_id=product.id)

    assert result.cached is False
    fields = {o.field_name for o in result.observations}
    assert "minimum_order_qty" in fields
    assert "unit_cost" in fields

    stored = list(enabled.observations_for_product(product.id))
    assert len(stored) == len(result.observations)
    assert all(o.verified_by_user is False for o in stored)
    assert all(o.confidence > 0 for o in stored)


def test_research_marks_the_source_ok_and_hashes_it(enabled, product):
    result = enabled.research(url="https://example.com/atta", product_id=product.id)
    source = result.sources[0]
    assert source.parse_status == "ok"
    assert source.content_hash
    assert enabled.sources.get_by_id(source.id).parse_status == "ok"


def test_a_blocked_page_is_recorded_without_inventing_facts(enabled, product):
    result = enabled.research(url="https://blocked.com/p", product_id=product.id)

    assert result.observations == []
    assert result.skipped and "refused" in result.skipped[0]
    assert result.sources[0].parse_status.startswith("fetch_error")


def test_second_research_of_the_same_url_uses_the_cache(enabled, product):
    first = enabled.research(url="https://example.com/atta", product_id=product.id)
    assert first.cached is False

    client = FakeClient()
    second = _rebind(enabled, client).research(
        url="https://example.com/atta", product_id=product.id
    )

    assert second.cached is True
    assert client.fetch_calls == [], "cached research must not spend a fetch"
    assert len(second.observations) == len(first.observations)


def test_research_caps_the_number_of_pages_per_action(enabled, product, ctx):
    urls = [f"https://example.com/p{i}" for i in range(8)]
    research = _service(ctx, FakeClient(), max_fetches_per_action=2)
    research.set_enabled(True)

    result = research.research_many(urls, product_id=product.id)

    assert len(result.sources) == 2
    assert any("Capped at 2" in note for note in result.skipped)


def test_research_screens_out_a_login_wall(ctx, product):
    client = FakeClient(pages={
        "https://example.com/wall": FetchedPage(
            url="https://example.com/wall", text="Sign in to continue." + "x" * 800,
        ),
    })
    research = _service(ctx, client)
    research.set_enabled(True)

    result = research.research(url="https://example.com/wall", product_id=product.id)

    assert result.observations == []
    assert "login wall" in result.skipped[0]


# ------------------------------------------------------------------ applying
def _first_cost_observation(research, product_id):
    for obs in research.observations_for_product(product_id):
        if obs.field_name == "unit_cost":
            return obs
    raise AssertionError("no unit_cost observation was extracted")


def test_research_never_writes_to_product_suppliers_by_itself(enabled, product):
    enabled.research(url="https://example.com/atta", product_id=product.id)
    assert list(enabled.suppliers.get_product_suppliers(product.id)) == []


def test_apply_writes_the_value_to_the_chosen_supplier(enabled, product, ctx):
    supplier = ctx.supplier_service.create_supplier(Supplier(name="Kirana Wholesale"))
    enabled.research(url="https://example.com/atta", product_id=product.id)
    observation = _first_cost_observation(enabled, product.id)

    link = enabled.apply(observation.id, supplier.id)

    assert link.unit_cost is not None
    assert float(link.unit_cost) == 42.50
    assert link.last_verified_at is not None
    assert enabled.observations.get_by_id(observation.id).verified_by_user is True


def test_apply_creates_the_link_when_none_exists_yet(enabled, product, ctx):
    supplier = ctx.supplier_service.create_supplier(Supplier(name="New Supplier"))
    enabled.research(url="https://example.com/atta", product_id=product.id)
    observation = _first_cost_observation(enabled, product.id)

    link = enabled.apply(observation.id, supplier.id)

    assert link.product_id == product.id
    assert link.supplier_id == supplier.id
    assert link.pack_size >= 1
    assert link.minimum_order_qty >= 1


def test_apply_preserves_the_existing_link_values(enabled, product, ctx):
    supplier = ctx.supplier_service.create_supplier(Supplier(name="Existing"))
    ctx.suppliers.link_product_supplier(ProductSupplier(
        product_id=product.id, supplier_id=supplier.id,
        minimum_order_qty=99, pack_size=7, lead_time_days=11, is_preferred=True,
    ))
    enabled.research(url="https://example.com/atta", product_id=product.id)
    observation = _first_cost_observation(enabled, product.id)

    link = enabled.apply(observation.id, supplier.id)

    assert link.minimum_order_qty == 99, "unrelated fields must not be reset"
    assert link.pack_size == 7
    assert link.lead_time_days == 11
    assert link.is_preferred is True


def test_apply_rejects_a_foreign_currency_price(enabled, product, ctx):
    supplier = ctx.supplier_service.create_supplier(Supplier(name="Exporter"))
    observation = enabled.observations.create_many([SupplierObservation(
        field_name="unit_cost", field_value="12.00", currency="USD",
        confidence=0.8, product_id=product.id,
    )])[0]

    with pytest.raises(ValidationError) as excinfo:
        enabled.apply(observation.id, supplier.id)
    assert "INR" in str(excinfo.value)


def test_apply_rejects_a_non_numeric_value(enabled, product, ctx):
    supplier = ctx.supplier_service.create_supplier(Supplier(name="Junk"))
    observation = enabled.observations.create_many([SupplierObservation(
        field_name="minimum_order_qty", field_value="lots", confidence=0.8,
        product_id=product.id,
    )])[0]

    with pytest.raises(ValidationError):
        enabled.apply(observation.id, supplier.id)


def test_apply_requires_an_existing_supplier(enabled, product, ctx):
    enabled.research(url="https://example.com/atta", product_id=product.id)
    observation = _first_cost_observation(enabled, product.id)
    with pytest.raises(NotFoundError):
        enabled.apply(observation.id, 424242)


def test_apply_needs_the_observation_tied_to_a_product(enabled, ctx):
    supplier = ctx.supplier_service.create_supplier(Supplier(name="Any"))
    observation = enabled.observations.create_many([SupplierObservation(
        field_name="unit_cost", field_value="10.00", currency="INR", confidence=0.8,
    )])[0]
    with pytest.raises(ValidationError):
        enabled.apply(observation.id, supplier.id)


def test_apply_of_a_missing_observation_raises(enabled):
    with pytest.raises(NotFoundError):
        enabled.apply(987654, 1)


# ------------------------------------------------------- verify and rejection
def test_verify_marks_the_candidate(enabled, product):
    enabled.research(url="https://example.com/atta", product_id=product.id)
    observation = enabled.observations_for_product(product.id)[0]

    verified = enabled.verify(observation.id)

    assert verified.verified_by_user is True


def test_reject_deletes_the_candidate_and_leaves_an_audit_trail(enabled, product, ctx):
    enabled.research(url="https://example.com/atta", product_id=product.id)
    before = len(enabled.observations_for_product(product.id))
    observation = enabled.observations_for_product(product.id)[0]

    enabled.reject(observation.id)

    assert len(enabled.observations_for_product(product.id)) == before - 1
    assert enabled.observations.get_by_id(observation.id) is None
    rows = ctx.db.query_all(
        "SELECT * FROM audit_events WHERE event_type = 'supplier_observation_rejected'"
    )
    assert rows


def test_reject_of_a_missing_observation_raises(enabled):
    with pytest.raises(NotFoundError):
        enabled.reject(555555)


# ----------------------------------------------------------------------- views
class _StubPage:
    """Minimal stand-in for ``ft.Page`` while a view is being constructed."""

    def __init__(self):
        self.controls = []

    def update(self):
        pass

    def show_dialog(self, dialog):
        pass

    def pop_dialog(self):
        pass


def test_suppliers_view_renders_the_panel_with_research_switched_on(ctx, wired_app_context, product):
    import flet as ft

    from ui.views.registry import build_view

    research = _service(ctx, FakeClient())
    research.set_enabled(True)
    wired_app_context.research_service = research

    view = build_view("/suppliers", _StubPage(), lambda route: None)

    assert isinstance(view, ft.Control)


def test_suppliers_view_renders_without_a_key(ctx, wired_app_context):
    import flet as ft

    from ui.views.registry import build_view

    # The conftest client has no API key: the panel must explain, not crash.
    wired_app_context.research_service = _service(ctx, FakeClient(configured=False))

    view = build_view("/suppliers", _StubPage(), lambda route: None)

    assert isinstance(view, ft.Control)