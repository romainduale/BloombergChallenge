from pathlib import Path

import pandas as pd

HORIZON_WEEKS = 4
TARGET_4W = "future_excess_return_4w"
CHALLENGE_END_DATE = pd.Timestamp("2026-11-13")
FINAL_SIGNAL_DATE = pd.Timestamp("2026-10-16")

OUTPUT_ROOT = Path("data/processed/strategies/final_four_week")
PANEL_PATH = OUTPUT_ROOT / "features_4w.csv.gz"
SIGNAL_PATH = OUTPUT_ROOT / "latest_signal_4w.csv"
COEFFICIENTS_PATH = OUTPUT_ROOT / "model_coefficients_4w.csv"
CORE_PORTFOLIO_PATH = OUTPUT_ROOT / "core_80_source_portfolio_4w.csv"
COMBINED_ALLOCATION_PATH = OUTPUT_ROOT / "allocation_80_20.csv"
ORDERS_PATH = OUTPUT_ROOT / "execution_orders.csv"
FINAL_CSV_PATH = OUTPUT_ROOT / "final_allocation_explained.csv"
MANIFEST_PATH = OUTPUT_ROOT / "run_manifest.json"

FEATURE_LABELS = {
    "mom_1m_rank": "momentum_1m",
    "mom_3m_rank": "momentum_3m",
    "mom_6m_rank": "momentum_6m",
    "volatility_13w_rank": "volatility_13w",
    "abnormal_volume_13w_rank": "abnormal_volume_13w",
    "distance_52w_high_rank": "distance_52w_high",
}
