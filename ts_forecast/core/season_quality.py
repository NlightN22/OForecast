from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

import numpy as np
import pandas as pd

from .backtest import BacktestResult, walk_forward
from .config import ForecastConfig
from .plausibility import PlausibilityResult, check_plausibility, season_backtest_reason
from .seasonality import SeasonalityInfo, contiguous_month_groups, is_seasonal_model, wape

SHORT_SEASON_DEGRADATION_FACTOR = 1.5

DEEP_BACKTEST_MODEL_DISAGREEMENT = 0.25
DEEP_BACKTEST_SEASONAL_VS_BASE = 0.35
DEEP_BACKTEST_TEST_LEN = 24
DEEP_BACKTEST_TOPK = 3
CONTRADICTORY_HISTORY_CV = 0.5


def disqualify_for_short_season(
    seasonality: SeasonalityInfo,
    target_month: int,
    bt: BacktestResult,
    chosen_name: str,
    all_metrics: dict,
) -> tuple[str, Optional[str]]:
    """Section 5: a model that forecasts the year well on average but
    systematically misses the entry/exit of a short (2-3 month) season
    must not be chosen for that season's months."""
    groups = [g for g in contiguous_month_groups(seasonality.seasonal_months) if len(g) <= 3]
    group = next((g for g in groups if target_month in g), None)
    if group is None or chosen_name not in bt.preds_y:
        return chosen_name, None

    boundary_months = {group[0], group[-1] % 12 + 1}
    idx_boundary = [i for i, p in enumerate(bt.periods) if pd.Timestamp(p).month in boundary_months]
    if not idx_boundary:
        return chosen_name, None

    def boundary_wape(pred: np.ndarray) -> tuple[float, float]:
        return (
            wape(bt.actual_y[idx_boundary], pred[idx_boundary]),
            wape(bt.actual_y, pred),
        )

    chosen_boundary, chosen_overall = boundary_wape(bt.preds_y[chosen_name])
    if (
        np.isnan(chosen_boundary)
        or np.isnan(chosen_overall)
        or chosen_overall == 0
        or chosen_boundary <= chosen_overall * SHORT_SEASON_DEGRADATION_FACTOR
    ):
        return chosen_name, None

    ranked = sorted(
        (m for m in all_metrics if m != chosen_name and m in bt.preds_y),
        key=lambda m: all_metrics[m]["MAE"],
    )
    for alt in ranked:
        alt_boundary, alt_overall = boundary_wape(bt.preds_y[alt])
        if np.isnan(alt_boundary) or np.isnan(alt_overall) or alt_overall == 0:
            continue
        if alt_boundary <= alt_overall * SHORT_SEASON_DEGRADATION_FACTOR:
            return alt, (
                f"{chosen_name} disqualified: season entry/exit WAPE {chosen_boundary:.1f}% "
                f"vs {chosen_overall:.1f}% overall; replaced with {alt}"
            )

    return chosen_name, (
        f"{chosen_name} degrades at season entry/exit (WAPE {chosen_boundary:.1f}% "
        f"vs {chosen_overall:.1f}% overall) but no better alternative is available"
    )


def calendar_month_history_is_contradictory(df: pd.DataFrame, target_month: int) -> bool:
    values = df.loc[df["period_start"].dt.month == target_month, "y"].to_numpy(float)
    if len(values) < 3:
        return False
    mean = float(np.mean(values))
    if mean == 0:
        return False
    cv = float(np.std(values) / abs(mean))
    return cv > CONTRADICTORY_HISTORY_CV


