from __future__ import annotations

import html

from fastapi import Body, FastAPI, Form
from fastapi.responses import HTMLResponse

from ..core.service import run_forecast, format_result_text
from ..interfaces.schemas import ForecastRequest, ForecastResponse

app = FastAPI(title="OForecast", version="0.1.0")

FORM_HTML = """<!doctype html>
<meta charset="utf-8">
<title>OForecast</title>
<style>
body { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; padding: 24px; }
textarea { width: 100%; max-width: 900px; height: 320px; }
pre { white-space: pre-wrap; background: #f6f6f6; padding: 12px; border: 1px solid #ddd; }
</style>
<h1>OForecast</h1>
<form method="post" action="/forecast/form">
  <textarea name="raw" placeholder="Вставьте данные как в data.txt"></textarea>
  <br><button type="submit">Рассчитать</button>
</form>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return FORM_HTML


@app.post("/forecast", response_model=ForecastResponse)
def forecast_json(payload: ForecastRequest) -> ForecastResponse:
    res = run_forecast(payload.raw)
    return ForecastResponse(
        rows_in=res.rows_in,
        rows_after_fill=res.rows_after_fill,
        missing_months_filled=res.missing_months_filled,
        chosen_dataset=res.chosen_dataset,
        chosen_model=res.chosen_model,
        metrics=res.metrics.to_dict(orient="records"),
        backtest=res.backtest.to_dict(orient="records"),
        next_month=res.next_month,
        intervals=res.intervals.to_dict(orient="records"),
    )


@app.post("/forecast/text", response_class=HTMLResponse)
def forecast_text(raw: str = Body(..., media_type="text/plain")) -> str:
    res = run_forecast(raw)
    text = html.escape(format_result_text(res))
    return f"<pre>{text}</pre>"


@app.post("/forecast/form", response_class=HTMLResponse)
def forecast_form(raw: str = Form(...)) -> str:
    res = run_forecast(raw)
    text = html.escape(format_result_text(res))
    return FORM_HTML + f"<h2>Result</h2><pre>{text}</pre>"
