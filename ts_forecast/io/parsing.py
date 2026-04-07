import re
import pandas as pd

try:
    import dateparser
except Exception:  # pragma: no cover - optional dependency
    dateparser = None

RU_MONTHS = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12
}

RU_MONTH_ABBR = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "сент": 9, "окт": 10, "ноя": 11, "дек": 12
}

def _normalize_month_token(token: str) -> str:
    return token.strip().lower().rstrip(".")

def _parse_with_dateparser(raw: str) -> pd.Timestamp | None:
    if dateparser is None:
        return None
    dt = dateparser.parse(
        raw,
        languages=["ru"],
        settings={
            "DATE_ORDER": "DMY",
            "PREFER_DAY_OF_MONTH": "first",
            "REQUIRE_PARTS": ["month", "year"],
        },
    )
    if dt is None:
        return None
    return pd.Timestamp(dt.year, dt.month, 1)

def parse_ru_month_year(s: str) -> pd.Timestamp:
    s = s.strip()
    s = re.sub(r"\s*г\.?\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    m = re.match(r"^([а-яё]+)\.?\s*(\d{2,4})$", s, flags=re.IGNORECASE)
    if m:
        mname = _normalize_month_token(m.group(1))
        year = int(m.group(2))
        if year < 100:
            year += 2000
        month = RU_MONTHS.get(mname) or RU_MONTH_ABBR.get(mname)
        if not month:
            raise ValueError(f"Unknown RU month: {mname!r}")
        return pd.Timestamp(year, month, 1)
    parsed = _parse_with_dateparser(s)
    if parsed is not None:
        return parsed
    raise ValueError(f"Bad month string: {s!r}")

def parse_ru_number(s: str) -> float:
    s = s.strip()
    s = re.sub(r"[ \u00A0\u202F]", "", s)  # spaces, NBSP, narrow NBSP
    s = s.replace(",", ".")
    return float(s)

def read_tsv_like(raw: str) -> pd.DataFrame:
    rows = []
    sep_re = re.compile(r"(?:\t+| {2,})")
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = sep_re.split(line.strip(), maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"Line must contain tab or 2+ spaces separator: {line}")
        m_str, v_str = parts
        rows.append((parse_ru_month_year(m_str), parse_ru_number(v_str)))
    df = pd.DataFrame(rows, columns=["month", "value"]).sort_values("month").reset_index(drop=True)
    return df

def fill_missing_months(df: pd.DataFrame, fill_with_mean: bool) -> tuple[pd.DataFrame, int]:
    full = pd.date_range(df["month"].min(), df["month"].max(), freq="MS")
    missing = full.difference(pd.DatetimeIndex(df["month"]))
    miss_n = len(missing)
    if miss_n == 0:
        return df.copy(), 0
    out = df.set_index("month").reindex(full).rename_axis("month").reset_index()
    if fill_with_mean:
        out["value"] = out["value"].interpolate("linear")
    else:
        out["value"] = out["value"].fillna(0.0)
    return out, miss_n

def add_transforms(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["y"] = out["value"].astype(float)
    out["y_log"] = (out["y"] + 1.0).apply(lambda v: __import__("math").log(v))
    return out
