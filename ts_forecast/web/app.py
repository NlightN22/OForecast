from __future__ import annotations

import html
import queue
import threading

from fastapi import Body, FastAPI, Form
from fastapi.responses import HTMLResponse, StreamingResponse

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
<form id="forecast-form" method="post" action="/forecast/form">
  <textarea id="raw" name="raw" placeholder="Вставьте данные как в data.txt"></textarea>
  <br><button id="run-btn" type="submit">Рассчитать</button>
</form>
<h2>Progress</h2>
<pre id="log"></pre>
<script>
const form = document.getElementById("forecast-form");
const log = document.getElementById("log");
const rawInput = document.getElementById("raw");
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  log.textContent = "";
  const resp = await fetch("/forecast/stream", {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: rawInput.value
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\\n\\n");
    buffer = parts.pop();
    for (const part of parts) {
      const line = part.trim();
      if (!line) continue;
      const msg = line.replace(/^data:\\s?/, "");
      if (msg === "[done]") continue;
      log.textContent += msg + "\\n";
      log.scrollTop = log.scrollHeight;
    }
  }
});
</script>
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


@app.post("/forecast/stream")
def forecast_stream(raw: str = Body(..., media_type="text/plain")) -> StreamingResponse:
    q: queue.Queue[tuple[str, str]] = queue.Queue()
    done = threading.Event()

    def on_log(msg: str) -> None:
        q.put(("log", msg))

    def worker() -> None:
        try:
            res = run_forecast(raw, on_log=on_log)
            q.put(("result", format_result_text(res)))
        except Exception as exc:
            q.put(("error", f"ERROR: {exc}"))
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def event_stream():
        yield "data: started\n\n"
        while not done.is_set() or not q.empty():
            try:
                kind, payload = q.get(timeout=0.1)
            except queue.Empty:
                continue
            for line in str(payload).splitlines():
                yield f"data: {line}\n\n"
            if kind in ("result", "error"):
                yield "data: [done]\n\n"
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")
