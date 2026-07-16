import pandas as pd

from sales_common.text import ensure_monthly_index
from sales_common.workbook import SalesLayout, brand_totals, extract_sales

try:
    from .config import (
        FILL_MISSING_MONTHS,
        FIRST_BRAND_COLUMN,
        HEADER_ROW,
        MIN_HISTORY_MONTHS,
        ROW_LABEL_COLUMN,
    )
except ImportError:  # pragma: no cover - script execution fallback
    from config import (
        FILL_MISSING_MONTHS,
        FIRST_BRAND_COLUMN,
        HEADER_ROW,
        MIN_HISTORY_MONTHS,
        ROW_LABEL_COLUMN,
    )


TOTAL_MANAGER = "All managers"


class SalesTransformer:
    def run(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        if dataframe.empty:
            raise ValueError("Empty DataFrame.")

        layout = SalesLayout(
            header_row=HEADER_ROW,
            row_label_column=ROW_LABEL_COLUMN,
            first_brand_column=FIRST_BRAND_COLUMN,
        )
        workbook_data = extract_sales(dataframe, layout)
        totals = brand_totals(workbook_data.manager_sales)
        return self._build_dataframe(totals, workbook_data.manager_sales)

    def _build_dataframe(
        self,
        total_sales: dict[str, dict[pd.Timestamp, float]],
        manager_sales: dict[str, dict[str, dict[pd.Timestamp, float]]],
    ) -> pd.DataFrame:
        rows = []
        end_period = self._max_period(total_sales)

        for brand, history in sorted(total_sales.items()):
            rows.extend(
                self._series_rows(
                    forecast_level="brand_total",
                    manager=TOTAL_MANAGER,
                    brand=brand,
                    history=history,
                    end_period=end_period,
                )
            )

        for manager, brands in sorted(manager_sales.items()):
            for brand, history in sorted(brands.items()):
                rows.extend(
                    self._series_rows(
                        forecast_level="manager_brand",
                        manager=manager,
                        brand=brand,
                        history=history,
                        end_period=None,
                    )
                )

        columns = [
            "unique_id",
            "forecast_level",
            "manager",
            "brand",
            "period_start",
            "y",
        ]
        result = pd.DataFrame(rows, columns=columns)

        if result.empty:
            return result

        result.sort_values(
            by=["forecast_level", "manager", "brand", "period_start"],
            inplace=True,
        )
        result.reset_index(drop=True, inplace=True)
        return result

    def _series_rows(
        self,
        forecast_level: str,
        manager: str,
        brand: str,
        history: dict[pd.Timestamp, float],
        end_period: pd.Timestamp | None,
    ) -> list[dict]:
        series = self._valid_series(history, end_period)
        if series is None:
            return []

        unique_id = self._unique_id(forecast_level, manager, brand)
        return [
            {
                "unique_id": unique_id,
                "forecast_level": forecast_level,
                "manager": manager,
                "brand": brand,
                "period_start": period,
                "y": float(value),
            }
            for period, value in series.items()
        ]

    @staticmethod
    def _valid_series(
        history: dict[pd.Timestamp, float],
        end_period: pd.Timestamp | None,
    ) -> pd.Series | None:
        if not history:
            return None

        series = pd.Series(history, dtype="float64").sort_index()
        if FILL_MISSING_MONTHS:
            series = ensure_monthly_index(series)
            if end_period is not None and series.index.max() < end_period:
                full_index = pd.date_range(
                    start=series.index.min(),
                    end=end_period,
                    freq="MS",
                )
                series = series.reindex(full_index).fillna(0.0)

        if len(series) < MIN_HISTORY_MONTHS or series.sum() <= 0:
            return None

        return series

    @staticmethod
    def _unique_id(forecast_level: str, manager: str, brand: str) -> str:
        if forecast_level == "brand_total":
            return f"brand_total::{brand}"
        return f"manager_brand::{manager}::{brand}"

    @staticmethod
    def _max_period(
        total_sales: dict[str, dict[pd.Timestamp, float]],
    ) -> pd.Timestamp | None:
        periods = [
            period for history in total_sales.values() for period in history.keys()
        ]
        if not periods:
            return None
        return max(periods)
