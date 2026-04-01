from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict

from statsmodels.tsa.holtwinters import SimpleExpSmoothing, ExponentialSmoothing

try:
    import pmdarima as pm

    HAS_PMDARIMA = True
except Exception:
    HAS_PMDARIMA = False


@dataclass(frozen=True)
class ModelSpec:
    name: str


def winsorize_log(ylog: np.ndarray, q_low: float, q_high: float) -> np.ndarray:
    lo, hi = np.quantile(ylog, [q_low, q_high])
    return np.clip(ylog, lo, hi)


def safe_expm1(x: float) -> float:
    x = float(np.clip(x, -50, 50))
    return float(np.expm1(x))


def ses_forecast_log(ylog_train: np.ndarray) -> float:
    try:
        fit = SimpleExpSmoothing(ylog_train, initialization_method="estimated").fit(
            optimized=True
        )
        return float(fit.forecast(1)[0])
    except Exception:
        return float(ylog_train[-1])


def ets_forecast_log(
    ylog_train: np.ndarray, trend, seasonal, seasonal_periods: Optional[int]
) -> float:
    try:
        fit = ExponentialSmoothing(
            ylog_train,
            trend=trend,
            seasonal=seasonal,
            seasonal_periods=seasonal_periods,
            initialization_method="estimated",
        ).fit(optimized=True)
        return float(fit.forecast(1)[0])
    except Exception:
        return float(ylog_train[-1])


def seasonal_naive_y(y_train: np.ndarray) -> float:
    if len(y_train) >= 13:
        return float(y_train[-12])
    return float(y_train[-1])


def arima_forecast_log(
    ylog_train: np.ndarray,
    m: int,
    stepwise: bool,
    max_pq: int,
    max_pq_seas: int,
) -> Optional[float]:
    if not HAS_PMDARIMA:
        return None
    try:
        model = pm.auto_arima(
            ylog_train,
            seasonal=True,
            m=m,
            stepwise=stepwise,
            suppress_warnings=True,
            error_action="ignore",
            information_criterion="aic",
            max_p=max_pq,
            max_q=max_pq,
            max_P=max_pq_seas,
            max_Q=max_pq_seas,
        )
        return float(model.predict(n_periods=1)[0])
    except Exception:
        return float(ylog_train[-1])


def available_model_names(
    n_train: int,
    ets_trends: tuple,
    ets_seasonals: tuple,
    ets_seasonal_periods: int,
    ets_seasonal_min_n: int,
    include_arima: bool,
) -> list[str]:
    names = ["SES_log", "SeasonalNaive_y"]
    use_seasonal = n_train >= ets_seasonal_min_n
    for tr in ets_trends:
        for seas in ets_seasonals:
            if seas is not None and not use_seasonal:
                continue
            names.append(f"ETS_log_trend={tr}_seasonal={seas}")
    if include_arima and HAS_PMDARIMA:
        names.append("AutoARIMA_log")
    return names
