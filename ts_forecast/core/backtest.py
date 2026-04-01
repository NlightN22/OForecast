from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List

from .config import ForecastConfig
from .models import (
    winsorize_log, safe_expm1,
    ses_forecast_log, ets_forecast_log, seasonal_naive_y, arima_forecast_log, HAS_PMDARIMA
)

@dataclass
class BacktestResult:
    months: List[pd.Timestamp]
    actual_y: np.ndarray
    preds_y: Dict[str, np.ndarray]  # model -> y-space preds

def _test_len(n: int, cfg: ForecastConfig) -> int:
    return cfg.test_len_if_ge_48 if n >= 48 else cfg.test_len_else

def walk_forward(df: pd.DataFrame, cfg: ForecastConfig, robust: bool, include_arima: bool = True) -> BacktestResult:
    n = len(df)
    tlen = _test_len(n, cfg)
    start = n - tlen

    months: List[pd.Timestamp] = []
    actual: List[float] = []
    preds: Dict[str, List[float]] = {}

    for i in range(start, n):
        train = df.iloc[:i]
        y_train = train["y"].to_numpy(dtype=float)
        ylog_train = train["y_log"].to_numpy(dtype=float)

        if robust:
            ylog_train = winsorize_log(ylog_train, cfg.winsor_q_low, cfg.winsor_q_high)

        # SES(log)
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
                f = ets_forecast_log(ylog_train, tr, seas, sp)
                preds.setdefault(name, []).append(safe_expm1(f))

        # Seasonal naive (y)
        preds.setdefault("SeasonalNaive_y", []).append(seasonal_naive_y(y_train))

        # ARIMA(log) optional
        if include_arima and HAS_PMDARIMA:
            a = arima_forecast_log(
                ylog_train,
                m=cfg.arima_m,
                stepwise=cfg.arima_stepwise,
                max_pq=cfg.arima_max_pq,
                max_pq_seas=cfg.arima_max_pq_seas,
            )
            if a is not None:
                preds.setdefault("AutoARIMA_log", []).append(safe_expm1(a))

        months.append(df.loc[i, "month"])
        actual.append(float(df.loc[i, "y"]))

    preds_np = {k: np.asarray(v, dtype=float) for k, v in preds.items()}
    return BacktestResult(months=months, actual_y=np.asarray(actual, dtype=float), preds_y=preds_np)

def choose_dataset(df: pd.DataFrame, cfg: ForecastConfig) -> tuple[str, BacktestResult]:
    bt_a = walk_forward(df, cfg, robust=False, include_arima=True)
    bt_b = walk_forward(df, cfg, robust=True, include_arima=True)

    best_mae_a = min(np.mean(np.abs(bt_a.actual_y - p)) for p in bt_a.preds_y.values())
    best_mae_b = min(np.mean(np.abs(bt_b.actual_y - p)) for p in bt_b.preds_y.values())

    if best_mae_b < best_mae_a:
        return "B_robust_winsor_log1p", bt_b
    return "A_raw", bt_a