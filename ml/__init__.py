"""StockWise — ML / forecasting pipeline.

This package is deliberately isolated: the application layer reaches it only
through ``ForecastService``, and the UI never imports it directly.

Modules:
    data_validation — sanity checks on demand inputs
    preprocessing   — clean, contiguous daily grid per product
    features        — leakage-safe lag / rolling / calendar features
    baseline        — seasonal-naive, moving-average and mean baselines
    evaluate        — MAE / RMSE / WAPE / bias
    train           — XGBoost training (admin/developer operation)
    predict         — inference + fallback selection
    artifacts       — model + metadata persistence

Forecasting never mutates stock. Baselines are deterministic; the XGBoost model
is only adopted when it beats or matches the baseline on a chronological holdout.
"""
