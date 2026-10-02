from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd

from ..io.parsing import infer_period_freq, period_seasonal_length
from .config import ForecastConfig
from .models import (
    HAS_PMDARIMA,
    HAS_SKTIME,
    arima_forecast_log,
    ets_forecast_log,
    safe_expm1,
    seasonal_naive_y,
    ses_forecast_log,
    should_use_model,
    statsforecast_one_step,
    tbats_forecast_y,
    winsorize_log,
)


def forecast_next_period(
    df: pd.DataFrame,
    cfg: ForecastConfig,
    robust: bool,
    chosen_name: str,
    metrics: dict,
    allowed_models: Optional[set[str]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> tuple[float, float, dict[str, float]]:
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
                full_y[name] = safe_expm1(ets_forecast_log(ylog_train, tr, seas, sp), log_shift)

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

    return point, float(np.log1p(max(point + log_shift, 0.0))), full_y
