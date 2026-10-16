# StockWise

Desktop-first **inventory decision-support tool** for small retailers. It connects
product and stock management, sales capture, daily demand forecasting, expiry
tracking, explainable reorder recommendations, and (optionally) supplier
research — so a shop owner can see *what may sell, what could run out, what to
consider buying, and why*.

> Target demo domain: **grocery / convenience** (India, currency **INR**).
> Build target: **Windows 10/11 64-bit**, single-user local desktop.
> Recommendations are **advisory only** — StockWise never orders automatically.

## Tech stack

| Concern | Choice |
|---|---|
| UI | [Flet](https://flet.dev) 1.0 (Python desktop) |
| Database | SQLite (embedded, repository layer, migrations, WAL) |
| Data / ML | pandas, NumPy, scikit-learn, XGBoost (local training) |
| CSV / Excel | stdlib `csv`, openpyxl |
| Config / secrets | python-dotenv (`.env`, names only in `.env.example`) |
| Packaging | PyInstaller via `flet pack` |
| Tests | pytest (133 tests: unit, integration, acceptance) |

## Setup

Requires **Python 3.12 or 3.13** (built and tested on Python 3.13.7).

```powershell
# 1. Create the virtual environment (isolated project sandbox)
py -3.13 -m venv .venv

# 2. Install dependencies
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 3. Configure environment
copy .env.example .env      # then edit .env
```

## Run the app

```powershell
.venv\Scripts\flet.exe run main.py
# or directly:
.venv\Scripts\python.exe main.py

# Run as a local web app (view in a browser at http://localhost:8550)
.venv\Scripts\flet.exe run --web --port 8550 main.py
```

## Seed demo data

Populate a realistic grocery/convenience dataset (15 products, 5 suppliers,
60 days of demand history including a few simulated stockout days, opening stock,
expiry batches). Idempotent — it does nothing if products already exist unless
`--reset` is given.

```powershell
.venv\Scripts\python.exe scripts\seed_demo_data.py           # seed
.venv\Scripts\python.exe scripts\seed_demo_data.py --reset   # clear and reseed
```

Then train the forecasting model (optional; the app falls back to baselines
whenever the model is missing or worse than the baseline):

```powershell
.venv\Scripts\python.exe scripts\train_model.py
.venv\Scripts\python.exe scripts\evaluate_model.py   # baseline vs model, per product
```

## Using the app (quick tour)

| Screen | What it does |
|---|---|
| **Dashboard** | Stock value, low/out-of-stock counts, expiry and demand-spike alerts, sales-vs-forecast chart, top products by predicted demand. |
| **Inventory** | Products, batches, stock ledger, receive/adjust stock, product detail with history. |
| **Sales** | Record sales (atomic: sale + stock movement in one transaction) and import sales history. |
| **Forecasting** | Generate forecasts (baselines + XGBoost), see accuracy vs baselines, the likely range around each day, and train the model. |
| **Reorder Center** | Periodic-review recommendations with a "Why?" breakdown (P = L + R, safety stock, inventory position, MOQ/pack, budget), and recording the order you decide to place. |
| **Expiry Management** | Batches by expiry, FEFO-aware "at risk" estimates, estimated value at risk, waste write-off. |
| **Supplier Research** | Supplier records and product links (lead time, MOQ, pack, cost). Live web research is the optional TinyFish stage. |
| **Reports** | Sales/margin, top products, stock valuation, forecast accuracy, waste, open purchase orders — all exportable to CSV. |
| **Data & Imports** | Validated CSV import (row-level errors) and CSV export. |
| **Settings** | Store preferences, baseline fallback, safety-stock policy and service level, budget, forecast model management, backups, diagnostics. |

## Forecasting & statistics

- **Model.** A pooled XGBoost regressor (one model across all products, `product_id`
  as a feature) with leakage-safe lag/rolling/calendar features. It is trained
  locally on your own demand history and **adopted only when it beats or matches
  the best baseline on a chronological holdout** (WAPE). Otherwise the baseline is
  used; a clearly-labelled candidate option can force the model for inspection.
- **Fallback baseline.** When no adopted model applies, the product's most accurate
  baseline on the holdout is used automatically (`seasonal_naive`,
  `moving_average`, or `mean`). This can be pinned to a single method in Settings.
- **Prediction intervals.** Each forecast day carries a likely range of
  `± z · σ · √h`, where `σ` is the holdout residual standard deviation and `h` is
  the step. The width grows with the horizon and is shown in the forecast table.
- **Censored demand.** Days the shop was out of stock (`stockout_flag`) understate
  real demand, so they are corrected before model training using the same-weekday
  observed average — a stockout is never learned as a genuine demand drop.
- **Safety stock.** Either the *heuristic* policy (`average demand × buffer days`)
  or the *statistical* policy (`z · σ_P`, `σ_P = σ · √P` for the protection period
  `P = L + R`) at a configurable service level. Both respect the product's
  configured minimum, and the Reorder Centre explains which one it used.

## Packaging (Windows executable)

```powershell
.venv\Scripts\python.exe scripts\package_app.py
```

This runs `flet pack` and produces a self-contained folder under `dist/`
(`dist/StockWise/StockWise.exe`). The live database, logs, backups and models
still live in `%LOCALAPPDATA%\StockWise`, so upgrading the app never touches data.
`dist/` and `build/` are gitignored.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest
```

## Where data lives

The live SQLite database is **never** stored in the repo. It lives in a
per-user writable app-data directory:

| OS | Default path |
|---|---|
| Windows | `%LOCALAPPDATA%\StockWise\stockwise.db` |
| macOS | `~/Library/Application Support/StockWise/stockwise.db` |
| Linux | `~/.local/share/StockWise/stockwise.db` |

Override with the `STOCKWISE_DB_PATH` environment variable.
Logs, backups, and ML model artifacts live beside it (`logs/`, `backups/`,
`models/`).

## Architecture

Layered, in-process (no separate server for the local MVP):

```
Flet UI (views + components)
  -> application services (product, inventory, sales, supplier, forecast, reorder,
     alert, report, import/export, backup)
    -> domain (entities, enums, policies, exceptions, reorder math)
      -> repositories (interfaces + sqlite)
        -> SQLite
  ML pipeline   -> behind ForecastService / ModelService
  TinyFish      -> behind SupplierResearchService (optional, never a startup dependency)
```

Hard rules: UI has no SQL/ML/reorder/business logic; sales + stock movement are
one transaction; stock movements are an immutable ledger (corrections are
reversal records); FEFO for batches; expired stock is never usable; only
confirmed incoming purchase orders count; recommendations are advisory (no
automatic ordering). Money is `Decimal` in the domain and converted only at the
SQLite boundary.

## Status

- [x] Stage 0 — Environment and scaffolding
- [x] Stage 1 — Flet shell, config/logging, SQLite bootstrap and migrations
- [x] Stage 2 — Products, suppliers, stock ledger, batches, sales, CSV import/export
- [x] Stage 3 — Baseline forecast and data pipeline
- [x] Stage 4 — XGBoost model (adopted only if it beats/matches the best baseline)
- [x] Stage 5 — Forecast UI and explanations
- [x] Stage 6 — Periodic-review reorder engine, MOQ/pack, budget, expiry-aware
- [x] Stage 7 — Expiry management, alerts, dashboard panels
- [x] Stage 8 — TinyFish supplier research *(optional; not started)*
- [x] Stage 9 — Reports, inventory/alert hardening, CSV exports
- [x] Stage 10 — Docs, packaging, acceptance tests

### Dataset plan (next phase)

The PRD recommends the **M5 Forecasting Accuracy** dataset as the time-series
pipeline benchmark, blended with clearly-labelled synthetic local-shop scenarios.
Blending plan: M5 for the global training corpus / pipeline benchmark, synthetic
Indian-grocery data for the labelled local demo, with real benchmark metrics kept
separate from synthetic scenario outputs. M5 raw data is large and its terms do
not permit redistribution, so it will live in a gitignored `data/m5/` folder and
only derived, license-safe artifacts will be produced by an ingestion script.

## License / data notes

Zero-cost constraint: no paid APIs, hosting, or databases. TinyFish is optional
and only uses existing credits. Review dataset terms before redistributing any
benchmark data.
