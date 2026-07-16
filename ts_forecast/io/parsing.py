import re
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

try:
    import dateparser
except Exception:  # pragma: no cover - optional dependency
    dateparser = None

QUARTER_START_MONTHS = {1: 1, 2: 4, 3: 7, 4: 10}


@dataclass(frozen=True)
class LabelRecognition:
    period_starts: list[pd.Timestamp | None]
    period_freq: str | None
    next_label: str
    confidence: float


class LabelRecognizer(Protocol):
    def recognize(self, labels: list[str]) -> LabelRecognition: ...


def _normalize_year(year: int) -> int:
    return year + 2000 if year < 100 else year


def _parse_with_dateparser(raw: str) -> pd.Timestamp | None:
    if dateparser is None:
        return None
    dt = dateparser.parse(
        raw,
        languages=["en"],
        settings={
            "DATE_ORDER": "YMD",
            "PREFER_DAY_OF_MONTH": "first",
        },
    )
    if dt is None:
        return None
    return pd.Timestamp(dt.year, dt.month, 1)


def _parse_quarter_year(raw: str) -> pd.Timestamp | None:
    value = raw.strip().lower()
    value = re.sub(r"\s+", " ", value)
    patterns = [
        r"^q([1-4])[\s.\-]*(\d{2,4})$",
        r"^(\d{2,4})[\s.\-]*q([1-4])$",
        r"^([1-4])[\s.\-]*q[\s.\-]*(\d{2,4})$",
        r"^quarter[\s.\-]*([1-4])[\s.\-]*(\d{2,4})$",
        r"^(\d{2,4})[\s.\-]*quarter[\s.\-]*([1-4])$",
    ]
    for pattern in patterns:
        match = re.match(pattern, value, flags=re.IGNORECASE)
        if match is None:
            continue
        first = int(match.group(1))
        second = int(match.group(2))
        if first in QUARTER_START_MONTHS:
            quarter, year = first, second
        else:
            year, quarter = first, second
        return pd.Timestamp(_normalize_year(year), QUARTER_START_MONTHS[quarter], 1)
    return None


def _parse_iso_period(raw: str) -> pd.Timestamp | None:
    match = re.match(r"^(\d{4})-(\d{2})(?:-\d{2})?$", raw.strip())
    if match is None:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    if not 1 <= month <= 12:
        return None
    return pd.Timestamp(year, month, 1)


def parse_period_start(label: str) -> pd.Timestamp | None:
    value = label.strip()
    return (
        _parse_quarter_year(value)
        or _parse_iso_period(value)
        or _parse_with_dateparser(value)
    )


def parse_number(value: str) -> float:
    normalized = value.strip()
    normalized = re.sub(r"[ \u00A0\u202F]", "", normalized)
    normalized = normalized.replace(",", ".")
    return float(normalized)


def infer_period_freq(df: pd.DataFrame) -> str | None:
    if "period_freq" in df.columns and not df["period_freq"].empty:
        value = df["period_freq"].iloc[0]
        if pd.notna(value):
            return str(value)
    if "period_start" not in df.columns or df["period_start"].isna().any():
        return None

    starts = pd.to_datetime(df["period_start"])
    months = set(starts.dt.month.to_list())
    if months and months.issubset(set(QUARTER_START_MONTHS.values())):
        return "QS"
    return "MS"


def period_seasonal_length(df: pd.DataFrame) -> int:
    return 4 if infer_period_freq(df) == "QS" else 12


def _next_period_label(df: pd.DataFrame) -> str:
    freq = infer_period_freq(df)
    if freq is None:
        return "next"
    next_start = pd.date_range(df["period_start"].max(), periods=2, freq=freq)[-1]
    return next_start.strftime("%Y-%m")


def _apply_label_recognition(
    df: pd.DataFrame,
    label_recognizer: LabelRecognizer | None,
) -> pd.DataFrame:
    if label_recognizer is None or not df["period_start"].isna().any():
        return df

    recognized = label_recognizer.recognize(df["label"].astype(str).to_list())
    if recognized.confidence < 0.7 or len(recognized.period_starts) != len(df):
        return df

    out = df.copy()
    out["period_start"] = recognized.period_starts
    out["period_freq"] = recognized.period_freq
    out["next_label"] = recognized.next_label
    return out


def read_tsv_like(
    raw: str, label_recognizer: LabelRecognizer | None = None
) -> pd.DataFrame:
    rows = []
    sep_re = re.compile(r"\s*(?:\t+| {2,}|[;|])\s*")
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = sep_re.split(line.strip(), maxsplit=1)
        if len(parts) != 2:
            raise ValueError(
                f"Line must contain tab, 2+ spaces, ';' or '|' separator: {line}"
            )
        label, raw_value = parts
        rows.append((label, parse_period_start(label), parse_number(raw_value)))

    df = pd.DataFrame(rows, columns=["label", "period_start", "value"])
    if df.empty:
        raise ValueError("input contains no data rows")

    df = _apply_label_recognition(df, label_recognizer)

    if not df["period_start"].isna().any():
        df = df.sort_values("period_start").reset_index(drop=True)
    else:
        df["period_start"] = pd.NaT

    df["period_index"] = range(len(df))
    df["period_freq"] = infer_period_freq(df)
    if "next_label" not in df.columns or df["next_label"].isna().all():
        df["next_label"] = _next_period_label(df)
    else:
        df["next_label"] = df["next_label"].fillna(_next_period_label(df))
    return df


def fill_missing_periods(
    df: pd.DataFrame, fill_with_mean: bool
) -> tuple[pd.DataFrame, int]:
    period_freq = infer_period_freq(df)
    if period_freq is None:
        return df.copy(), 0

    full = pd.date_range(
        df["period_start"].min(), df["period_start"].max(), freq=period_freq
    )
    missing = full.difference(pd.DatetimeIndex(df["period_start"]))
    missing_count = len(missing)
    if missing_count == 0:
        return df.copy(), 0

    out = (
        df.set_index("period_start")
        .reindex(full)
        .rename_axis("period_start")
        .reset_index()
    )
    out["period_freq"] = period_freq
    out["label"] = out["label"].fillna(out["period_start"].dt.strftime("%Y-%m"))
    out["next_label"] = _next_period_label(out)
    out["period_index"] = range(len(out))
    if fill_with_mean:
        out["value"] = out["value"].interpolate("linear")
    else:
        out["value"] = out["value"].fillna(0.0)
    return out, missing_count


def add_transforms(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["y"] = out["value"].astype(float)
    log_shift = max(0.0, -float(out["y"].min()))
    out["log_shift"] = log_shift
    out["y_log"] = (out["y"] + log_shift + 1.0).apply(
        lambda v: __import__("math").log(v)
    )
    return out
