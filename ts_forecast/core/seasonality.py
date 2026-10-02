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

SEASONAL_INSTABILITY_THRESHOLD = 0.35
NON_SEASONAL_INSTABILITY_THRESHOLD = 0.25
NON_SEASONAL_BIAS_THRESHOLD = 0.15
MIN_CONFIRMING_SEASONAL_MODELS = 2


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


def detect_seasonality(
    df: pd.DataFrame,
    bt_actual: np.ndarray,
    bt_preds: dict[str, np.ndarray],
) -> SeasonalityInfo:
    """Cheap, aggregate-only seasonality check (no extra model training):
    reuses the existing 12-month rolling backtest predictions already
    computed for model selection."""
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


@dataclass
class PlausibilityResult:
    unstable: bool
    reasons: list[str]
    seasonal: bool
    reference_value: Optional[float] = None
    deviation_pct: Optional[float] = None
    seasonal_anchor_raw: Optional[float] = None
    seasonal_scale_ratio: Optional[float] = None


def check_plausibility(
    point_forecast: float,
    chosen_name: str,
    target_month: int,
    df: pd.DataFrame,
    seasonality: SeasonalityInfo,
    full_y: dict[str, float],
    all_metrics: dict,
) -> PlausibilityResult:
    is_seasonal_month = seasonality.confirmed and target_month in seasonality.seasonal_months

    if is_seasonal_month:
        anchor = compute_seasonal_anchor(df, target_month)
        if not anchor.available:
            return PlausibilityResult(False, [f"no seasonal anchor: {anchor.reason}"], seasonal=False)

        ref = anchor.anchor_adjusted
        reasons: list[str] = []
        deviation = abs(point_forecast - ref) / ref if ref else 0.0
        if deviation > SEASONAL_INSTABILITY_THRESHOLD:
            reasons.append(
                f"forecast deviates {deviation:.1%} from adjusted seasonal anchor "
                f"(>{SEASONAL_INSTABILITY_THRESHOLD:.0%})"
            )

        seasonal_model_names = [m for m in full_y if is_seasonal_model(m)]
        direction_up = point_forecast >= ref
        agreeing = sum(1 for m in seasonal_model_names if (full_y[m] >= ref) == direction_up)
        if len(seasonal_model_names) >= MIN_CONFIRMING_SEASONAL_MODELS and agreeing < MIN_CONFIRMING_SEASONAL_MODELS:
            reasons.append(
                f"only {agreeing}/{len(seasonal_model_names)} seasonal models confirm forecast direction "
                f"(need >={MIN_CONFIRMING_SEASONAL_MODELS})"
            )

        return PlausibilityResult(
            unstable=bool(reasons),
            reasons=reasons,
            seasonal=True,
            reference_value=ref,
            deviation_pct=deviation * 100,
            seasonal_anchor_raw=anchor.anchor_raw,
            seasonal_scale_ratio=anchor.scale_ratio,
        )

    candidate_vals = [v for m, v in full_y.items() if m != "Ensemble_top3_weighted"]
    if not candidate_vals:
        return PlausibilityResult(False, ["no candidate models"], seasonal=False)

    ref = float(np.median(candidate_vals))
    reasons = []
    deviation = abs(point_forecast - ref) / ref if ref else 0.0
    if deviation > NON_SEASONAL_INSTABILITY_THRESHOLD:
        reasons.append(
            f"forecast deviates {deviation:.1%} from median of candidate models "
            f"(>{NON_SEASONAL_INSTABILITY_THRESHOLD:.0%})"
        )

    chosen_metrics = all_metrics.get(chosen_name, {})
    bias = chosen_metrics.get("MAPE")
    if bias is not None and not np.isnan(bias) and bias > NON_SEASONAL_BIAS_THRESHOLD * 100:
        reasons.append(
            f"chosen model absolute bias {bias:.1f}% > {NON_SEASONAL_BIAS_THRESHOLD:.0%}"
        )

    return PlausibilityResult(
        unstable=bool(reasons),
        reasons=reasons,
        seasonal=False,
        reference_value=ref,
        deviation_pct=deviation * 100,
    )
