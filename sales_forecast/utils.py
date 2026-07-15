"""
Shared helper functions.
"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd


MONTHS = {
    "январь": 1,
    "january": 1,
    "февраль": 2,
    "february": 2,
    "март": 3,
    "march": 3,
    "апрель": 4,
    "april": 4,
    "май": 5,
    "may": 5,
    "июнь": 6,
    "june": 6,
    "июль": 7,
    "july": 7,
    "август": 8,
    "august": 8,
    "сентябрь": 9,
    "september": 9,
    "октябрь": 10,
    "october": 10,
    "ноябрь": 11,
    "november": 11,
    "декабрь": 12,
    "december": 12,
}


# -----------------------------------------------------------------------------


def normalize_text(value) -> str:
    """
    Normalize a text value.
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
    Safely convert an Excel value to float.
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
    Convert a localized month label such as

        January 2024

    into a Timestamp.
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
    Make a time series continuous.
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
    Check whether a value is a month label.
    """

    return parse_month(value) is not None


# -----------------------------------------------------------------------------


def is_empty(value) -> bool:
    """
    Check whether a value is empty.
    """

    return normalize_text(value) == ""
