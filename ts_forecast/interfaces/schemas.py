from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


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


class ForecastResponse(BaseModel):
    rows_in: int
    rows_after_fill: int
    missing_months_filled: int
    chosen_dataset: str
    chosen_model: str
    metrics: List[Dict[str, Any]]
    backtest: List[Dict[str, Any]]
    next_month: str
    intervals: List[Dict[str, Any]]
