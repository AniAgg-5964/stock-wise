"""StockWise — model lifecycle service (train, load, predict, fallback).

Wraps the ``ml`` package for the application layer: it owns the model artifact
directory, trains the pooled XGBoost model, and *never* raises during prediction
\u2014 any problem returns ``None`` so the forecast service falls back to a baseline.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

from app.config import Config
from ml import artifacts
from ml.features import FEATURE_SCHEMA_VERSION
from ml.predict import recursive_forecast
from ml.preprocessing import DayPoint
from ml.train import train_global

logger = logging.getLogger(__name__)


class ModelService:
    def __init__(self, model_dir: Path | str | None = None) -> None:
        self.model_dir = Path(model_dir) if model_dir is not None else Config.MODEL_DIR

    # ------------------------------------------------------------------- status
    def metadata(self) -> dict | None:
        return artifacts.load_metadata(model_dir=self.model_dir)

    def is_available(self) -> bool:
        """True when an adopted, schema-compatible model artifact is present."""
        meta = self.metadata()
        return bool(
            meta
            and meta.get("adopted")
            and meta.get("feature_schema_version") == FEATURE_SCHEMA_VERSION
            and artifacts.model_exists(model_dir=self.model_dir)
        )

    def status(self) -> dict:
        meta = self.metadata() or {}
        return {
            "artifact_present": artifacts.model_exists(model_dir=self.model_dir),
            "available": self.is_available(),
            "version": meta.get("version"),
            "adopted": bool(meta.get("adopted")),
            "trained_at": meta.get("trained_at"),
            "metrics": meta.get("metrics", {}) or {},
            "baseline_metrics": meta.get("baseline_metrics", {}) or {},
            "notes": meta.get("notes", ""),
            "model_dir": str(self.model_dir),
        }

    # ---------------------------------------------------------------- prediction
    def predict(
        self,
        product,
        series: Sequence[DayPoint],
        horizon: int,
        *,
        allow_candidate: bool = False,
    ) -> list[float] | None:
        meta = self.metadata()
        if not meta:
            return None
        if not meta.get("adopted") and not allow_candidate:
            return None
        if meta.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
            logger.info("Model feature schema mismatch; using fallback.")
            return None

        model = artifacts.load_model(model_dir=self.model_dir)
        if model is None:
            return None

        try:
            history = [p.quantity for p in series]
            start = date.fromisoformat(series[-1].date) + timedelta(days=1) if series else date.today()
            return recursive_forecast(lambda X, m=model: m.predict(X), history, product.id, start, horizon)
        except Exception as exc:  # never crash the app on inference
            logger.warning("Model prediction failed (%s); using fallback.", exc)
            return None

    # ------------------------------------------------------------------ training
    def train(
        self,
        series_by_product: Mapping[int, Sequence[DayPoint]],
        *,
        horizon: int = 7,
        force: bool = False,
    ) -> dict:
        """Train and persist a pooled model; return a JSON-safe summary."""
        model, result = train_global(series_by_product, horizon=horizon)
        adopted = bool(result.adopted) or force
        metadata = {
            "version": result.version,
            "model_type": "xgboost",
            "feature_schema_version": result.feature_schema_version,
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "horizon": horizon,
            "adopted": adopted,
            "metrics": result.metrics,
            "baseline_metrics": result.baseline_metrics,
            "train_start": result.train_start,
            "train_end": result.train_end,
            "test_start": result.test_start,
            "test_end": result.test_end,
            "products": result.products,
            "n_train": result.n_train,
            "hyperparameters": result.hyperparameters,
            "notes": result.notes,
        }
        artifacts.save_artifact(model, metadata, model_dir=self.model_dir)

        summary = dict(metadata)
        summary["artifact_path"] = str(self.model_dir)
        summary["adopted_by_holdout"] = bool(result.adopted)
        return summary
