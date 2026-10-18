"""Tests for the demand-read memoisation in ``ForecastService``.

The cache is a performance device with one real hazard: a stale read after a sale
has been recorded. These tests pin both halves of that bargain -- the reads *are*
memoised, and they *are* dropped the moment the underlying history changes.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from domain.entities import Product, Sale, SaleItem


def _make_product(ctx, sku="CACHE-1", name="Cached Item"):
    return ctx.product_service.create_product(
        Product(sku=sku, name=name, category="Test", unit="pcs",
                cost_price=Decimal("10"), selling_price=Decimal("15"))
    )


def _seed_demand(ctx, product_id, days, base=10):
    today = date.today()
    with ctx.db.get_connection() as conn:
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            conn.execute(
                "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) "
                "VALUES (?, ?, ?)",
                (day.isoformat(), product_id, float(base)),
            )


def _count_history_queries(ctx):
    """Wrap the repository read so we can count how often it actually runs."""
    repo = ctx.forecast_repo
    original = repo.get_demand_history_full
    calls = {"n": 0}

    def counting(product_id, **kwargs):
        calls["n"] += 1
        return original(product_id, **kwargs)

    repo.get_demand_history_full = counting
    return calls


class TestDemandSeriesMemoisation:
    def test_repeat_reads_hit_the_database_once(self, ctx):
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 30)
        ctx.forecast_service.demand_series(product.id)  # warm the page

        calls = _count_history_queries(ctx)
        for _ in range(5):
            ctx.forecast_service.demand_series(product.id)

        assert calls["n"] == 0, "a warm cache must not touch the database"

    def test_the_imputed_series_is_cached_separately(self, ctx):
        """Imputed and raw series differ, so they must not share a cache entry."""
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 30)
        service = ctx.forecast_service

        raw = service.demand_series(product.id)
        imputed = service.demand_series(product.id, impute=True)

        assert raw is not imputed
        assert service.demand_series(product.id) is raw
        assert service.demand_series(product.id, impute=True) is imputed

    def test_backtest_is_memoised(self, ctx):
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 40)
        ctx.forecast_service.backtest(product.id, horizon=7)

        calls = _count_history_queries(ctx)
        for _ in range(5):
            ctx.forecast_service.backtest(product.id, horizon=7)

        assert calls["n"] == 0

    def test_invalidation_clears_only_the_named_product(self, ctx):
        first = _make_product(ctx, sku="CACHE-A", name="A")
        second = _make_product(ctx, sku="CACHE-B", name="B")
        _seed_demand(ctx, first.id, 30)
        _seed_demand(ctx, second.id, 30)
        service = ctx.forecast_service
        service.demand_series(first.id)
        service.demand_series(second.id)

        service.invalidate_demand_cache(first.id)

        calls = _count_history_queries(ctx)
        service.demand_series(first.id)
        service.demand_series(second.id)
        assert calls["n"] == 1, "only the invalidated product is rebuilt"

    def test_invalidation_without_a_product_clears_everything(self, ctx):
        first = _make_product(ctx, sku="CACHE-C", name="C")
        second = _make_product(ctx, sku="CACHE-D", name="D")
        _seed_demand(ctx, first.id, 30)
        _seed_demand(ctx, second.id, 30)
        service = ctx.forecast_service
        service.demand_series(first.id)
        service.demand_series(second.id)

        service.invalidate_demand_cache()

        calls = _count_history_queries(ctx)
        service.demand_series(first.id)
        service.demand_series(second.id)
        assert calls["n"] == 2


class TestCacheInvalidationOnWrite:
    def test_recording_a_sale_updates_average_demand_immediately(self, ctx):
        """The hazard this cache could introduce, guarded directly."""
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 30, base=0)
        service = ctx.forecast_service

        before = service.average_daily_demand(product.id)
        # Warm the cache so an un-invalidated cache would definitely be stale.
        service.average_daily_demand(product.id)

        ctx.sales_service.record_sale(Sale(
            items=[SaleItem(product_id=product.id, quantity=100, unit_price=Decimal("15"))],
        ), allow_override=True)

        after = service.average_daily_demand(product.id)

        assert after > before, "a recorded sale must change the demand figures at once"

    def test_a_sale_is_reflected_in_the_stored_forecast_context(self, ctx):
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 30, base=0)
        ctx.forecast_service.generate(product.id, horizon=7)
        service = ctx.forecast_service

        before = service.latest(product.id)

        ctx.sales_service.record_sale(Sale(
            items=[SaleItem(product_id=product.id, quantity=50, unit_price=Decimal("15"))],
        ), allow_override=True)

        after = service.latest(product.id)
        assert after.average_daily_demand != before.average_daily_demand
        # The sale lands on today, which the seeded history did not cover, so the
        # series correctly grows by one observed day.
        assert after.observed_days > before.observed_days

    def test_a_rolled_back_sale_does_not_disturb_the_cache(self, ctx):
        """Invalidation happens after commit, so a failure must not clear good data."""
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 30)
        service = ctx.forecast_service
        service.demand_series(product.id)
        calls = _count_history_queries(ctx)

        try:
            ctx.sales_service.record_sale(Sale(
                items=[SaleItem(product_id=999_999, quantity=1, unit_price=Decimal("15"))],
            ))
        except Exception:
            pass  # expected: unknown product

        service.demand_series(product.id)
        assert calls["n"] == 0, "a failed sale must not evict a valid cache"


class TestBatchForecastReads:
    def test_batch_matches_the_single_product_read(self, ctx):
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 40)
        ctx.forecast_service.generate(product.id, horizon=7)
        service = ctx.forecast_service

        batched = service.latest_for_products([product.id])
        single = service.latest(product.id)

        assert product.id in batched
        assert batched[product.id] == single

    def test_products_without_a_forecast_are_absent(self, ctx):
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 40)

        assert ctx.forecast_service.latest_for_products([product.id]) == {}
        assert ctx.forecast_service.latest(product.id) is None

    def test_an_empty_request_is_harmless(self, ctx):
        assert ctx.forecast_service.latest_for_products([]) == {}

    def test_a_newly_generated_forecast_is_visible_immediately(self, ctx):
        """Stored forecasts are deliberately not cached."""
        product = _make_product(ctx)
        _seed_demand(ctx, product.id, 40)
        service = ctx.forecast_service

        assert service.latest(product.id) is None
        service.generate(product.id, horizon=7)

        assert service.latest(product.id) is not None
        assert product.id in service.latest_for_products([product.id])