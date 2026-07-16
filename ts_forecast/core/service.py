from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd

from .config import ForecastConfig
from ..io.parsing import (
    add_transforms,
    fill_missing_periods,
    infer_period_freq,
    period_seasonal_length,
    read_tsv_like,
)
from .backtest import choose_dataset
from .ensemble import build_ensemble_or_best
from .intervals import bootstrap_intervals_log1p
from .result import (
    ForecastResult,
    backtest_table,
    ensemble_top_models,
    format_result_text,
)
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
    model_catalog,
    should_use_model,
)

__all__ = ["format_result_text", "next_period_label", "run_forecast"]


def next_period_label(df: pd.DataFrame) -> str:
    if "next_label" in df.columns and not df["next_label"].empty:
        return str(df["next_label"].iloc[-1])
    period_freq = infer_period_freq(df)
    if period_freq is None:
        return "next"
    next_start = pd.date_range(df["period_start"].max(), periods=2, freq=period_freq)[
        -1
    ]
    return next_start.strftime("%Y-%m")


def forecast_next_period(
    df: pd.DataFrame,
    cfg: ForecastConfig,
    robust: bool,
    chosen_name: str,
    metrics: dict,
    allowed_models: Optional[set[str]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> tuple[float, float]:
    def log(msg: str) -> None:
        if on_log is not None:
            on_log(msg)

    y_full = df["y"].to_numpy(float)
    ylog_full = df["y_log"].to_numpy(float)
    log_shift = float(df["log_shift"].iloc[-1])
    period_freq = infer_period_freq(df)
    seasonal_length = period_seasonal_length(df)
    ylog_train = (
        winsorize_log(ylog_full, cfg.winsor_q_low, cfg.winsor_q_high)
        if robust
        else ylog_full
    )

    # produce single-step forecasts for all models (needed for ensemble)
    full_y = {}

    # SES
    if should_use_model(allowed_models, "SES_log"):
        full_y["SES_log"] = safe_expm1(ses_forecast_log(ylog_train), log_shift)

    # ETS grid
    use_seasonal = len(ylog_train) >= cfg.ets_seasonal_min_n
    for tr in cfg.ets_trends:
        for seas in cfg.ets_seasonals:
            if seas is not None and not use_seasonal:
                continue
            sp = cfg.ets_seasonal_periods if seas is not None else None
            name = f"ETS_log_trend={tr}_seasonal={seas}"
            if should_use_model(allowed_models, name):
                full_y[name] = safe_expm1(
                    ets_forecast_log(ylog_train, tr, seas, sp), log_shift
                )

    # Seasonal naive
    if should_use_model(allowed_models, "SeasonalNaive_y"):
        full_y["SeasonalNaive_y"] = seasonal_naive_y(y_full, seasonal_length)

    # ARIMA
    if HAS_PMDARIMA and should_use_model(allowed_models, "AutoARIMA_log"):
        a = arima_forecast_log(
            ylog_train,
            seasonal_length,
            cfg.arima_stepwise,
            cfg.arima_max_pq,
            cfg.arima_max_pq_seas,
        )
        if a is not None:
            full_y["AutoARIMA_log"] = safe_expm1(a, log_shift)

    # StatsForecast (y)
    sf = statsforecast_one_step(
        df["period_start"],
        y_full,
        seasonal_length,
        freq=period_freq,
        allowed_models=allowed_models,
    )
    for name, value in sf.items():
        full_y[name] = value

    # TBATS (y)
    if should_use_model(allowed_models, "TBATS_y"):
        tb, tb_err = tbats_forecast_y(
            y_full, cfg.tbats_seasonal_periods, cfg.tbats_min_n
        )
        if tb is not None:
            full_y["TBATS_y"] = tb
        elif HAS_SKTIME and len(y_full) >= cfg.tbats_min_n:
            log(f"sktime.tbats: failed ({tb_err})")

    # chosen point forecast
    if chosen_name == "Ensemble_top3_weighted":
        ranked = sorted(
            (
                (m, metrics[m]["MAE"])
                for m in metrics.keys()
                if m != "Ensemble_top3_weighted"
            ),
            key=lambda x: x[1],
        )
        top = [m for m, _ in ranked[: cfg.ensemble_topk]]
        w = np.array([1.0 / max(metrics[m]["MAE"], 1e-9) for m in top], float)
        w = w / w.sum()
        point = float(sum(wi * full_y[m] for wi, m in zip(w, top)))
    else:
        point = float(full_y[chosen_name])

    return point, float(np.log1p(max(point + log_shift, 0.0)))


def run_forecast(
    raw: str,
    cfg: ForecastConfig = ForecastConfig(),
    on_log: Optional[Callable[[str], None]] = None,
    models: Optional[list[str]] = None,
    use_all: bool = True,
    fill_missing_with_mean: bool = False,
    should_abort: Optional[Callable[[], bool]] = None,
) -> ForecastResult:
    def log(msg: str) -> None:
        if on_log is not None:
            on_log(msg)

    def check_abort() -> None:
        if should_abort is not None and should_abort():
            raise RuntimeError("aborted")

    check_abort()
    log("parse: start")
    df0 = read_tsv_like(raw)
    log(f"parse: ok rows={len(df0)}")
    if len(df0) > cfg.max_rows:
        raise ValueError(f"too many rows: {len(df0)} (max {cfg.max_rows})")
    period_freq = infer_period_freq(df0)
    df1, miss_n = fill_missing_periods(df0, fill_missing_with_mean)
    mode = "interpolate" if fill_missing_with_mean else "zero"
    log(
        f"fill_missing_periods: freq={period_freq or 'ordinal'} mode={mode} "
        f"missing={miss_n} rows_after_fill={len(df1)}"
    )
    df = add_transforms(df1)
    log("transforms: ok")
    check_abort()

    all_models = set(model_catalog(cfg.ets_trends, cfg.ets_seasonals))
    if use_all or not models:
        allowed_models = None
    else:
        requested = [m for m in models if m in all_models]
        unknown = [m for m in (models or []) if m not in all_models]
        if unknown:
            log(f"models: ignoring unknown: {', '.join(unknown)}")
        if not requested:
            log("models: none selected, using all")
            allowed_models = None
        else:
            allowed_models = set(requested)

    if allowed_models is not None:
        if not HAS_PMDARIMA and "AutoARIMA_log" in allowed_models:
            allowed_models.discard("AutoARIMA_log")
            log("models: AutoARIMA_log skipped (pmdarima unavailable)")
        if not HAS_STATSFORECAST:
            sf_removed = {m for m in allowed_models if m.startswith("SF_")}
            if sf_removed:
                allowed_models.difference_update(sf_removed)
                log("models: statsforecast models skipped (unavailable)")
        if not HAS_SKTIME and "TBATS_y" in allowed_models:
            allowed_models.discard("TBATS_y")
            log("models: TBATS_y skipped (sktime unavailable)")
        if not allowed_models:
            log("models: no available selections, using all")
            allowed_models = None

    log("backtest: start")
    if not HAS_STATSFORECAST:
        log("statsforecast: unavailable (optional)")
    else:
        if len(df) < 3:
            log("statsforecast: skipped (n<3)")
        else:
            seasonal_length = period_seasonal_length(df)
            mstl_min_n = max(2 * seasonal_length, seasonal_length + 1)
            if len(df) < mstl_min_n:
                log(f"statsforecast: MSTL skipped (n<{mstl_min_n})")
    if not HAS_SKTIME:
        log("sktime.tbats: unavailable (optional)")
    else:
        if len(df) < cfg.tbats_min_n:
            log(f"sktime.tbats: skipped (n<{cfg.tbats_min_n})")
    ds_name, bt = choose_dataset(
        df,
        cfg,
        allowed_models=allowed_models,
        on_log=log,
        should_abort=should_abort,
    )
    robust = ds_name != "A_raw"
    log(f"backtest: chosen_dataset={ds_name}")
    check_abort()

    log("ensemble: start")
    chosen_name, chosen_bt_forecast, all_metrics = build_ensemble_or_best(
        actual_y=bt.actual_y,
        preds_y=bt.preds_y,
        topk=cfg.ensemble_topk,
        max_degradation=cfg.ensemble_max_degradation,
    )
    log(f"ensemble: chosen_model={chosen_name}")
    check_abort()
    ensemble_models = []
    if "Ensemble_top3_weighted" in all_metrics:
        ensemble_models = ensemble_top_models(all_metrics, cfg.ensemble_topk)

    bt_df = backtest_table(bt.periods, bt.actual_y, chosen_bt_forecast)

    # errors in log1p space for bootstrap intervals
    log_shift = float(df["log_shift"].iloc[-1])
    errors_log = np.log1p(bt.actual_y + log_shift) - np.log1p(
        np.maximum(chosen_bt_forecast + log_shift, 0.0) + 1e-9
    )

    # point forecast + intervals for the next period
    log("intervals: start")
    point_y, point_log = forecast_next_period(
        df,
        cfg,
        robust,
        chosen_name,
        all_metrics,
        allowed_models=allowed_models,
        on_log=log,
    )
    intervals = bootstrap_intervals_log1p(
        errors_log,
        point_log,
        cfg.bootstrap_n,
        cfg.seed,
        log_shift=log_shift,
    )
    _ = point_y
    log("intervals: ok")
    check_abort()

    next_period = next_period_label(df)

    metrics_df = pd.DataFrame(all_metrics).T.sort_values("MAE")

    log("done")
    return ForecastResult(
        rows_in=len(df0),
        rows_after_fill=len(df1),
        missing_periods_filled=miss_n,
        chosen_dataset=ds_name,
        chosen_model=chosen_name,
        ensemble_models=ensemble_models,
        metrics=metrics_df,
        backtest=bt_df,
        next_period=next_period,
        intervals=intervals,
    )
