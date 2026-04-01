from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd

from .config import ForecastConfig
from ..io.parsing import read_tsv_like, fill_missing_months, add_transforms
from .backtest import choose_dataset
from .ensemble import build_ensemble_or_best
from .intervals import bootstrap_intervals_log1p
from .models import (
    winsorize_log,
    safe_expm1,
    ses_forecast_log,
    ets_forecast_log,
    seasonal_naive_y,
    arima_forecast_log,
    HAS_PMDARIMA,
    HAS_STATSFORECAST,
    statsforecast_one_step,
    HAS_SKTIME,
    tbats_forecast_y,
)


def format_month(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m")


def backtest_table(months, actual, forecast) -> pd.DataFrame:
    err = forecast - actual
    abs_err = np.abs(err)
    ape = np.where(actual > 0, 100.0 * abs_err / actual, np.nan)
    return pd.DataFrame(
        {
            "month": [format_month(m) for m in months],
            "actual": actual,
            "forecast": forecast,
            "error": err,
            "abs_error": abs_err,
            "ape%": ape,
        }
    )


def forecast_next_month(
    df: pd.DataFrame,
    cfg: ForecastConfig,
    robust: bool,
    chosen_name: str,
    metrics: dict,
    on_log: Optional[Callable[[str], None]] = None,
) -> tuple[float, float]:
    def log(msg: str) -> None:
        if on_log is not None:
            on_log(msg)

    y_full = df["y"].to_numpy(float)
    ylog_full = df["y_log"].to_numpy(float)
    ylog_train = (
        winsorize_log(ylog_full, cfg.winsor_q_low, cfg.winsor_q_high)
        if robust
        else ylog_full
    )

    # produce single-step forecasts for all models (needed for ensemble)
    full_y = {}

    # SES
    full_y["SES_log"] = safe_expm1(ses_forecast_log(ylog_train))

    # ETS grid
    use_seasonal = len(ylog_train) >= cfg.ets_seasonal_min_n
    for tr in cfg.ets_trends:
        for seas in cfg.ets_seasonals:
            if seas is not None and not use_seasonal:
                continue
            sp = cfg.ets_seasonal_periods if seas is not None else None
            name = f"ETS_log_trend={tr}_seasonal={seas}"
            full_y[name] = safe_expm1(ets_forecast_log(ylog_train, tr, seas, sp))

    # Seasonal naive
    full_y["SeasonalNaive_y"] = seasonal_naive_y(y_full)

    # ARIMA
    if HAS_PMDARIMA:
        a = arima_forecast_log(
            ylog_train, cfg.arima_m, cfg.arima_stepwise, cfg.arima_max_pq, cfg.arima_max_pq_seas
        )
        if a is not None:
            full_y["AutoARIMA_log"] = safe_expm1(a)

    # StatsForecast (y)
    sf = statsforecast_one_step(df["month"], y_full, cfg.statsforecast_seasonal_length)
    for name, value in sf.items():
        full_y[name] = value

    # TBATS (y)
    tb, tb_err = tbats_forecast_y(y_full, cfg.tbats_seasonal_periods, cfg.tbats_min_n)
    if tb is not None:
        full_y["TBATS_y"] = tb
    elif HAS_SKTIME and len(y_full) >= cfg.tbats_min_n:
        log(f"sktime.tbats: failed ({tb_err})")

    # chosen point forecast
    if chosen_name == "Ensemble_top3_weighted":
        ranked = sorted(
            ((m, metrics[m]["MAE"]) for m in metrics.keys() if m != "Ensemble_top3_weighted"),
            key=lambda x: x[1],
        )
        top = [m for m, _ in ranked[: cfg.ensemble_topk]]
        w = np.array([1.0 / max(metrics[m]["MAE"], 1e-9) for m in top], float)
        w = w / w.sum()
        point = float(sum(wi * full_y[m] for wi, m in zip(w, top)))
    else:
        point = float(full_y[chosen_name])

    return point, float(np.log1p(max(point, 0.0)))


@dataclass(frozen=True)
class ForecastResult:
    rows_in: int
    rows_after_fill: int
    missing_months_filled: int
    chosen_dataset: str
    chosen_model: str
    metrics: pd.DataFrame
    backtest: pd.DataFrame
    next_month: str
    intervals: pd.DataFrame


def run_forecast(
    raw: str,
    cfg: ForecastConfig = ForecastConfig(),
    on_log: Optional[Callable[[str], None]] = None,
) -> ForecastResult:
    def log(msg: str) -> None:
        if on_log is not None:
            on_log(msg)

    log("parse: start")
    df0 = read_tsv_like(raw)
    log(f"parse: ok rows={len(df0)}")
    df1, miss_n = fill_missing_months(df0)
    log(f"fill_missing_months: missing={miss_n} rows_after_fill={len(df1)}")
    df = add_transforms(df1)
    log("transforms: ok")

    log("backtest: start")
    if not HAS_STATSFORECAST:
        log("statsforecast: unavailable (optional)")
    else:
        if len(df) < 3:
            log("statsforecast: skipped (n<3)")
        else:
            mstl_min_n = max(2 * cfg.statsforecast_seasonal_length, cfg.statsforecast_seasonal_length + 1)
            if len(df) < mstl_min_n:
                log(f"statsforecast: MSTL skipped (n<{mstl_min_n})")
    if not HAS_SKTIME:
        log("sktime.tbats: unavailable (optional)")
    else:
        if len(df) < cfg.tbats_min_n:
            log(f"sktime.tbats: skipped (n<{cfg.tbats_min_n})")
    ds_name, bt = choose_dataset(df, cfg)
    robust = ds_name != "A_raw"
    log(f"backtest: chosen_dataset={ds_name}")

    log("ensemble: start")
    chosen_name, chosen_bt_forecast, all_metrics = build_ensemble_or_best(
        actual_y=bt.actual_y,
        preds_y=bt.preds_y,
        topk=cfg.ensemble_topk,
        max_degradation=cfg.ensemble_max_degradation,
    )
    log(f"ensemble: chosen_model={chosen_name}")

    bt_df = backtest_table(bt.months, bt.actual_y, chosen_bt_forecast)

    # errors in log1p space for bootstrap intervals
    errors_log = np.log1p(bt.actual_y) - np.log1p(np.maximum(chosen_bt_forecast, 0.0) + 1e-9)

    # point forecast + intervals for next month
    log("intervals: start")
    point_y, point_log = forecast_next_month(df, cfg, robust, chosen_name, all_metrics, on_log=log)
    intervals = bootstrap_intervals_log1p(errors_log, point_log, cfg.bootstrap_n, cfg.seed)
    _ = point_y
    log("intervals: ok")

    next_month = df["month"].max() + pd.offsets.MonthBegin(1)

    metrics_df = pd.DataFrame(all_metrics).T.sort_values("MAE")

    log("done")
    return ForecastResult(
        rows_in=len(df0),
        rows_after_fill=len(df1),
        missing_months_filled=miss_n,
        chosen_dataset=ds_name,
        chosen_model=chosen_name,
        metrics=metrics_df,
        backtest=bt_df,
        next_month=format_month(next_month),
        intervals=intervals,
    )


def format_result_text(res: ForecastResult) -> str:
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

    parts = []
    parts.append("=== DATA ===")
    parts.append(
        f"rows_in={res.rows_in} rows_after_fill={res.rows_after_fill} missing_months_filled={res.missing_months_filled}"
    )
    parts.append(f"chosen_dataset={res.chosen_dataset}")
    parts.append("")

    parts.append("=== METRICS ===")
    parts.append(format_table(res.metrics, index=True))
    parts.append("")

    parts.append("=== CHOSEN_FORECAST_FOR_REPORTING ===")
    parts.append(res.chosen_model)
    parts.append("")

    parts.append("=== BACKTEST_TABLE ===")
    parts.append(format_table(res.backtest, index=False))
    parts.append("")

    parts.append("=== FINAL_FORECAST_NEXT_MONTH ===")
    parts.append(f"next_month={res.next_month}")
    parts.append(format_table(res.intervals, index=False))
    parts.append("")

    return "\n".join(parts)
