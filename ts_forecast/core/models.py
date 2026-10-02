from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Dict, Iterable

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


def safe_expm1(x: float, shift: float = 0.0) -> float:
    x = float(np.clip(x, -50, 50))
    return float(np.expm1(x) - shift)


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


def seasonal_naive_y(y_train: np.ndarray, seasonal_periods: int = 12) -> float:
    if len(y_train) > seasonal_periods:
        return float(y_train[-seasonal_periods])
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
        use_seasonal = m > 1 and len(ylog_train) >= (2 * m + 1)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", module=r"pmdarima\..*")
            warnings.filterwarnings("ignore", module=r"statsmodels\..*")
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            model = pm.auto_arima(
                ylog_train,
                seasonal=use_seasonal,
                m=m if use_seasonal else 1,
                stepwise=stepwise,
                suppress_warnings=True,
                error_action="ignore",
                information_criterion="aic",
                max_p=max_pq,
                max_q=max_pq,
                max_P=max_pq_seas if use_seasonal else 0,
                max_Q=max_pq_seas if use_seasonal else 0,
            )
        return float(model.predict(n_periods=1)[0])
    except Exception:
        return float(ylog_train[-1])


def statsforecast_one_step(
    ds: pd.Series,
    y_train: np.ndarray,
    seasonal_length: int,
    freq: Optional[str] = "MS",
    allowed_models: Optional[set[str]] = None,
) -> Dict[str, float]:
    if not HAS_STATSFORECAST:
        return {}
    if len(y_train) < 3:
        return {}
    if freq is None:
        freq = "MS"
    ds_values = pd.to_datetime(ds)
    if pd.isna(ds_values).any():
        ds_values = pd.date_range("2000-01-01", periods=len(y_train), freq=freq)

    df = pd.DataFrame(
        {
            "unique_id": "series",
            "ds": ds_values,
            "y": y_train,
        }
    )

    def want_sf(name: str) -> bool:
        return allowed_models is None or f"SF_{name}" in allowed_models

    models = []
    if len(y_train) >= max(2 * seasonal_length, seasonal_length + 1):
        try:
            if want_sf("MSTL"):
                models.append(MSTL(season_length=seasonal_length))
        except Exception:
            pass
    try:
        if want_sf("CrostonSBA"):
            models.append(CrostonSBA())
    except Exception:
        pass
    try:
        if want_sf("TSB"):
            models.append(TSB(alpha_d=0.1, alpha_p=0.1))
    except Exception:
        pass
    try:
        if want_sf("ADIDA"):
            models.append(ADIDA())
    except Exception:
        pass
    try:
        if want_sf("IMAPA"):
            models.append(IMAPA())
    except Exception:
        pass
    if not models:
        return {}

    try:
        sf = StatsForecast(models=models, freq=freq)
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


def model_catalog(ets_trends: Iterable, ets_seasonals: Iterable) -> list[str]:
    names = ["SES_log", "SeasonalNaive_y"]
    for tr in ets_trends:
        for seas in ets_seasonals:
            names.append(f"ETS_log_trend={tr}_seasonal={seas}")
    names.append("AutoARIMA_log")
    names.extend(["SF_MSTL", "SF_CrostonSBA", "SF_TSB", "SF_ADIDA", "SF_IMAPA"])
    names.append("TBATS_y")
    return names


def should_use_model(allowed_models: Optional[set[str]], name: str) -> bool:
    return allowed_models is None or name in allowed_models


def resolve_allowed_models(
    ets_trends: Iterable,
    ets_seasonals: Iterable,
    models: Optional[list[str]],
    use_all: bool,
    on_log=None,
) -> Optional[set[str]]:
    """Resolve the client-requested model list into an allowed-model set,
    dropping unknown names and names unavailable in this environment."""

    def log(msg: str) -> None:
        if on_log is not None:
            on_log(msg)

    all_models = set(model_catalog(ets_trends, ets_seasonals))
    if use_all or not models:
        allowed: Optional[set[str]] = None
    else:
        requested = [m for m in models if m in all_models]
        unknown = [m for m in models if m not in all_models]
        if unknown:
            log(f"models: ignoring unknown: {', '.join(unknown)}")
        allowed = set(requested) if requested else None
        if allowed is None:
            log("models: none selected, using all")

    if allowed is not None:
        if not HAS_PMDARIMA and "AutoARIMA_log" in allowed:
            allowed.discard("AutoARIMA_log")
            log("models: AutoARIMA_log skipped (pmdarima unavailable)")
        if not HAS_STATSFORECAST:
            sf_removed = {m for m in allowed if m.startswith("SF_")}
            if sf_removed:
                allowed.difference_update(sf_removed)
                log("models: statsforecast models skipped (unavailable)")
        if not HAS_SKTIME and "TBATS_y" in allowed:
            allowed.discard("TBATS_y")
            log("models: TBATS_y skipped (sktime unavailable)")
        if not allowed:
            log("models: no available selections, using all")
            allowed = None

    return allowed


def tbats_forecast_y(
    y_train: np.ndarray,
    seasonal_periods: int,
    min_n: int,
) -> tuple[Optional[float], Optional[str]]:
    if not HAS_SKTIME:
        return None, "sktime not available"
    if len(y_train) < min_n:
        return None, f"n<{min_n}"
    try:
        series = pd.Series(y_train)
        forecaster = TBATS(sp=[seasonal_periods])
        forecaster.fit(series)
        pred = forecaster.predict(fh=[1])
        return float(pred.iloc[0]), None
    except Exception as exc:
        return None, str(exc)


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
