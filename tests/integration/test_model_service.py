"""Integration tests for the model lifecycle (train, artifact, predict, fallback)."""

from __future__ import annotations

import math
from datetime import date, timedelta

from application.services.model_service import ModelService
from ml.preprocessing import to_daily_series


def _synth_series(product_id: int, days: int = 120, *, base: float = 20.0):
    """A series with weekday seasonality, a gentle trend and mild noise."""
    start = date(2026, 1, 1)
    points = []
    for i in range(days):
        day = start + timedelta(days=i)
        weekly = 1.0 + 0.5 * day.weekday()
        trend = 1.0 + i / days
        noise = 1.0 + 0.1 * math.sin(i * 1.7 + product_id)
        points.append((day.isoformat(), base * weekly * trend * noise))
    return to_daily_series(points)


def _series_map():
    return {pid: _synth_series(pid, base=15.0 * pid) for pid in (1, 2, 3)}


class TestModelService:
    def test_no_artifact_falls_back(self, tmp_path):
        service = ModelService(model_dir=tmp_path / "empty")
        assert service.is_available() is False
        assert service.predict(product=_StubProduct(1), series=[], horizon=7) is None

    def test_train_saves_artifact_and_predicts(self, tmp_path):
        service = ModelService(model_dir=tmp_path / "models")
        summary = service.train(_series_map(), horizon=7)

        assert (tmp_path / "models" / "model_metadata.json").exists()
        assert set(summary["baseline_metrics"]) == {"seasonal_naive", "moving_average", "mean"}
        assert isinstance(summary["adopted"], bool)

        # Candidate predictions are available regardless of adoption.
        preds = service.predict(_StubProduct(1), _synth_series(1), 7, allow_candidate=True)
        assert preds is not None and len(preds) == 7
        assert all(p >= 0 for p in preds)

    def test_status_reports_metrics(self, tmp_path):
        service = ModelService(model_dir=tmp_path / "models")
        service.train(_series_map(), horizon=7)

        status = service.status()

        assert status["artifact_present"] is True
        assert "mae" in status["metrics"]
        assert status["baseline_metrics"]

    def test_training_requires_enough_rows(self, tmp_path):
        service = ModelService(model_dir=tmp_path / "models")
        small = {1: _synth_series(1, days=35)}
        try:
            service.train(small, horizon=7)
        except ValueError as exc:
            assert "rows" in str(exc)
        else:  # pragma: no cover - should not happen with 35 days
            raise AssertionError("expected ValueError for insufficient training rows")


class TestForecastServiceWithModel:
    def test_forced_candidate_is_used(self, ctx):
        # Seed demand so the model can train.
        product = ctx.product_service.create_product(
            _StubProduct.as_domain(1, "MDL-1", "Model Item")
        )
        with ctx.db.get_connection() as conn:
            start = date.today() - timedelta(days=120)
            for i in range(120):
                day = start + timedelta(days=i)
                conn.execute(
                    "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) VALUES (?,?,?)",
                    (day.isoformat(), product.id, 10 + day.weekday() * 3),
                )

        ctx.forecast_service.train_model(horizon=7, force=True)
        result = ctx.forecast_service.generate(product.id, horizon=7, method="auto")

        assert result.method == "xgboost"
        assert result.is_baseline is False

    def test_xgboost_without_model_falls_back(self, ctx):
        product = ctx.product_service.create_product(
            _StubProduct.as_domain(2, "MDL-2", "No Model Item")
        )
        with ctx.db.get_connection() as conn:
            start = date.today() - timedelta(days=40)
            for i in range(40):
                day = start + timedelta(days=i)
                conn.execute(
                    "INSERT INTO daily_demand (demand_date, product_id, quantity_sold) VALUES (?,?,?)",
                    (day.isoformat(), product.id, 5 + day.weekday()),
                )

        result = ctx.forecast_service.generate(product.id, horizon=7, method="xgboost")

        assert result.method != "xgboost"
        assert "baseline" in result.note.lower()


# --- tiny helpers so tests stay readable -------------------------------------
class _StubProduct:
    def __init__(self, pid: int) -> None:
        self.id = pid

    @staticmethod
    def as_domain(pid, sku, name):
        from decimal import Decimal

        from domain.entities import Product

        return Product(sku=sku, name=name, category="Test", unit="pcs",
                       cost_price=Decimal("10"), selling_price=Decimal("15"))
