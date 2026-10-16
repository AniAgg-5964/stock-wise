"""Persist and load the trained model artifact plus its metadata (PRD 7.9).

Two files live side by side in the model directory: the XGBoost model and a JSON
metadata file (version, feature schema, metrics, adoption flag). Metadata is
always readable even when the binary model cannot be loaded.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from app.config import Config

logger = logging.getLogger(__name__)

MODEL_FILENAME = "model.xgb.json"
METADATA_FILENAME = "model_metadata.json"


def artifact_dir(model_dir: Path | str | None = None) -> Path:
    return Path(model_dir) if model_dir is not None else Config.MODEL_DIR


def save_artifact(model: Any, metadata: dict, *, model_dir: Path | str | None = None) -> Path:
    directory = artifact_dir(model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    model.save_model(str(directory / MODEL_FILENAME))
    (directory / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return directory


def load_metadata(*, model_dir: Path | str | None = None) -> Optional[dict]:
    path = artifact_dir(model_dir) / METADATA_FILENAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:  # corrupt metadata must never crash the app
        logger.warning("Could not read model metadata: %s", exc)
        return None


def load_model(*, model_dir: Path | str | None = None):
    """Return a loaded ``XGBRegressor`` or ``None`` if unavailable/corrupt."""
    path = artifact_dir(model_dir) / MODEL_FILENAME
    if not path.exists():
        return None
    try:
        import xgboost as xgb

        model = xgb.XGBRegressor()
        model.load_model(str(path))
        return model
    except Exception as exc:  # missing library, incompatible artifact, etc.
        logger.warning("Could not load model artifact: %s", exc)
        return None


def model_exists(*, model_dir: Path | str | None = None) -> bool:
    return (artifact_dir(model_dir) / MODEL_FILENAME).exists()
