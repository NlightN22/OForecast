from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .seasonality import SeasonalityInfo, compute_seasonal_anchor, is_seasonal_model, wape

SEASONAL_INSTABILITY_THRESHOLD = 0.35
NON_SEASONAL_INSTABILITY_THRESHOLD = 0.25
NON_SEASONAL_BIAS_THRESHOLD = 0.15
MIN_CONFIRMING_SEASONAL_MODELS = 2

SEASON_BACKTEST_DEGRADATION_FACTOR = 1.5
SEASON_BACKTEST_MIN_WAPE = 15.0

ANALOGOUS_CHANGE_MIN_POINTS = 3
ANALOGOUS_CHANGE_MARGIN = 1.1


def season_backtest_reason(
    bt_periods: list, bt_actual: np.ndarray, bt_pred: np.ndarray, target_month: int
) -> Optional[str]:
    """Flag a model that historically forecasted this same calendar month
    noticeably worse than it forecasts the rest of the year."""
    idx = [i for i, p in enumerate(bt_periods) if pd.Timestamp(p).month == target_month]
    if not idx:
        return None
    season_wape = wape(bt_actual[idx], bt_pred[idx])
    overall_wape = wape(bt_actual, bt_pred)
    if np.isnan(season_wape) or np.isnan(overall_wape) or overall_wape == 0:
        return None
    if season_wape > overall_wape * SEASON_BACKTEST_DEGRADATION_FACTOR and season_wape > SEASON_BACKTEST_MIN_WAPE:
        return (
            f"model's rolling-backtest WAPE for this calendar month is {season_wape:.1f}% "
            f"vs {overall_wape:.1f}% overall"
        )
    return None


def _analogous_change_reason(
    point_forecast: float, reference: Optional[float], bt_actual: np.ndarray
) -> Optional[str]:
    """Flag a forecast implying a change with no precedent of comparable
    magnitude in the actual backtest history."""
    if not reference or len(bt_actual) < ANALOGOUS_CHANGE_MIN_POINTS + 1:
        return None
    implied_change = abs(point_forecast - reference) / reference
    prior = bt_actual[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        historical_changes = np.abs(np.diff(bt_actual) / prior)
    historical_changes = historical_changes[np.isfinite(historical_changes)]
    if len(historical_changes) < ANALOGOUS_CHANGE_MIN_POINTS:
        return None
    max_historical = float(historical_changes.max())
    if implied_change > max_historical * ANALOGOUS_CHANGE_MARGIN:
        return (
            f"implied change {implied_change:.1%} has no precedent in backtest history "
            f"(max historical change {max_historical:.1%})"
        )
    return None


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
    bt_periods: list,
    bt_actual: np.ndarray,
    bt_chosen_pred: Optional[np.ndarray],
) -> PlausibilityResult:
    is_seasonal_month = seasonality.confirmed and target_month in seasonality.seasonal_months

    if is_seasonal_month:
        anchor = compute_seasonal_anchor(df, target_month)
        if not anchor.available:
            return PlausibilityResult(False, [f"no seasonal anchor: {anchor.reason}"], seasonal=False)

        ref = anchor.anchor_adjusted
        reasons: list[str] = []
        if not ref:
            reasons.append("adjusted seasonal anchor is zero/undefined")
            deviation = None
        else:
            deviation = abs(point_forecast - ref) / ref
            if deviation > SEASONAL_INSTABILITY_THRESHOLD:
                reasons.append(
                    f"forecast deviates {deviation:.1%} from adjusted seasonal anchor "
                    f"(>{SEASONAL_INSTABILITY_THRESHOLD:.0%})"
                )

        seasonal_model_names = [m for m in full_y if is_seasonal_model(m)]
        if ref:
            direction_up = point_forecast >= ref
            agreeing = sum(1 for m in seasonal_model_names if (full_y[m] >= ref) == direction_up)
            disagreeing = len(seasonal_model_names) - agreeing
            if len(seasonal_model_names) >= MIN_CONFIRMING_SEASONAL_MODELS and disagreeing >= MIN_CONFIRMING_SEASONAL_MODELS:
                reasons.append(
                    f"{disagreeing}/{len(seasonal_model_names)} seasonal models disagree with forecast "
                    f"direction (>={MIN_CONFIRMING_SEASONAL_MODELS})"
                )

        if bt_chosen_pred is not None:
            season_reason = season_backtest_reason(bt_periods, bt_actual, bt_chosen_pred, target_month)
            if season_reason:
                reasons.append(season_reason)
            analog_reason = _analogous_change_reason(point_forecast, ref, bt_actual)
            if analog_reason:
                reasons.append(analog_reason)

        return PlausibilityResult(
            unstable=bool(reasons),
            reasons=reasons,
            seasonal=True,
            reference_value=ref,
            deviation_pct=deviation * 100 if deviation is not None else None,
            seasonal_anchor_raw=anchor.anchor_raw,
            seasonal_scale_ratio=anchor.scale_ratio,
        )

    candidate_vals = [v for m, v in full_y.items() if m != "Ensemble_top3_weighted"]
    if not candidate_vals:
        return PlausibilityResult(False, ["no candidate models"], seasonal=False)

    ref = float(np.median(candidate_vals))
    reasons = []
    if not ref:
        reasons.append("median of candidate models is zero/undefined")
        deviation = None
    else:
        deviation = abs(point_forecast - ref) / ref
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

    if bt_chosen_pred is not None:
        analog_reason = _analogous_change_reason(point_forecast, ref, bt_actual)
        if analog_reason:
            reasons.append(analog_reason)

    return PlausibilityResult(
        unstable=bool(reasons),
        reasons=reasons,
        seasonal=False,
        reference_value=ref,
        deviation_pct=deviation * 100 if deviation is not None else None,
    )
