from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..core.result import ForecastResult


class ForecastRequest(BaseModel):
    raw: str = Field(..., description="Raw time series text (tab-separated, same as data.txt)")
    models: List[str] | None = Field(
        default=None,
        description="Optional list of model names to run",
    )
    use_all: bool = Field(
        default=True,
        description="Use all available models (ignores models list when true)",
    )
    fill_missing_with_mean: bool = Field(
        default=False,
        description="Fill missing recognized periods by interpolation; when false, missing periods use 0",
    )
    run_id: str | None = Field(
        default=None,
        description="Optional client run id for cancellation tracking",
    )


class ForecastResponse(BaseModel):
    rows_in: int
    rows_after_fill: int
    missing_periods_filled: int
    chosen_dataset: str
    chosen_model: str
    metrics: List[Dict[str, Any]]
    backtest: List[Dict[str, Any]]
    next_period: str
    intervals: List[Dict[str, Any]]
    seasonal: bool
    plausibility_unstable: bool
    plausibility_reasons: List[str]


def forecast_response_from_result(res: "ForecastResult") -> ForecastResponse:
    return ForecastResponse(
        rows_in=res.rows_in,
        rows_after_fill=res.rows_after_fill,
        missing_periods_filled=res.missing_periods_filled,
        chosen_dataset=res.chosen_dataset,
        chosen_model=res.chosen_model,
        metrics=res.metrics.to_dict(orient="records"),
        backtest=res.backtest.to_dict(orient="records"),
        next_period=res.next_period,
        intervals=[res.intervals],
        seasonal=res.seasonal,
        plausibility_unstable=res.plausibility_unstable,
        plausibility_reasons=res.plausibility_reasons,
    )
