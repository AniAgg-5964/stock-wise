"""Report the current model status and per-product baseline accuracy.

Usage (from the repo root, with the project venv):

    .venv\\Scripts\\python.exe scripts\\evaluate_model.py
    .venv\\Scripts\\python.exe scripts\\evaluate_model.py --horizon 7

Reads the trained model metadata (if any) and back-tests the baselines for every
active product using a chronological holdout. Read-only: it never trains or
changes stock.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import build_context  # noqa: E402
from app.config import Config  # noqa: E402
from repositories.sqlite.connection import DatabaseConnection  # noqa: E402
from repositories.sqlite.schema import initialize_database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Report forecasting accuracy.")
    parser.add_argument("--db-path", type=str, default=None)
    parser.add_argument("--horizon", type=int, default=7)
    args = parser.parse_args()

    if args.db_path:
        Config.DB_PATH = Path(args.db_path)

    db = DatabaseConnection()
    initialize_database(db)
    ctx = build_context(db)

    status = ctx.forecast_service.model_status()
    print(f"Model artifact present: {status.get('artifact_present')}")
    print(f"Adopted:                {status.get('adopted')}")
    print(f"Version:                {status.get('version')}")
    print(f"Trained at:             {status.get('trained_at')}")
    print(f"Notes:                  {status.get('notes')}\n")

    print(f"{'Product':<34} {'SN MAE':>8} {'MA WAPE':>9} {'Best':>16}")
    print("-" * 70)
    for product in ctx.product_service.list_products(active_only=True):
        metrics = ctx.forecast_service.backtest(product.id, horizon=args.horizon)
        if not metrics:
            print(f"{product.name[:33]:<34} {'(insufficient history)':>36}")
            continue
        by_method = {m.method: m for m in metrics}
        sn = by_method.get("seasonal_naive")
        ma = by_method.get("moving_average")
        best = min((m for m in metrics if m.wape is not None), key=lambda m: m.wape, default=None)
        print(
            f"{product.name[:33]:<34} "
            f"{(f'{sn.mae:.2f}' if sn else '-'):>8} "
            f"{(f'{ma.wape:.1f}%' if ma and ma.wape is not None else '-'):>9} "
            f"{(best.label if best else '-'):>16}"
        )


if __name__ == "__main__":
    main()
