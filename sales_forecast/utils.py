"""
Общие вспомогательные функции.
"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd


MONTHS = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}


# -----------------------------------------------------------------------------


def normalize_text(value) -> str:
    """
    Нормализует текстовое значение.
    """

    if value is None:
        return ""

    if pd.isna(value):
        return ""

    text = str(value)

    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# -----------------------------------------------------------------------------


def to_float(value) -> float:
    """
    Безопасное преобразование значения Excel в float.
    """

    if value is None:
        return 0.0

    if pd.isna(value):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = normalize_text(value)

    if text in ("", "-"):
        return 0.0

    text = text.replace(" ", "")
    text = text.replace(",", ".")

    try:
        return float(text)

    except Exception:
        return 0.0


# -----------------------------------------------------------------------------


def parse_month(value) -> pd.Timestamp | None:
    """
    Преобразует строку

        Январь 2024

    в Timestamp.
    """

    text = normalize_text(value).lower()

    text = text.replace(".", "")

    parts = [
        part
        for part in text.split()
        if part not in {"г", "года"}
    ]

    if len(parts) != 2:
        return None

    month = MONTHS.get(parts[0])

    if month is None:
        return None

    try:

        year = int(parts[1])

    except Exception:

        return None

    return pd.Timestamp(
        datetime(
            year,
            month,
            1,
        )
    )


# -----------------------------------------------------------------------------


def ensure_monthly_index(
    series: pd.Series,
) -> pd.Series:
    """
    Делает временной ряд непрерывным.
    """

    if series.empty:
        return series

    series = series.sort_index()

    full_index = pd.date_range(
        start=series.index.min(),
        end=series.index.max(),
        freq="MS",
    )

    return (
        series
        .reindex(full_index)
        .fillna(0.0)
    )


# -----------------------------------------------------------------------------


def is_month(value) -> bool:
    """
    Проверяет,
    является ли значение месяцем.
    """

    return parse_month(value) is not None


# -----------------------------------------------------------------------------


def is_empty(value) -> bool:
    """
    Проверяет,
    является ли значение пустым.
    """

    return normalize_text(value) == ""
