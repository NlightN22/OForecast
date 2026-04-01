"""
ts_forecast: robust monthly time-series forecasting (1 month ahead)
"""

from .core.config import ForecastConfig
from .core.service import run_forecast, format_result_text

__all__ = ["ForecastConfig", "run_forecast", "format_result_text"]
