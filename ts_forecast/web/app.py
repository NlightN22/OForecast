from __future__ import annotations

import html
import queue
import threading

from fastapi import Body, FastAPI, Form
from fastapi.responses import HTMLResponse, StreamingResponse

from ..core.config import ForecastConfig
from ..core.models import model_catalog
from ..core.service import run_forecast, format_result_text
from ..interfaces.schemas import ForecastRequest, ForecastResponse

app = FastAPI(title="OForecast", version="0.1.0")

CFG = ForecastConfig()
MODEL_OPTIONS = model_catalog(CFG.ets_trends, CFG.ets_seasonals)


def render_form(
    selected_models: list[str] | None = None,
    use_all: bool = True,
    fill_missing_with_mean: bool = False,
) -> str:
    selected = set(selected_models or [])
    options_html = "\n".join(
        f'<option value="{html.escape(name)}"{" selected" if (use_all or name in selected) else ""}>'
        f"{html.escape(name)}</option>"
        for name in MODEL_OPTIONS
    )
    use_all_checked = " checked" if use_all else ""
    fill_checked = " checked" if fill_missing_with_mean else ""
    return f"""<!doctype html>
<meta charset="utf-8">
<title>OForecast</title>
<style>
body {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; padding: 24px; }}
textarea {{ width: 100%; max-width: 900px; height: 320px; }}
select {{ width: 100%; max-width: 900px; height: 180px; }}
pre {{ white-space: pre-wrap; background: #f6f6f6; padding: 12px; border: 1px solid #ddd; }}
</style>
<h1>OForecast</h1>
<form id="forecast-form" method="post" action="/forecast/form">
  <textarea id="raw" name="raw" placeholder="Paste data here (same format as data.txt)"></textarea>
  <div>
    <label><input type="checkbox" id="fill_missing_with_mean" name="fill_missing_with_mean"{fill_checked}> Fill missing months by interpolation</label>
  </div>
  <div>
    <label><input type="checkbox" id="use_all" name="use_all"{use_all_checked}> Use all models</label>
  </div>
  <div>
    <select id="models" name="models" multiple>
      {options_html}
    </select>
  </div>
  <br><button id="run-btn" type="submit">Run forecast</button>
</form>
<h2>Progress</h2>
<pre id="log"></pre>
<script>
const form = document.getElementById("forecast-form");
const log = document.getElementById("log");
const rawInput = document.getElementById("raw");
const modelsSelect = document.getElementById("models");
const useAll = document.getElementById("use_all");
const fillMissing = document.getElementById("fill_missing_with_mean");
const syncModels = () => {{
  modelsSelect.disabled = useAll.checked;
}};
useAll.addEventListener("change", syncModels);
syncModels();
form.addEventListener("submit", async (e) => {{
  e.preventDefault();
  log.textContent = "";
  const selected = Array.from(modelsSelect.selectedOptions).map((o) => o.value);
  const payload = {{
    raw: rawInput.value,
    models: selected,
    use_all: useAll.checked,
    fill_missing_with_mean: fillMissing.checked
  }};
  const resp = await fetch("/forecast/stream", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify(payload)
  }});
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {{
    const {{ value, done }} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {{ stream: true }});
    const parts = buffer.split("\\n\\n");
    buffer = parts.pop();
    for (const part of parts) {{
      const lines = part.split("\\n");
      for (const line of lines) {{
        if (!line.startsWith("data:")) continue;
        let msg = line.slice(5);
        if (msg.startsWith(" ")) msg = msg.slice(1);
        if (msg === "[done]") continue;
        log.textContent += msg + "\\n";
        log.scrollTop = log.scrollHeight;
      }}
    }}
  }}
}});
</script>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return render_form()


@app.post("/forecast", response_model=ForecastResponse)
def forecast_json(payload: ForecastRequest) -> ForecastResponse:
    res = run_forecast(
        payload.raw,
        models=payload.models,
        use_all=payload.use_all,
        fill_missing_with_mean=payload.fill_missing_with_mean,
    )
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
def forecast_form(
    raw: str = Form(...),
    models: list[str] = Form(default=[]),
    use_all: bool = Form(False),
    fill_missing_with_mean: bool = Form(False),
) -> str:
    res = run_forecast(
        raw,
        models=models,
        use_all=use_all,
        fill_missing_with_mean=fill_missing_with_mean,
    )
    text = html.escape(format_result_text(res))
    return (
        render_form(
            selected_models=models,
            use_all=use_all,
            fill_missing_with_mean=fill_missing_with_mean,
        )
        + f"<h2>Result</h2><pre>{text}</pre>"
    )


@app.post("/forecast/stream")
def forecast_stream(payload: ForecastRequest) -> StreamingResponse:
    q: queue.Queue[tuple[str, str]] = queue.Queue()
    done = threading.Event()

    def on_log(msg: str) -> None:
        q.put(("log", msg))

    def worker() -> None:
        try:
            res = run_forecast(
                payload.raw,
                on_log=on_log,
                models=payload.models,
                use_all=payload.use_all,
                fill_missing_with_mean=payload.fill_missing_with_mean,
            )
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
