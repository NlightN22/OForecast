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
TOTAL_LABELS = {"итог", "итого", "всего", "общий итог", "total"}


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

    text = text.replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_month(value) -> pd.Timestamp | None:
    text = normalize_text(value).lower().replace(".", "")
    parts = [part for part in text.split() if part not in {"г", "года"}]

    if len(parts) != 2:
        return None

    month = MONTHS.get(parts[0])
    if month is None:
        return None

    try:
        year = int(parts[1])
    except ValueError:
        return None

    return pd.Timestamp(datetime(year, month, 1))


def ensure_monthly_index(series: pd.Series) -> pd.Series:
    if series.empty:
        return series

    series = series.sort_index()
    full_index = pd.date_range(
        start=series.index.min(),
        end=series.index.max(),
        freq="MS",
    )
    return series.reindex(full_index).fillna(0.0)


def is_total_label(value) -> bool:
    return normalize_text(value).lower() in TOTAL_LABELS
