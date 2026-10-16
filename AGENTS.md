# StockWise

Desktop-first inventory decision-support tool for small retailers (Python + Flet).

## Run the app

```
.venv\Scripts\python.exe -m flet run main.py
```

Requires Python >=3.11. The virtualenv lives at `.venv` (gitignored). On Windows use `.venv\Scripts\python.exe`. `main.py` is the Flet entry point.

## Environment

Copy `.env.example` to `.env` and fill in values:

- `TINYFISH_API_KEY` — optional; supplier research unavailable without it
- `STOCKWISE_ENV` (default `development`), `STOCKWISE_LOG_LEVEL` (default `INFO`)
- `STOCKWISE_DB_PATH` — optional; defaults to `%LOCALAPPDATA%\StockWise\stockwise.db` (outside the repo; `*.db` is gitignored)

`app/config.py` loads `.env` automatically via `python-dotenv` on import.

## Tests

Run the suite from the repo root:

```
.venv\Scripts\python.exe -m pytest
```

`pyproject.toml` sets `testpaths = ["tests"]` and `pythonpath = ["."]`. Tests build isolated temp databases, so they never touch the real app-data DB and need no external services.

## Architecture (layered)

- `app/` — config, bootstrap (DI wiring), logging, theme, navigation, Flet 1.0 compat shim
- `domain/` — entities, enums, exceptions, stock policies
- `application/` — services (product, supplier, inventory, sales), DTOs
- `repositories/` — interfaces + SQLite implementation (connection, schema, per-table repos)
- `ui/` — Flet views and components
- `integrations/tinyfish` — supplier research API
- `ml/` — forecasting (placeholder)
- `scripts/seed_demo_data.py` — seeds products, suppliers, batches, 60 days of demand into the real app-data DB

## Gotchas

- `app/flet_compat.py` is a Flet 1.0+ compatibility shim imported in `main.py` before other Flet usage; do not remove that import.
- Schema is version 1, idempotent (`CREATE TABLE IF NOT EXISTS`), WAL journal mode, foreign keys ON.
- No lint, typecheck, formatter, or CI is configured. `dev` extras only include `pytest`/`pytest-cov`.
