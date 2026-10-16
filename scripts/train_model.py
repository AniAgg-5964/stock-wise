"""Train the XGBoost demand model (admin/developer operation).

Usage (from the repo root, with the project venv):

    .venv\\Scripts\\python.exe scripts\\train_model.py
    .venv\\Scripts\\python.exe scripts\\train_model.py --horizon 7 --force
    .venv\\Scripts\\python.exe scripts\\train_model.py --db-path C:\\temp\\demo.db

Training is never triggered automatically on app launch (PRD 7.9). The model is
only adopted when it beats or matches the best baseline on a chronological
holdout; ``--force`` adopts it regardless (clearly labelled as a candidate).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import build_context  # noqa: E402
from app.config import Config  # noqa: E402
from domain.exceptions import StockWiseError  # noqa: E402
from repositories.sqlite.connection import DatabaseConnection  # noqa: E402
from repositories.sqlite.schema import initialize_database  # noqa: E402


def _fmt(value, *, pct: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}%" if pct else f"{value:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the StockWise demand model.")
    parser.add_argument("--db-path", type=str, default=None, help="Train against a specific database.")
    parser.add_argument("--horizon", type=int, default=7, help="Forecast horizon / holdout days.")
    parser.add_argument("--force", action="store_true", help="Adopt the model even if it does not beat the baseline.")
    args = parser.parse_args()

    if args.db_path:
        Config.DB_PATH = Path(args.db_path)

    db = DatabaseConnection()
    initialize_database(db)
    ctx = build_context(db)

    print(f"Database: {db.db_path}")
    print(f"Model directory: {ctx.model_service.model_dir}")
    try:
        summary = ctx.forecast_service.train_model(horizon=args.horizon, force=args.force)
    except (StockWiseError, ValueError) as exc:
        print(f"Cannot train yet: {exc}")
        raise SystemExit(1)

    print(f"\nTrained model {summary['version']} on {summary['n_train']} rows "
          f"across {summary['products']} products.")
    print(f"Holdout window: {summary['test_start']} -> {summary['test_end']}")
    print(f"Adopted: {summary['adopted']}  ({summary['notes']})\n")

    model_m = summary.get("metrics", {})
    print("Model:     MAE={mae}  RMSE={rmse}  WAPE={wape}  Bias={bias}".format(
        mae=_fmt(model_m.get("mae")), rmse=_fmt(model_m.get("rmse")),
        wape=_fmt(model_m.get("wape"), pct=True), bias=_fmt(model_m.get("bias")),
    ))
    for name, m in (summary.get("baseline_metrics") or {}).items():
        print("{label:<10} MAE={mae}  RMSE={rmse}  WAPE={wape}  Bias={bias}".format(
            label=name, mae=_fmt(m.get("mae")), rmse=_fmt(m.get("rmse")),
            wape=_fmt(m.get("wape"), pct=True), bias=_fmt(m.get("bias")),
        ))


if __name__ == "__main__":
    main()
