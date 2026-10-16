# StockWise

Desktop-first **inventory decision-support tool** for small retailers. It connects
product and stock management, sales capture, daily demand forecasting, expiry
tracking, explainable reorder recommendations, and traceable supplier research —
so a shop owner can see *what may sell, what could run out, what to consider
buying, and why*.

> Target demo domain: **grocery / convenience** (India, currency **INR**).
> Build target: **Windows 10/11 64-bit**, single-user local desktop.

## Tech stack

| Concern | Choice |
|---|---|
| UI | [Flet](https://flet.dev) 1.0 (Python desktop) |
| Database | SQLite (embedded, repository layer, migrations, WAL) |
| Data / ML | pandas, NumPy, scikit-learn, XGBoost (local training) |
| CSV / Excel | stdlib `csv`, openpyxl |
| Config / secrets | python-dotenv (`.env`, names only in `.env.example`) |
| Packaging | PyInstaller via `flet pack` |
| Tests | pytest, pytest-cov |

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
60 days of demand history, opening stock, expiry batches). Idempotent — it does
nothing if products already exist unless `--reset` is given.

```powershell
.venv\Scripts\python.exe scripts\seed_demo_data.py           # seed
.venv\Scripts\python.exe scripts\seed_demo_data.py --reset   # clear and reseed
```

CSV import templates live in `imports/templates/`.

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
  -> application services (product, inventory, sales, forecast, reorder, supplier,
     import/export, backup)
    -> domain (entities, enums, policies, exceptions)
      -> repositories (interfaces + sqlite)
        -> SQLite
  ML pipeline   -> behind ForecastService
  TinyFish      -> behind SupplierResearchService (optional, never a startup dependency)
```

Hard rules: UI has no SQL/ML/reorder/business logic; sales + stock movement are
one transaction; stock movements are an immutable ledger (corrections are
reversal records); FEFO for batches; expired stock is never usable; only
confirmed incoming purchase orders count; recommendations are advisory (no
automatic ordering).

## Status

Stage 0–2 complete (P0 core). Forecasting, reorder, and TinyFish are later stages.

- [x] Stage 0 — Environment and scaffolding
- [x] Stage 1 — Flet shell, config/logging, SQLite bootstrap and migrations
- [x] Stage 2 — Products, suppliers, stock ledger, batches, sales, CSV import/export
- [ ] Stage 3 — Baseline forecast and data pipeline
- [ ] Stage 4 — XGBoost model
- [ ] Stage 5 — Forecast UI and explanations
- [ ] Stage 6 — Periodic-review reorder engine, alerts, budget, expiry
- [ ] Stage 7 — Dashboard, usability, pilot simulation
- [ ] Stage 8 — TinyFish supplier research
- [ ] Stage 9 — Hardening, security, packaging
- [ ] Stage 10 — Demo, measurement, handoff

## License / data notes

Zero-cost constraint: no paid APIs, hosting, or databases. Only TinyFish uses
existing credits. Review dataset terms before redistributing any benchmark data.
