from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re

import pandas as pd

from config import HEADER_ROW, FIRST_BRAND_COLUMN, PERIOD_COLUMN, DROP_ZERO_ROWS


IGNORED_COLUMNS = {"", "итог", "итого", "всего", "общий итог", "total"}


@dataclass
class ManagerBrandRaw:
    forecast_level: str
    manager: str
    brand: str
    raw: str


def normalize_text(value) -> str:
    if value is None or pd.isna(value):
        return ""

    text = str(value).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def to_float(value) -> float:
    if value is None or pd.isna(value):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = normalize_text(value)

    if text in {"", "-"}:
        return 0.0

    text = text.replace(" ", "")
    text = text.replace("\xa0", "")
    text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return 0.0


def is_month_label(value) -> bool:
    text = normalize_text(value).lower()

    return bool(
        re.match(
            r"^(январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь|january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\s*г?\.?$",
            text,
        )
    )


def is_total_label(value) -> bool:
    text = normalize_text(value).lower()
    return text in IGNORED_COLUMNS


def format_number_for_api(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def safe_sheet_name(value: str) -> str:
    value = re.sub(r"[\[\]\:\*\?\/\\]", "_", value)
    return value[:31]


class SalesApiTransformer:
    def run(self, dataframe: pd.DataFrame) -> list[ManagerBrandRaw]:
        brands = self._read_brands(dataframe)
        data = self._collect(dataframe, brands)
        return self._build_raw(self._brand_totals(data), data)

    @staticmethod
    def _brand_totals(data):
        totals = defaultdict(lambda: defaultdict(float))
        for brands in data.values():
            for brand, rows in brands.items():
                for label, value in rows.items():
                    totals[brand][label] += value
        return totals

    def _read_brands(self, dataframe: pd.DataFrame) -> list[str]:
        row = dataframe.iloc[HEADER_ROW - 1]

        brands: list[str] = []
        column = FIRST_BRAND_COLUMN

        while column < len(row):
            value = normalize_text(row.iloc[column])

            if value.lower() in IGNORED_COLUMNS:
                break

            if value:
                brands.append(value)

            column += 1

        if not brands:
            raise ValueError("Could not find brands in Excel.")

        return brands

    def _collect(
        self,
        dataframe: pd.DataFrame,
        brands: list[str],
    ) -> dict[str, dict[str, dict[str, float]]]:

        result = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        current_manager = None

        for row_index in range(HEADER_ROW + 1, len(dataframe)):
            row = dataframe.iloc[row_index]

            label = normalize_text(row.iloc[PERIOD_COLUMN])

            if not label:
                continue

            if is_total_label(label):
                current_manager = None
                continue

            if not is_month_label(label):
                current_manager = label
                continue

            if current_manager is None:
                continue

            for offset, brand in enumerate(brands):
                column = FIRST_BRAND_COLUMN + offset

                if column >= len(row):
                    break

                value = to_float(row.iloc[column])

                if DROP_ZERO_ROWS and value == 0:
                    continue

                result[current_manager][brand][label] += value

        return result

    def _build_raw(
        self,
        totals: dict[str, dict[str, float]],
        data: dict[str, dict[str, dict[str, float]]],
    ) -> list[ManagerBrandRaw]:

        result: list[ManagerBrandRaw] = []

        for brand, rows in totals.items():
            result.append(
                ManagerBrandRaw(
                    forecast_level="brand_total",
                    manager="All managers",
                    brand=brand,
                    raw=self._rows_to_raw(rows),
                )
            )

        for manager, brands in data.items():
            if is_total_label(manager):
                continue

            for brand, rows in brands.items():
                raw = self._rows_to_raw(rows)
                if not raw:
                    continue

                result.append(
                    ManagerBrandRaw(
                        forecast_level="manager_brand",
                        manager=manager,
                        brand=brand,
                        raw=raw,
                    )
                )

        return result

    @staticmethod
    def _rows_to_raw(rows: dict[str, float]) -> str:
        lines = [
            f"{label}\t{format_number_for_api(value)}"
            for label, value in rows.items()
            if not DROP_ZERO_ROWS or value != 0
        ]
        return "\n".join(lines)
