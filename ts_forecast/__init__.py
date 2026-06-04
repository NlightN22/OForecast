"""
ts_forecast: robust time-series forecasting for labeled numeric series
"""

from .core.config import ForecastConfig
from .core.service import run_forecast, format_result_text

__all__ = ["ForecastConfig", "run_forecast", "format_result_text"]
