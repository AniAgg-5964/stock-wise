"""Build a standalone desktop bundle with ``flet pack`` (PyInstaller).

Windows-first. Run from the repository root with the project interpreter:

    .venv\\Scripts\\python.exe scripts\\package_app.py

The result is a self-contained folder under ``dist/`` containing
``StockWise.exe`` (no Python install required on the target machine). The live
database, backups, logs and models still live in ``%LOCALAPPDATA%\\StockWise``.

This script is intentionally explicit about hidden imports and bundled data so
the frozen app behaves like the source app (templates and migrations included).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "0.1.0"

# Libraries imported lazily / by name at runtime that PyInstaller cannot see.
HIDDEN_IMPORTS = [
    "xgboost",
    "sklearn",
    "sklearn.utils._typedefs",
    "pandas",
    "numpy",
    "openpyxl",
    "dotenv",
]

# (source dir, destination name inside the bundle) — read via Config.PROJECT_ROOT.
ADD_DATA = [
    (ROOT / "imports", "imports"),
    (ROOT / "migrations", "migrations"),
]


def main() -> int:
    flet = Path(sys.executable).with_name("flet.exe")
    if not flet.exists():
        print(f"Could not find the flet CLI next to {sys.executable}", file=sys.stderr)
        return 1

    separator = ";" if sys.platform.startswith("win") else ":"

    cmd = [
        str(flet), "pack", str(ROOT / "main.py"),
        "-n", "StockWise",
        "--product-name", "StockWise",
        "--file-description", "Inventory decision support for small retailers",
        "--product-version", VERSION,
        "--company-name", "StockWise",
        "--distpath", str(ROOT / "dist"),
        "-y",
        "--hidden-import", *HIDDEN_IMPORTS,
    ]

    data_args = [f"{src}{separator}{dest}" for src, dest in ADD_DATA if src.exists()]
    if data_args:
        cmd += ["--add-data", *data_args]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode == 0:
        print(f"\nBuilt. Executable under: {ROOT / 'dist'}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
