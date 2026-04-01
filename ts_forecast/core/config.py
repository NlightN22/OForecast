from dataclasses import dataclass

@dataclass(frozen=True)
class ForecastConfig:
    seed: int = 42
    bootstrap_n: int = 10_000

    # Backtest
    test_len_if_ge_48: int = 12
    test_len_else: int = 6

    # Robust winsorize on log1p
    winsor_q_low: float = 0.05
    winsor_q_high: float = 0.95

    # ETS constraints
    ets_trends: tuple = (None, "add")
    ets_seasonals: tuple = (None, "add")
    ets_seasonal_periods: int = 12
    ets_seasonal_min_n: int = 36

    # ARIMA constraints (pmdarima)
    arima_m: int = 12
    arima_stepwise: bool = True
    arima_max_pq: int = 2
    arima_max_pq_seas: int = 2

    # Ensemble rule
    ensemble_topk: int = 3
    ensemble_max_degradation: float = 0.05  # <= best*(1+5%)

    # StatsForecast
    statsforecast_seasonal_length: int = 12

    # TBATS (sktime)
    tbats_seasonal_periods: int = 12
    tbats_min_n: int = 24
