"""
Adapter between Sales Forecast input data and the local OForecast package.
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import pandas as pd

from ts_forecast.core.config import ForecastConfig
from ts_forecast.core.models import model_catalog
from ts_forecast.core.result import ForecastResult, format_result_text
from ts_forecast.core.service import run_forecast

try:
    from .config import DISABLED_MODELS
except ImportError:  # pragma: no cover - script execution fallback
    from config import DISABLED_MODELS


class OForecastAdapter:
    def __init__(self, cfg: ForecastConfig | None = None):
        self.cfg = cfg or ForecastConfig()

    def forecast(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Runs OForecast for every unique sales series and returns a flat table.
        """

        self._validate_input(dataframe)

        rows: list[dict[str, Any]] = []

        for unique_id in sorted(dataframe["unique_id"].dropna().unique()):
            series_df = dataframe[dataframe["unique_id"] == unique_id].copy()
            meta = self._series_meta(series_df)

            try:
                forecast = self.forecast_brand(series_df)

                try:
                    from .config import PRINT_FULL_REPORT
                except ImportError:
                    from config import PRINT_FULL_REPORT

                if PRINT_FULL_REPORT:
                    print()
                    print("=" * 80)
                    print(f"BRAND: {meta.get('brand') or meta.get('unique_id')}")
                    print("=" * 80)
                    print(format_result_text(forecast))

                rows.append(self._result_row(meta, forecast))
            except Exception as exc:
                rows.append(self._error_row(meta, exc))

        return pd.DataFrame(rows, columns=self._output_columns())

    def forecast_brand(self, dataframe: pd.DataFrame) -> ForecastResult:
        """
        Runs OForecast for one brand.
        """

        prepared = self.prepare_dataframe(dataframe)
        raw = self._to_tsv(prepared)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)

            result = run_forecast(
                raw=raw,
                cfg=self.cfg,
                models=self._allowed_models(),
                use_all=False,
            )

        return result

    @staticmethod
    def prepare_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        Converts sales data to the public OForecast text input contract.
        """

        required = {"unique_id", "period_start", "y"}
        missing = required.difference(dataframe.columns)
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")

        df = dataframe.loc[:, ["unique_id", "period_start", "y"]].copy()
        df["period_start"] = pd.to_datetime(df["period_start"], errors="coerce")
        df["y"] = pd.to_numeric(df["y"], errors="coerce")
        df = df.dropna(subset=["period_start", "y"])
        df = df.sort_values("period_start").reset_index(drop=True)

        if df.empty:
            raise ValueError("Brand has no valid forecast rows.")

        return df

    def _allowed_models(self) -> list[str]:
        models = model_catalog(
            self.cfg.ets_trends,
            self.cfg.ets_seasonals,
        )
        return [name for name in models if name not in DISABLED_MODELS]

    @staticmethod
    def _to_tsv(dataframe: pd.DataFrame) -> str:
        lines = []

        for row in dataframe.itertuples(index=False):
            period = pd.Timestamp(row.period_start).strftime("%Y-%m")
            value = float(row.y)

            if not math.isfinite(value):
                continue

            lines.append(f"{period}\t{value:.12g}")

        if not lines:
            raise ValueError("Brand has no finite forecast values.")

        return "\n".join(lines)

    @staticmethod
    @staticmethod
    def _series_meta(dataframe: pd.DataFrame) -> dict[str, str]:
        first = dataframe.iloc[0]
        return {
            "unique_id": str(first.get("unique_id", "")),
            "forecast_level": str(first.get("forecast_level", "brand_total")),
            "manager": str(first.get("manager", "")),
            "brand": str(first.get("brand", first.get("unique_id", ""))),
        }

    @staticmethod
    def _result_row(
        meta: dict[str, str],
        result: ForecastResult,
    ) -> dict[str, Any]:
        return {
            **meta,
            "next_period": result.next_period,
            "forecast": OForecastAdapter._clean_value(
                result.intervals.get("point")
            ),
            "lo80": OForecastAdapter._clean_value(result.intervals.get("lo80")),
            "hi80": OForecastAdapter._clean_value(result.intervals.get("hi80")),
            "lo95": OForecastAdapter._clean_value(result.intervals.get("lo95")),
            "hi95": OForecastAdapter._clean_value(result.intervals.get("hi95")),
            "best_model": result.chosen_model,
            "chosen_dataset": result.chosen_dataset,
            "rows_in": result.rows_in,
            "rows_after_fill": result.rows_after_fill,
            "missing_periods_filled": result.missing_periods_filled,
            "status": "ok",
            "error": "",
        }

    @staticmethod
    def _error_row(meta: dict[str, str], exc: Exception) -> dict[str, Any]:
        return {
            **meta,
            "next_period": "",
            "forecast": None,
            "lo80": None,
            "hi80": None,
            "lo95": None,
            "hi95": None,
            "best_model": "",
            "chosen_dataset": "",
            "rows_in": None,
            "rows_after_fill": None,
            "missing_periods_filled": None,
            "status": "error",
            "error": str(exc),
        }

    @staticmethod
    def _validate_input(dataframe: pd.DataFrame) -> None:
        if dataframe.empty:
            raise ValueError("No sales rows to forecast.")

        required = {"unique_id", "period_start", "y"}
        missing = required.difference(dataframe.columns)
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")

    @staticmethod
    def _output_columns() -> list[str]:
        return [
            "unique_id",
            "forecast_level",
            "manager",
            "brand",
            "next_period",
            "forecast",
            "lo80",
            "hi80",
            "lo95",
            "hi95",
            "best_model",
            "chosen_dataset",
            "rows_in",
            "rows_after_fill",
            "missing_periods_filled",
            "status",
            "error",
        ]

    @staticmethod
    def _clean_value(value: Any) -> float | None:
        if value is None:
            return None

        number = float(value)
        if not math.isfinite(number):
            return None

        return max(0.0, number)
