import pandas as pd

from src.weekly_data_update import (
    BENCHMARK_SHEET,
    FX_SHEET,
    MARKET_SHEET,
    OPPORTUNITY_COLUMNS,
    OPPORTUNITY_SHEET,
    SNAPSHOT_COLUMNS,
    SNAPSHOT_SHEET,
    validate_weekly_data,
)


def test_weekly_template_validation_accepts_aligned_core_data():
    date = pd.Timestamp("2026-10-09")
    snapshot = pd.DataFrame([{column: None for column in SNAPSHOT_COLUMNS}])
    snapshot.loc[0, "id"] = "A Equity"
    snapshot.loc[0, "as_of_date"] = date
    sheets = {
        MARKET_SHEET: pd.DataFrame(
            {"date": [date], "id": ["A Equity"], "px_last": [100.0], "volume": [10.0]}
        ),
        BENCHMARK_SHEET: pd.DataFrame({"date": [date], "px_last": [1000.0]}),
        SNAPSHOT_SHEET: snapshot,
        FX_SHEET: pd.DataFrame(columns=["date", "currency", "usd_rate"]),
        OPPORTUNITY_SHEET: pd.DataFrame(columns=OPPORTUNITY_COLUMNS),
    }

    checks = validate_weekly_data(sheets)

    assert not checks["status"].eq("ERROR").any()
    assert checks["status"].eq("WARNING").any()
