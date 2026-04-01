from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Dict

from statsmodels.tsa.holtwinters import SimpleExpSmoothing, ExponentialSmoothing

try:
    import pmdarima as pm

    HAS_PMDARIMA = True
except Exception:
    HAS_PMDARIMA = False

try:
    from statsforecast import StatsForecast
    from statsforecast.models import MSTL, CrostonSBA, TSB, ADIDA, IMAPA

    HAS_STATSFORECAST = True
except Exception:
    HAS_STATSFORECAST = False

try:
    from sktime.forecasting.tbats import TBATS

    HAS_SKTIME = True
except Exception:
    HAS_SKTIME = False


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


def statsforecast_one_step(
    ds: pd.Series,
    y_train: np.ndarray,
    seasonal_length: int,
) -> Dict[str, float]:
    if not HAS_STATSFORECAST:
        return {}
    if len(y_train) < 3:
        return {}
    df = pd.DataFrame(
        {
            "unique_id": "series",
            "ds": pd.to_datetime(ds),
            "y": y_train,
        }
    )

    models = []
    if len(y_train) >= max(2 * seasonal_length, seasonal_length + 1):
        try:
            models.append(MSTL(season_length=seasonal_length))
        except Exception:
            pass
    try:
        models.append(CrostonSBA())
    except Exception:
        pass
    try:
        models.append(TSB(alpha_d=0.1, alpha_p=0.1))
    except Exception:
        pass
    try:
        models.append(ADIDA())
    except Exception:
        pass
    try:
        models.append(IMAPA())
    except Exception:
        pass
    if not models:
        return {}

    try:
        sf = StatsForecast(models=models, freq="MS")
        fcst = sf.forecast(df=df, h=1)
    except Exception:
        return {}

    out: Dict[str, float] = {}
    for col in fcst.columns:
        if col in ("unique_id", "ds"):
            continue
        try:
            out[f"SF_{col}"] = float(fcst[col].iloc[0])
        except Exception:
            continue
    return out


def tbats_forecast_y(
    y_train: np.ndarray,
    seasonal_periods: int,
    min_n: int,
) -> Optional[float]:
    if not HAS_SKTIME:
        return None
    if len(y_train) < min_n:
        return None
    try:
        series = pd.Series(y_train)
        forecaster = TBATS(seasonal_periods=[seasonal_periods])
        forecaster.fit(series)
        pred = forecaster.predict(fh=[1])
        return float(pred.iloc[0])
    except Exception:
        return None


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