def _should_run_deep_backtest(
    seasonal_model_values: list[float],
    seasonal_forecast: Optional[float],
    nonseasonal_ref: Optional[float],
    short_season_flagged: bool,
    history_contradictory: bool,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if len(seasonal_model_values) >= 2:
        median_val = float(np.median(seasonal_model_values))
        if median_val:
            spread = (max(seasonal_model_values) - min(seasonal_model_values)) / abs(median_val)
            if spread > DEEP_BACKTEST_MODEL_DISAGREEMENT:
                reasons.append(f"seasonal models disagree by {spread:.1%}")
    if seasonal_forecast and nonseasonal_ref:
        diff = abs(seasonal_forecast - nonseasonal_ref) / nonseasonal_ref
        if diff > DEEP_BACKTEST_SEASONAL_VS_BASE:
            reasons.append(f"seasonal vs non-seasonal forecast diverge by {diff:.1%}")
    if short_season_flagged:
        reasons.append("model fails to reproduce season entry/exit")
    if history_contradictory:
        reasons.append("history for this calendar month is contradictory")
    return bool(reasons), reasons


def _run_deep_season_backtest(
    df: pd.DataFrame,
    cfg: ForecastConfig,
    chosen_name: str,
    all_metrics: dict,
    target_month: int,
    on_log: Optional[Callable[[str], None]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
    """Section 6: deeper 24-month backtest over only the top-3 models,
    run only when _should_run_deep_backtest() triggers it."""
    top3 = [m for m, _ in sorted(all_metrics.items(), key=lambda kv: kv[1]["MAE"])[:DEEP_BACKTEST_TOPK]]
    if chosen_name not in top3:
        top3.append(chosen_name)
    deep_cfg = replace(
        cfg,
        test_len_if_ge_48=DEEP_BACKTEST_TEST_LEN,
        test_len_else=min(DEEP_BACKTEST_TEST_LEN, max(len(df) - 1, 1)),
    )
    deep_bt = walk_forward(
        df,
        deep_cfg,
        robust=False,
        include_arima=chosen_name == "AutoARIMA_log",
        allowed_models=set(top3),
        on_log=on_log,
        should_abort=should_abort,
    )
    if chosen_name not in deep_bt.preds_y:
        return None
    reason = season_backtest_reason(deep_bt.periods, deep_bt.actual_y, deep_bt.preds_y[chosen_name], target_month)
    return f"deep {DEEP_BACKTEST_TEST_LEN}m backtest confirms: {reason}" if reason else None


def evaluate_plausibility(
    df: pd.DataFrame,
    cfg: ForecastConfig,
    chosen_name: str,
    short_season_reason: Optional[str],
    target_month: int,
    seasonality: SeasonalityInfo,
    full_y: dict[str, float],
    all_metrics: dict,
    bt: BacktestResult,
    point_y: float,
    on_log: Optional[Callable[[str], None]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> PlausibilityResult:
    """Full plausibility pipeline for one forecast: base checks (section 4),
    the short-season disqualification reason (section 5), and the triggered
    deep-backtest confirmation (section 6)."""
    plausibility = check_plausibility(
        point_forecast=point_y,
        chosen_name=chosen_name,
        target_month=target_month,
        df=df,
        seasonality=seasonality,
        full_y=full_y,
        all_metrics=all_metrics,
        bt_periods=bt.periods,
        bt_actual=bt.actual_y,
        bt_chosen_pred=bt.preds_y.get(chosen_name),
    )
    if short_season_reason:
        plausibility.unstable = True
        plausibility.reasons.append(short_season_reason)

    seasonal_model_values = [v for m, v in full_y.items() if is_seasonal_model(m)]
    nonseasonal_candidates = [v for m, v in full_y.items() if m != "Ensemble_top3_weighted"]
    nonseasonal_ref = float(np.median(nonseasonal_candidates)) if nonseasonal_candidates else None
    history_contradictory = calendar_month_history_is_contradictory(df, target_month)
    run_deep, deep_reasons = _should_run_deep_backtest(
        seasonal_model_values=seasonal_model_values,
        seasonal_forecast=point_y if plausibility.seasonal else None,
        nonseasonal_ref=nonseasonal_ref,
        short_season_flagged=bool(short_season_reason),
        history_contradictory=history_contradictory,
    )
    if run_deep:
        if on_log is not None:
            on_log(f"plausibility: deep backtest triggered ({'; '.join(deep_reasons)})")
        deep_reason = _run_deep_season_backtest(
            df, cfg, chosen_name, all_metrics, target_month, on_log=on_log, should_abort=should_abort
        )
        if deep_reason:
            plausibility.unstable = True
            plausibility.reasons.append(deep_reason)

    return plausibility
