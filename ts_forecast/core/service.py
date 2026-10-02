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
from .models import HAS_SKTIME, HAS_STATSFORECAST, resolve_allowed_models
from .point_forecast import forecast_next_period
from .seasonality import detect_seasonality
from .season_quality import disqualify_for_short_season, evaluate_plausibility


def next_period_label(df: pd.DataFrame) -> str:
    if "next_label" in df.columns and not df["next_label"].empty:
        return str(df["next_label"].iloc[-1])
    period_freq = infer_period_freq(df)
    if period_freq is None:
        return "next"
    next_start = pd.date_range(df["period_start"].max(), periods=2, freq=period_freq)[-1]
    return next_start.strftime("%Y-%m")


def _target_month(df: pd.DataFrame) -> Optional[int]:
    period_freq = infer_period_freq(df)
    if period_freq is None:
        return None
    next_start = pd.date_range(df["period_start"].max(), periods=2, freq=period_freq)[-1]
    return int(next_start.month)


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

    allowed_models = resolve_allowed_models(cfg.ets_trends, cfg.ets_seasonals, models, use_all, on_log=log)

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

    seasonality = detect_seasonality(df, bt.actual_y, bt.preds_y)
    target_month = _target_month(df)

    short_season_reason: Optional[str] = None
    if target_month is not None and seasonality.confirmed:
        chosen_name, short_season_reason = disqualify_for_short_season(
            seasonality, target_month, bt, chosen_name, all_metrics
        )
        if short_season_reason:
            log(f"plausibility: {short_season_reason}")
            chosen_bt_forecast = bt.preds_y.get(chosen_name, chosen_bt_forecast)

    bt_df = backtest_table(bt.periods, bt.actual_y, chosen_bt_forecast)

    # errors in log1p space for bootstrap intervals
    log_shift = float(df["log_shift"].iloc[-1])
    errors_log = np.log1p(bt.actual_y + log_shift) - np.log1p(
        np.maximum(chosen_bt_forecast + log_shift, 0.0) + 1e-9
    )

    # point forecast + intervals for the next period
    log("intervals: start")
    point_y, point_log, full_y = forecast_next_period(
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

    # Seasonality-aware plausibility check (isolated from model selection/ranking above).
    if target_month is not None:
        plausibility = evaluate_plausibility(
            df,
            cfg,
            chosen_name,
            chosen_bt_forecast,
            short_season_reason,
            target_month,
            seasonality,
            full_y,
            all_metrics,
            bt,
            point_y,
            on_log=log,
            should_abort=should_abort,
        )
        if plausibility.unstable:
            log(f"plausibility: unstable ({'; '.join(plausibility.reasons)})")
        else:
            log("plausibility: ok")
    else:
        plausibility = None
        log("plausibility: skipped (non-calendar series)")

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
        seasonal=seasonality.confirmed,
        plausibility_unstable=bool(plausibility.unstable) if plausibility else False,
        plausibility_reasons=plausibility.reasons if plausibility else [],
    )
