import re
import pandas as pd

RU_MONTHS = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12
}

def parse_ru_month_year(s: str) -> pd.Timestamp:
    s = s.strip()
    s = re.sub(r"\s*г\.?\s*$", "", s, flags=re.IGNORECASE)
    parts = s.split()
    if len(parts) < 2:
        raise ValueError(f"Bad month string: {s!r}")
    mname = parts[0].lower()
    year = int(parts[1])
    if mname not in RU_MONTHS:
        raise ValueError(f"Unknown RU month: {mname!r}")
    return pd.Timestamp(year, RU_MONTHS[mname], 1)

def parse_ru_number(s: str) -> float:
    s = s.strip()
    s = re.sub(r"[ \u00A0\u202F]", "", s)  # spaces, NBSP, narrow NBSP
    s = s.replace(",", ".")
    return float(s)

def read_tsv_like(raw: str) -> pd.DataFrame:
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if "\t" not in line:
            raise ValueError(f"Line must contain tab separator: {line}")
        m_str, v_str = line.split("\t", 1)
        rows.append((parse_ru_month_year(m_str), parse_ru_number(v_str)))
    df = pd.DataFrame(rows, columns=["month", "value"]).sort_values("month").reset_index(drop=True)
    return df

def fill_missing_months(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    full = pd.date_range(df["month"].min(), df["month"].max(), freq="MS")
    missing = full.difference(pd.DatetimeIndex(df["month"]))
    miss_n = len(missing)
    if miss_n == 0:
        return df.copy(), 0
    out = df.set_index("month").reindex(full).rename_axis("month").reset_index()
    out["value"] = out["value"].interpolate("linear")
    return out, miss_n

def add_transforms(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["y"] = out["value"].astype(float)
    out["y_log"] = (out["y"] + 1.0).apply(lambda v: __import__("math").log(v))
    return out