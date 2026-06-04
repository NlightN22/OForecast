from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ForecastResult:
    rows_in: int
    rows_after_fill: int
    missing_periods_filled: int
    chosen_dataset: str
    chosen_model: str
    ensemble_models: list[str]
    metrics: pd.DataFrame
    backtest: pd.DataFrame
    next_period: str
    intervals: dict[str, float]


def format_period(value: object) -> str:
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m")
    if pd.isna(value):
        return "unknown"
    return str(value)


def backtest_table(periods, actual, forecast) -> pd.DataFrame:
    err = forecast - actual
    abs_err = np.abs(err)
    ape = np.where(actual > 0, 100.0 * abs_err / actual, np.nan)
    return pd.DataFrame(
        {
            "period": [format_period(period) for period in periods],
            "actual": actual,
            "forecast": forecast,
            "error": err,
            "abs_error": abs_err,
            "ape%": ape,
        }
    )


def ensemble_top_models(metrics: dict, topk: int) -> list[str]:
    ranked = sorted(
        ((m, v["MAE"]) for m, v in metrics.items() if m != "Ensemble_top3_weighted"),
        key=lambda x: x[1],
    )
    return [m for m, _ in ranked[:topk]]


def format_result_text(res: ForecastResult) -> str:
    parts = [
        "=== DATA ===",
        (
            f"rows_in={res.rows_in} rows_after_fill={res.rows_after_fill} "
            f"missing_periods_filled={res.missing_periods_filled}"
        ),
        f"chosen_dataset={res.chosen_dataset}",
        "",
        "=== METRICS ===",
        format_table(res.metrics, index=True),
        "",
        "=== CHOSEN_FORECAST_FOR_REPORTING ===",
        chosen_model_text(res),
        "",
        "=== BACKTEST_TABLE ===",
        format_table(res.backtest, index=False),
        "",
        "=== FINAL_FORECAST_NEXT_PERIOD ===",
        f"next_period={res.next_period}",
        format_table(res.intervals, index=False),
        "",
    ]
    return "\n".join(parts)


def chosen_model_text(res: ForecastResult) -> str:
    if res.chosen_model == "Ensemble_top3_weighted" and res.ensemble_models:
        return f"{res.chosen_model} (models: {', '.join(res.ensemble_models)})"
    return res.chosen_model


def format_number(value: object) -> object:
    if isinstance(value, (int, float, np.floating)) and not isinstance(value, bool):
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return value
        return f"{value:,.2f}".replace(",", " ")
    return value


def as_df(value: object) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        df = value.copy()
    elif isinstance(value, dict):
        df = pd.DataFrame([value])
    else:
        df = pd.DataFrame(value)
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].map(format_number)
    return df


def format_table(value: object, index: bool = False) -> str:
    df = as_df(value).copy()
    if index:
        idx_name = df.index.name or "index"
        df.insert(0, idx_name, df.index.astype(str))

    cols = [str(c) for c in df.columns]
    rows = [[str(v) for v in row] for row in df.to_numpy()]
    widths = [len(c) for c in cols]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    header = " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols))
    sep = "-+-".join("-" * widths[i] for i in range(len(widths)))
    lines = [header, sep]
    for row in rows:
        lines.append(" | ".join(row[i].rjust(widths[i]) for i in range(len(widths))))
    return "\n".join(lines)
