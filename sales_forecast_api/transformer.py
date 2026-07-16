from __future__ import annotations

from sales_common.api_payload import ForecastTask, rows_to_raw
from sales_common.workbook import SalesLayout, brand_totals, extract_sales

try:
    from .config import HEADER_ROW, FIRST_BRAND_COLUMN, PERIOD_COLUMN, DROP_ZERO_ROWS
except ImportError:  # pragma: no cover - script execution fallback
    from config import HEADER_ROW, FIRST_BRAND_COLUMN, PERIOD_COLUMN, DROP_ZERO_ROWS


class SalesApiTransformer:
    def run(self, dataframe) -> list[ForecastTask]:
        layout = SalesLayout(
            header_row=HEADER_ROW,
            row_label_column=PERIOD_COLUMN,
            first_brand_column=FIRST_BRAND_COLUMN,
            drop_zero_rows=DROP_ZERO_ROWS,
        )
        workbook_data = extract_sales(dataframe, layout)
        return self._build_tasks(
            brand_totals(workbook_data.manager_sales),
            workbook_data.manager_sales,
        )

    @staticmethod
    def _build_tasks(totals, data) -> list[ForecastTask]:
        tasks: list[ForecastTask] = []

        for brand, rows in totals.items():
            tasks.append(
                ForecastTask(
                    forecast_level="brand_total",
                    manager="All managers",
                    brand=brand,
                    raw=rows_to_raw(rows, DROP_ZERO_ROWS),
                )
            )

        for manager, brands in data.items():
            for brand, rows in brands.items():
                raw = rows_to_raw(rows, DROP_ZERO_ROWS)
                if not raw:
                    continue
                tasks.append(
                    ForecastTask(
                        forecast_level="manager_brand",
                        manager=manager,
                        brand=brand,
                        raw=raw,
                    )
                )

        return tasks
