"""Configuration tests: paths and defaults (no real directories written)."""

from __future__ import annotations

from pathlib import Path

from app.config import Config, get_app_data_dir, get_project_root


def test_app_data_dir_is_under_stockwise():
    path = get_app_data_dir()
    assert isinstance(path, Path)
    assert path.name == "StockWise"


def test_project_root_contains_main():
    assert (get_project_root() / "main.py").exists()


def test_db_path_is_sqlite_file():
    assert Config.DB_PATH.suffix == ".db"


def test_defaults_match_spec():
    assert Config.DEFAULT_CURRENCY == "INR"
    assert Config.DEFAULT_FORECAST_HORIZON == 7
    assert Config.DB_SCHEMA_VERSION == 1
    assert Config.TINYFISH_API_KEY == "" or isinstance(Config.TINYFISH_API_KEY, str)
