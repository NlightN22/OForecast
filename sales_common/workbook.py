from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from .text import is_total_label, normalize_text, parse_month, to_float


@dataclass(frozen=True)
class SalesLayout:
    header_row: int = 8
    row_label_column: int = 1
    first_brand_column: int = 2
    drop_zero_rows: bool = False


@dataclass(frozen=True)
class SalesWorkbookData:
    brands: list[str]
    manager_sales: dict[str, dict[str, dict[pd.Timestamp, float]]]


def extract_sales(dataframe: pd.DataFrame, layout: SalesLayout) -> SalesWorkbookData:
    brands = read_brands(dataframe, layout)
    manager_sales = collect_sales(dataframe, brands, layout)
    return SalesWorkbookData(brands=brands, manager_sales=manager_sales)


def read_brands(dataframe: pd.DataFrame, layout: SalesLayout) -> list[str]:
    row = dataframe.iloc[layout.header_row - 1]
    brands: list[str] = []

    for column in range(layout.first_brand_column, len(row)):
        value = normalize_text(row.iloc[column])
        if is_total_label(value):
            break
        if value:
            brands.append(value)

    if not brands:
        raise ValueError("Brands not found.")

    return brands


def collect_sales(
    dataframe: pd.DataFrame,
    brands: list[str],
    layout: SalesLayout,
) -> dict[str, dict[str, dict[pd.Timestamp, float]]]:
    result = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    current_manager = ""

    for row_index in range(layout.header_row + 1, len(dataframe)):
        row = dataframe.iloc[row_index]
        label = normalize_text(row.iloc[layout.row_label_column])

        if not label:
            continue

        month = parse_month(label)
        if month is None:
            current_manager = "" if is_total_label(label) else label
            continue

        if not current_manager:
            continue

        for offset, brand in enumerate(brands):
            column = layout.first_brand_column + offset
            if column >= len(row):
                break

            value = to_float(row.iloc[column])
            if layout.drop_zero_rows and value == 0:
                continue

            result[current_manager][brand][month] += value

    return result


def brand_totals(
    data: dict[str, dict[str, dict[pd.Timestamp, float]]],
) -> dict[str, dict[pd.Timestamp, float]]:
    totals = defaultdict(lambda: defaultdict(float))
    for brands in data.values():
        for brand, rows in brands.items():
            for period, value in rows.items():
                totals[brand][period] += value
    return totals
