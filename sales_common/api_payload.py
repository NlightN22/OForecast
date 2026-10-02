from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ForecastTask:
    forecast_level: str
    manager: str
    brand: str
    raw: str


def format_number_for_api(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def rows_to_raw(rows: dict[pd.Timestamp, float], drop_zero_rows: bool) -> str:
    lines = [
        f"{period.strftime('%Y-%m')}\t{format_number_for_api(value)}"
        for period, value in sorted(rows.items())
        if not drop_zero_rows or value != 0
    ]
    return "\n".join(lines)
