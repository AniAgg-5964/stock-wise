"""StockWise — application layer (services + DTOs).

The application layer orchestrates repositories, owns transactions, and exposes
task-oriented APIs to the UI. The UI never touches SQL or repositories directly.
"""

from __future__ import annotations
