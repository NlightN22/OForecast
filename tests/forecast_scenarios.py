from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TESTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ForecastScenario:
    name: str
    fixture: str
    rows_in: int
    rows_after_zero_fill: int
    missing_periods: int
    first_period: pd.Timestamp | None
    last_period: pd.Timestamp | None
    next_period: str
    period_freq: str = "MS"
    has_negative_values: bool = False


SCENARIOS = [
    ForecastScenario(
        name="complete_calendar_series",
        fixture="data_complete_periods.txt",
        rows_in=65,
        rows_after_zero_fill=65,
        missing_periods=0,
        first_period=pd.Timestamp(2021, 1, 1),
        last_period=pd.Timestamp(2026, 5, 1),
        next_period="2026-06",
    ),
    ForecastScenario(
        name="missing_periods_with_negative_values",
        fixture="data_missing_periods.txt",
        rows_in=62,
        rows_after_zero_fill=64,
        missing_periods=2,
        first_period=pd.Timestamp(2021, 1, 1),
        last_period=pd.Timestamp(2026, 4, 1),
        next_period="2026-05",
        has_negative_values=True,
    ),
    ForecastScenario(
        name="iso_period_with_space_grouped_numbers",
        fixture="data_iso_periods.txt",
        rows_in=29,
        rows_after_zero_fill=29,
        missing_periods=0,
        first_period=pd.Timestamp(2024, 1, 1),
        last_period=pd.Timestamp(2026, 5, 1),
        next_period="2026-06",
    ),
    ForecastScenario(
        name="quarterly_series",
        fixture="data_quarters.txt",
        rows_in=21,
        rows_after_zero_fill=22,
        missing_periods=1,
        first_period=pd.Timestamp(2021, 1, 1),
        last_period=pd.Timestamp(2026, 4, 1),
        next_period="2026-07",
        period_freq="QS",
    ),
    ForecastScenario(
        name="ordinal_numeric_series",
        fixture="data_ordinal.txt",
        rows_in=24,
        rows_after_zero_fill=24,
        missing_periods=0,
        first_period=None,
        last_period=None,
        next_period="next",
        period_freq=None,
    ),
]

MISSING_PERIODS_WITH_ZERO_FILL = {
    "data_missing_periods.txt": [
        pd.Timestamp(2021, 6, 1),
        pd.Timestamp(2025, 1, 1),
    ],
    "data_quarters.txt": [
        pd.Timestamp(2022, 7, 1),
    ],
}

STABLE_MODEL_SET = [
    "SES_log",
    "SeasonalNaive_y",
    "ETS_log_trend=None_seasonal=None",
    "ETS_log_trend=add_seasonal=None",
]


def read_fixture(name: str) -> str:
    return (TESTS_DIR / name).read_text(encoding="utf-8")
