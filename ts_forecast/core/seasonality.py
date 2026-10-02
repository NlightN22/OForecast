from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

SEASONALITY_MIN_HISTORY = 36
SEASONALITY_MIN_REPEAT_YEARS = 2
SEASONAL_WAPE_ADVANTAGE_MIN = 0.10
SEASON_MONTH_RATIO_THRESHOLD = 1.3

SCALE_RATIO_MIN = 0.5
SCALE_RATIO_MAX = 2.0

SHORT_SEASON_MAX_LEN = 3


def wape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return float("nan")
    return float(100.0 * np.sum(np.abs(y_true - y_pred)) / denom)


def is_seasonal_model(name: str) -> bool:
    if name in ("SeasonalNaive_y", "SF_MSTL", "TBATS_y"):
        return True
    if name.startswith("ETS_log_trend=") and "seasonal=add" in name:
        return True
    return False


@dataclass
class SeasonalityInfo:
    confirmed: bool
    reasons: list[str]
    seasonal_months: set[int] = field(default_factory=set)


def _calendar_month_repeats(df: pd.DataFrame) -> set[int]:
    """Calendar months whose value is consistently elevated or depressed
    relative to that year's median, in at least SEASONALITY_MIN_REPEAT_YEARS
    different years."""
    yearly_median = df.groupby(df["period_start"].dt.year)["y"].median()
    hits_high = {m: 0 for m in range(1, 13)}
    hits_low = {m: 0 for m in range(1, 13)}
    for _, row in df.iterrows():
        year = row["period_start"].year
        month = row["period_start"].month
        med = yearly_median.get(year)
        if not med:
            continue
        ratio = row["y"] / med
        if ratio >= SEASON_MONTH_RATIO_THRESHOLD:
            hits_high[month] += 1
        elif ratio <= 1.0 / SEASON_MONTH_RATIO_THRESHOLD:
            hits_low[month] += 1
    return {
        m
        for m in range(1, 13)
        if hits_high[m] >= SEASONALITY_MIN_REPEAT_YEARS
        or hits_low[m] >= SEASONALITY_MIN_REPEAT_YEARS
    }


def contiguous_month_groups(months: set[int]) -> list[list[int]]:
    """Group calendar months into contiguous (circular) runs, e.g. {11,12,1} -> [[11,12,1]]."""
    if not months:
        return []
    visited: set[int] = set()
    groups: list[list[int]] = []
    for m in sorted(months):
        if m in visited:
            continue
        group = [m]
        visited.add(m)
        nxt = m % 12 + 1
        while nxt in months and nxt not in visited:
            group.append(nxt)
            visited.add(nxt)
            nxt = nxt % 12 + 1
        prv = (m - 2) % 12 + 1
        while prv in months and prv not in visited:
            group.insert(0, prv)
            visited.add(prv)
            prv = (prv - 2) % 12 + 1
        groups.append(group)
    return groups


def detect_seasonality(
    df: pd.DataFrame,
    bt_actual: np.ndarray,
    bt_preds: dict[str, np.ndarray],
) -> SeasonalityInfo:
    """Cheap, aggregate-only seasonality check (no extra model training):
    reuses the existing rolling backtest predictions already computed for
    model selection."""
    if len(df) < SEASONALITY_MIN_HISTORY:
        return SeasonalityInfo(False, [f"history<{SEASONALITY_MIN_HISTORY}m"])

    repeated_months = _calendar_month_repeats(df)
    if not repeated_months:
        return SeasonalityInfo(False, ["no calendar month repeats in >=2 years"])

    seasonal_names = [m for m in bt_preds if is_seasonal_model(m)]
    non_seasonal_names = [m for m in bt_preds if not is_seasonal_model(m)]
    if not seasonal_names or not non_seasonal_names:
        return SeasonalityInfo(False, ["not enough model families in backtest to compare"])

    best_seasonal_wape = min(wape(bt_actual, bt_preds[m]) for m in seasonal_names)
    best_baseline_wape = min(wape(bt_actual, bt_preds[m]) for m in non_seasonal_names)
    if (
        not best_baseline_wape
        or np.isnan(best_baseline_wape)
        or np.isnan(best_seasonal_wape)
    ):
        return SeasonalityInfo(False, ["WAPE undefined (zero actuals in backtest window)"])

    improvement = (best_baseline_wape - best_seasonal_wape) / best_baseline_wape
    if improvement < SEASONAL_WAPE_ADVANTAGE_MIN:
        return SeasonalityInfo(
            False,
            [f"seasonal WAPE improvement {improvement:.1%} < {SEASONAL_WAPE_ADVANTAGE_MIN:.0%}"],
        )
    return SeasonalityInfo(
        True,
        [f"seasonal WAPE improvement {improvement:.1%}"],
        repeated_months,
    )


@dataclass
class SeasonalAnchor:
    available: bool
    anchor_raw: Optional[float] = None
    scale_ratio: Optional[float] = None
    anchor_adjusted: Optional[float] = None
    reason: Optional[str] = None


def compute_seasonal_anchor(df: pd.DataFrame, target_month: int) -> SeasonalAnchor:
    last_date = df["period_start"].max()
    past_years = [last_date.year - k for k in (1, 2, 3)]

    values = []
    for y in past_years:
        row = df[(df["period_start"].dt.year == y) & (df["period_start"].dt.month == target_month)]
        if not row.empty:
            values.append(float(row["y"].iloc[0]))

    if len(values) == 0:
        return SeasonalAnchor(False, reason="no historical data for this calendar month")
    if len(values) == 1:
        return SeasonalAnchor(False, reason="only one past year available, seasonal control skipped")

    anchor_raw = float(np.median(values)) if len(values) == 3 else float(np.mean(values))

    df_sorted = df.sort_values("period_start")
    current_year_rows = df_sorted[df_sorted["period_start"].dt.year == last_date.year]
    last3 = current_year_rows.tail(3)
    if len(last3) < 3:
        # Not enough closed months in the current calendar year yet (e.g. early January):
        # fall back to the last 3 available months regardless of year boundary.
        last3 = df_sorted.tail(3)
    ratios = []
    if len(last3) == 3:
        cur_mean = float(last3["y"].mean())
        for years_back in (1, 2, 3):
            prior_values = []
            for _, r in last3.iterrows():
                prior = df[
                    (df["period_start"].dt.year == r["period_start"].year - years_back)
                    & (df["period_start"].dt.month == r["period_start"].month)
                ]
                if not prior.empty:
                    prior_values.append(float(prior["y"].iloc[0]))
            if len(prior_values) == 3:
                prior_mean = float(np.mean(prior_values))
                if prior_mean > 0:
                    ratios.append(cur_mean / prior_mean)

    scale_ratio = float(np.median(ratios)) if ratios else 1.0
    scale_ratio = float(np.clip(scale_ratio, SCALE_RATIO_MIN, SCALE_RATIO_MAX))

    return SeasonalAnchor(True, anchor_raw, scale_ratio, anchor_raw * scale_ratio)
