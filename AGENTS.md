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
# local web preview: .venv\Scripts\flet.exe run --web --port 8550 main.py

# Seed the demo dataset (idempotent; --reset to clear first)
.venv\Scripts\python.exe scripts\seed_demo_data.py

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
- TinyFish calls happen only inside `SupplierResearchService`; results are advisory
  candidate observations until the user applies them.
- Sales + stock movement are written in ONE transaction.
- `stock_movements` is an immutable ledger; corrections are reversal/correction records, never rewrites.
- FEFO for batch consumption; expired stock is never usable.
- Only confirmed, outstanding purchase orders count as incoming stock.
- Money uses Decimal or integer minor units, never binary floats.
- The live DB lives in a per-user writable dir, never the repo or CWD (`%LOCALAPPDATA%\StockWise`).
- Recommendations are advisory only — no automatic ordering.
- Forecasting must not mutate stock.

## Layout

- `app/` — config, logging, bootstrap (DI wiring via `build_context`/`AppContext`), navigation, theme
- `domain/` — entities, enums, policies (validation + FEFO + status), exceptions, money helpers
- `application/dto.py` — DTOs (ImportPreview/ImportResult, ProductStock, DashboardStats)
- `application/services/` — product, inventory, sales, supplier, import_export, backup, dashboard (+ forecast/reorder later)
- `repositories/interfaces.py` — repository contracts; `repositories/sqlite/` — connection (FK ON, WAL), schema (idempotent + versioned), per-table repos
- `ui/views/` — real screens (dashboard, inventory, product_detail, sales, expiry, suppliers, reports/import-export, settings) + placeholders for later stages
- `ui/components/` — layout (page_header/card/section), forms (text_field/dropdown_field), feedback (notify/banner), table, kpi_card, status_chip, empty_state
- `ml/` — data_validation, preprocessing, features, train, evaluate, predict, fallback, artifacts
- `integrations/tinyfish/` — `client.py` (stdlib urllib; Search + Fetch only, no
  metered Agent/Browser), `schemas.py`, `parser.py` (deterministic fact extraction),
  `source_validation.py`. Transport is injectable so tests never hit the network.
- `integrations/tinyfish/source_validation.py` also holds `KNOWN_BOT_HOSTILE_HOSTS`
  plus `host_of()` / `is_known_bot_hostile()`. This list is **advisory** — it warns and
  deprioritises, and must never be used to refuse a URL the user chose. Pair it with
  the learned list (`SqliteExternalSourceRepository.list_failed_sources`) rather than
  trusting the curated one alone.
- `imports/templates/` — CSV templates; `migrations/` — schema versions
- `scripts/` — seed_demo_data.py (and later train/evaluate)
- `tests/unit|integration|acceptance/`; `tests/conftest.py` provides the `ctx` and `wired_app_context` fixtures

## Environment

`.env` (gitignored) is loaded by `python-dotenv`. Copy from `.env.example`:
`TINYFISH_API_KEY` (optional), `STOCKWISE_ENV`, `STOCKWISE_LOG_LEVEL`, `STOCKWISE_DB_PATH`.

## Flet 1.0 notes (verified against installed 1.0.4)

Flet resolves to **1.0.4** — write against the Flet 1.0 API. Verify styling/control
signatures against current Flet 1.0 docs (Context7 MCP server is configured) rather
than assuming older 0.x APIs. Specifics already hit:

- Buttons: `ft.Button` / `ft.FilledButton` / `ft.OutlinedButton` / `ft.TextButton` / `ft.IconButton`.
  There is **no** `ft.ElevatedButton`. Use `content=` (str or control) plus `icon=`.
- Dialogs/snackbars: `page.show_dialog(dialog)` and `page.pop_dialog()` (not `page.open`/`page.close`).
  `page.show_dialog(ft.SnackBar(...))` for snackbars.
- `ft.Switch` uses `label_text_style`; `ft.Checkbox` uses `label_style`.
- `ft.Dropdown` uses `ft.DropdownOption(key=..., text=...)` and `on_select`.
- Text fields: style the border with a `{ControlState.DEFAULT: OutlineInputBorder(...), ControlState.FOCUSED: ...}` dict
  (the old `border_color`/`focused_border_color`/`border_radius` kwargs are deprecated).
- `ft.DataTable` rows expose `on_select_change` (shows checkboxes) — for row clicks we add an explicit action cell instead.
- React to enum values with `.value`, never `str(enum)` (which yields `"MovementType.SALE"`).
- `ft.Row(wrap=True)` makes the whole row (and everything under it) render as a blank grey
  block in 1.0.4 — never use it. Use `ft.ResponsiveRow` instead; `ui/components/layout.py`
  provides `flow_row(...)`, `kpi_grid(...)` and `panel_grid(...)` for wrapping layouts.
- `ft.DataCell` content is laid out with unbounded width: a stretchy `ft.Row` or a bare
  `ft.Column` inside a cell makes the entire `DataTable` render blank. Wrap cell content in a
  `tight=True` Row — use `ui/components/table.py`'s `entity_cell(...)` for name/subtitle cells.
- `ft.Stack` children shrink-wrap unless you pass `fit=ft.StackFit.EXPAND`; position overlay
  children with explicit `top`/`right`/`left`/`bottom`.
- `ft.ColorScheme` has no `background`/`on_background` in 1.0 — use `surface`/`on_surface`.
- Input borders: pass `border=ft.OutlineInputBorder(border_radius=..., side=ft.BorderSide(...))`
  or a `{ControlState: OutlineInputBorder}` dict. `TextField.border_radius` and
  `Dropdown.focused_border_color` are deprecated.

## Gotchas

- Tests create isolated temp databases; the `ctx` fixture builds the full service graph on a temp DB,
  and `wired_app_context` points the shared `app_context` singleton at it for view-construction tests.
- `pyproject.toml` pins exact dependency versions; keep the in-repo `requirements.lock` in sync if you change them.
- Schema is versioned via `schema_version`; bump `DB_SCHEMA_VERSION` and add a migration rather than altering tables in place.
- Money is `Decimal` in the domain; repositories convert at the SQLite boundary (`to_money`/`to_db`).
  Never multiply a `Decimal` by a float — wrap the float in `Decimal(str(x))` first.
- `ForecastService` memoises two demand-history reads (`demand_series`,
  `backtest`). Both are pure functions of the `daily_demand` table, and
  **`SalesService.record_sale` must keep calling `invalidate_demand_cache(...)`
  after its transaction commits**. Any new writer of `daily_demand` must do the
  same, or forecasts, alerts and reorder figures go stale. Stored `forecasts` are
  deliberately *not* cached, so regenerating a forecast shows up immediately.
- Views that render a whole screen should share one `products` /
  `snapshots_for_products` / `latest_for_products` pass across their panels.
  `dashboard_view` does this; a panel that re-queries per-panel is what made
  navigation take seconds.
- `DatabaseConnection(reuse_connections=True)` caches one connection **per thread**
  (set by `build_context` for the app). It is off by default so tests keep a fresh
  connection per call and never hold a deleted temp file open on Windows. Never
  hold a returned connection across a `with` block's end, and keep passing `conn=`
  down to nested repository calls — a nested *fresh* connection during an open
  write transaction would deadlock. Cold connections measured ~20ms for their first
  query here versus ~0.4ms warm, so this is the single biggest performance lever.
