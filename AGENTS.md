# StockWise

Desktop-first inventory decision-support tool for small retailers (Python + Flet).
Single-user local desktop MVP; Windows-first; demo domain grocery/convenience; currency INR.

## Commands

Always use the project venv interpreter (`.venv\Scripts\python.exe`); do not use the
system `python` (3.14, unsupported). Built and tested on **Python 3.13.7**.

```
# Install / refresh deps
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Run the app (Flet 1.0: use the installed flet CLI; `python -m flet` does NOT work)
.venv\Scripts\flet.exe run main.py
# or: .venv\Scripts\python.exe main.py

# Tests (run from repo root; pyproject sets testpaths=["tests"], pythonpath=["."])
.venv\Scripts\python.exe -m pytest

# Single test file / test
.venv\Scripts\python.exe -m pytest tests/unit/test_schema.py
.venv\Scripts\python.exe -m pytest tests/unit/test_schema.py::TestDatabaseSchema::test_foreign_keys_enabled
```

No linter/formatter/typecheck or CI is configured. Do not invent lint commands.

## Architecture (layered — keep it that way)

```
Flet UI (ui/views, ui/components)
  -> application services (application/services)   # orchestration, transactions, DTOs
    -> domain (domain/entities, enums, policies, exceptions)  # invariants + math
      -> repositories (repositories/interfaces, repositories/sqlite)
        -> SQLite (per-user app-data dir)
  ml/            -> behind ForecastService
  integrations/tinyfish/ -> behind SupplierResearchService (optional, never a startup dep)
```

Rules from the product spec (do not violate):
- UI event handlers must not contain SQL, ML, reorder math, or TinyFish calls.
- Sales + stock movement are written in ONE transaction.
- `stock_movements` is an immutable ledger; corrections are reversal/correction records, never rewrites.
- FEFO for batch consumption; expired stock is never usable.
- Only confirmed, outstanding purchase orders count as incoming stock.
- Money uses Decimal or integer minor units, never binary floats.
- The live DB lives in a per-user writable dir, never the repo or CWD (`%LOCALAPPDATA%\StockWise`).
- Recommendations are advisory only — no automatic ordering.
- Forecasting must not mutate stock.

## Layout

- `app/` — config, logging, bootstrap (DI wiring), navigation, theme
- `domain/` — entities, enums, policies, exceptions
- `application/services/` — product, inventory, sales, forecast, reorder, supplier, import_export, backup
- `repositories/sqlite/` — connection (FK ON, WAL), schema (idempotent + versioned), per-table repos
- `ui/views/` and `ui/components/` — Flet screens and reusable widgets
- `ml/` — data_validation, preprocessing, features, train, evaluate, predict, fallback, artifacts
- `integrations/tinyfish/` — client, schemas, parser, source_validation
- `imports/templates/` — CSV templates; `migrations/` — schema versions
- `scripts/` — seed_demo_data.py (and later train/evaluate)
- `tests/unit|integration|acceptance/`

## Environment

`.env` (gitignored) is loaded by `python-dotenv`. Copy from `.env.example`:
`TINYFISH_API_KEY` (optional), `STOCKWISE_ENV`, `STOCKWISE_LOG_LEVEL`, `STOCKWISE_DB_PATH`.

## Flet

Flet resolves to **1.0.4** — write against the Flet 1.0 API. Verify styling/control
signatures against current Flet 1.0 docs (Context7 MCP server is configured) rather
than assuming older 0.x APIs.

## Gotchas

- Tests create isolated temp databases; they never touch the real app-data DB.
- `pyproject.toml` pins exact dependency versions; keep the in-repo `requirements.lock` in sync if you change them.
- Schema is versioned via `schema_version`; bump `DB_SCHEMA_VERSION` and add a migration rather than altering tables in place.
