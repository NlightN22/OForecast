from collections import defaultdict

import pandas as pd

try:
    from .config import (
        FILL_MISSING_MONTHS,
        FIRST_BRAND_COLUMN,
        HEADER_ROW,
        IGNORED_COLUMNS,
        MIN_HISTORY_MONTHS,
        ROW_LABEL_COLUMN,
    )
    from .utils import ensure_monthly_index, normalize_text, parse_month, to_float
except ImportError:  # pragma: no cover - script execution fallback
    from config import (
        FILL_MISSING_MONTHS,
        FIRST_BRAND_COLUMN,
        HEADER_ROW,
        IGNORED_COLUMNS,
        MIN_HISTORY_MONTHS,
        ROW_LABEL_COLUMN,
    )
    from utils import ensure_monthly_index, normalize_text, parse_month, to_float


TOTAL_MANAGER = "All managers"


class SalesTransformer:
    def run(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        if dataframe.empty:
            raise ValueError("Empty DataFrame.")

        brands = self._read_brands(dataframe)
        if not brands:
            raise ValueError("Brands not found.")

        total_sales, manager_sales = self._collect_sales(dataframe, brands)
        return self._build_dataframe(total_sales, manager_sales)

    def _read_brands(self, dataframe: pd.DataFrame) -> list[str]:
        row = dataframe.iloc[HEADER_ROW - 1]
        brands = []

        for column in range(FIRST_BRAND_COLUMN, len(row)):
            value = normalize_text(row.iloc[column])
            if value in IGNORED_COLUMNS:
                break
            brands.append(value)

        return brands

    def _collect_sales(
        self,
        dataframe: pd.DataFrame,
        brands: list[str],
    ) -> tuple[
        dict[str, dict[pd.Timestamp, float]],
        dict[tuple[str, str], dict[pd.Timestamp, float]],
    ]:
        total_sales = defaultdict(lambda: defaultdict(float))
        manager_sales = defaultdict(lambda: defaultdict(float))
        current_manager = ""

        for row_index in range(HEADER_ROW + 1, len(dataframe)):
            row = dataframe.iloc[row_index]
            row_label = normalize_text(row.iloc[ROW_LABEL_COLUMN])

            if row_label == "":
                continue

            month = parse_month(row_label)
            if month is None:
                if row_label not in IGNORED_COLUMNS:
                    current_manager = row_label
                continue

            if not current_manager:
                continue

            for offset, brand in enumerate(brands):
                column = FIRST_BRAND_COLUMN + offset
                if column >= len(row):
                    break

                value = to_float(row.iloc[column])
                total_sales[brand][month] += value
                manager_sales[(current_manager, brand)][month] += value

        return total_sales, manager_sales

    def _build_dataframe(
        self,
        total_sales: dict[str, dict[pd.Timestamp, float]],
        manager_sales: dict[tuple[str, str], dict[pd.Timestamp, float]],
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

        for (manager, brand), history in sorted(manager_sales.items()):
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
            period
            for history in total_sales.values()
            for period in history.keys()
        ]
        if not periods:
            return None
        return max(periods)
