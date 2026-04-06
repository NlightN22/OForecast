from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable

from .config import ForecastConfig
from .models import (
    winsorize_log,
    safe_expm1,
    ses_forecast_log,
    ets_forecast_log,
    seasonal_naive_y,
    arima_forecast_log,
    HAS_PMDARIMA,
    HAS_STATSFORECAST,
    HAS_SKTIME,
    statsforecast_one_step,
    tbats_forecast_y,
    should_use_model,
)

@dataclass
class BacktestResult:
    months: List[pd.Timestamp]
    actual_y: np.ndarray
    preds_y: Dict[str, np.ndarray]  # model -> y-space preds
    diagnostics: Dict[str, str]

def _test_len(n: int, cfg: ForecastConfig) -> int:
    return cfg.test_len_if_ge_48 if n >= 48 else cfg.test_len_else

def walk_forward(
    df: pd.DataFrame,
    cfg: ForecastConfig,
    robust: bool,
    include_arima: bool = True,
    allowed_models: Optional[set[str]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> BacktestResult:
    n = len(df)
    tlen = _test_len(n, cfg)
    start = n - tlen

    months: List[pd.Timestamp] = []
    actual: List[float] = []
    preds: Dict[str, List[float]] = {}
    diagnostics: Dict[str, str] = {}
    tbats_fail_count = 0
    tbats_err: Optional[str] = None

    for i in range(start, n):
        if should_abort is not None and should_abort():
            raise RuntimeError("aborted")
        if on_log is not None and (i == start or (i - start) % 2 == 0):
            on_log(f"backtest: step {i - start + 1}/{tlen} (train={i})")
        train = df.iloc[:i]
        y_train = train["y"].to_numpy(dtype=float)
        ylog_train = train["y_log"].to_numpy(dtype=float)

        if robust:
            ylog_train = winsorize_log(ylog_train, cfg.winsor_q_low, cfg.winsor_q_high)

        # SES(log)
        if should_use_model(allowed_models, "SES_log"):
            f_log = ses_forecast_log(ylog_train)
            preds.setdefault("SES_log", []).append(safe_expm1(f_log))

        # ETS(log) grid
        use_seasonal = len(ylog_train) >= cfg.ets_seasonal_min_n
        for tr in cfg.ets_trends:
            for seas in cfg.ets_seasonals:
                if seas is not None and not use_seasonal:
                    continue
                sp = cfg.ets_seasonal_periods if seas is not None else None
                name = f"ETS_log_trend={tr}_seasonal={seas}"
                if should_use_model(allowed_models, name):
                    f = ets_forecast_log(ylog_train, tr, seas, sp)
                    preds.setdefault(name, []).append(safe_expm1(f))

        # Seasonal naive (y)
        if should_use_model(allowed_models, "SeasonalNaive_y"):
            preds.setdefault("SeasonalNaive_y", []).append(seasonal_naive_y(y_train))

        # ARIMA(log) optional
        if include_arima and HAS_PMDARIMA and should_use_model(allowed_models, "AutoARIMA_log"):
            a = arima_forecast_log(
                ylog_train,
                m=cfg.arima_m,
                stepwise=cfg.arima_stepwise,
                max_pq=cfg.arima_max_pq,
                max_pq_seas=cfg.arima_max_pq_seas,
            )
            if a is not None:
                preds.setdefault("AutoARIMA_log", []).append(safe_expm1(a))
        elif include_arima and should_use_model(allowed_models, "AutoARIMA_log") and not HAS_PMDARIMA:
            diagnostics.setdefault("AutoARIMA_log", "pmdarima unavailable")

        # StatsForecast (y)
        if HAS_STATSFORECAST:
            sf = statsforecast_one_step(
                train["month"],
                y_train,
                cfg.statsforecast_seasonal_length,
                allowed_models=allowed_models,
            )
            for name, value in sf.items():
                preds.setdefault(name, []).append(value)
        elif allowed_models is not None:
            if any(name.startswith("SF_") for name in allowed_models):
                diagnostics.setdefault("SF_*", "statsforecast unavailable")

        # TBATS (y)
        if should_use_model(allowed_models, "TBATS_y"):
            tb, tb_err = tbats_forecast_y(y_train, cfg.tbats_seasonal_periods, cfg.tbats_min_n)
            if tb is not None:
                preds.setdefault("TBATS_y", []).append(tb)
            else:
                tbats_fail_count += 1
                if tb_err:
                    tbats_err = tb_err

        months.append(df.loc[i, "month"])
        actual.append(float(df.loc[i, "y"]))

    if should_use_model(allowed_models, "TBATS_y") and tbats_fail_count:
        if not HAS_SKTIME:
            diagnostics.setdefault("TBATS_y", "sktime unavailable")
        elif tbats_err:
            diagnostics.setdefault(
                "TBATS_y",
                f"failed in {tbats_fail_count}/{len(months)} windows: {tbats_err}",
            )

    preds_np = {k: np.asarray(v, dtype=float) for k, v in preds.items()}
    expected_len = len(actual)
    if preds_np:
        filtered: Dict[str, np.ndarray] = {}
        for name, values in preds_np.items():
            if len(values) != expected_len:
                diagnostics.setdefault(
                    name,
                    f"dropped: preds_len={len(values)} expected={expected_len}",
                )
                continue
            filtered[name] = values
        preds_np = filtered
    return BacktestResult(
        months=months,
        actual_y=np.asarray(actual, dtype=float),
        preds_y=preds_np,
        diagnostics=diagnostics,
    )

def choose_dataset(
    df: pd.DataFrame,
    cfg: ForecastConfig,
    allowed_models: Optional[set[str]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> tuple[str, BacktestResult]:
    bt_a = walk_forward(
        df,
        cfg,
        robust=False,
        include_arima=True,
        allowed_models=allowed_models,
        on_log=on_log,
        should_abort=should_abort,
    )
    bt_b = walk_forward(
        df,
        cfg,
        robust=True,
        include_arima=True,
        allowed_models=allowed_models,
        on_log=on_log,
        should_abort=should_abort,
    )

    if not bt_a.preds_y and not bt_b.preds_y:
        selected = sorted(allowed_models or [])
        diag = {**bt_a.diagnostics, **bt_b.diagnostics}
        diag_msg = "; ".join(f"{k}={v}" for k, v in diag.items()) if diag else "none"
        raise ValueError(
            "no backtest predictions available "
            f"(selected={selected}, n={len(df)}, diagnostics={diag_msg})"
        )
    if not bt_a.preds_y:
        return "B_robust_winsor_log1p", bt_b
    if not bt_b.preds_y:
        return "A_raw", bt_a

    best_mae_a = min(np.mean(np.abs(bt_a.actual_y - p)) for p in bt_a.preds_y.values())
    best_mae_b = min(np.mean(np.abs(bt_b.actual_y - p)) for p in bt_b.preds_y.values())

    if best_mae_b < best_mae_a:
        return "B_robust_winsor_log1p", bt_b
    return "A_raw", bt_a
