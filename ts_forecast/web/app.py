from __future__ import annotations

import html
import queue
import threading
import uuid

from fastapi import Body, FastAPI, Form
from fastapi.responses import HTMLResponse, StreamingResponse

from ..core.config import ForecastConfig
from ..core.models import model_catalog
from ..core.service import run_forecast, format_result_text
from ..interfaces.schemas import ForecastRequest, ForecastResponse

app = FastAPI(title="OForecast", version="0.1.0")

CFG = ForecastConfig()
MODEL_OPTIONS = model_catalog(CFG.ets_trends, CFG.ets_seasonals)
CANCEL_EVENTS: dict[str, threading.Event] = {}
CANCEL_LOCK = threading.Lock()


def get_cancel_event(run_id: str) -> threading.Event:
    with CANCEL_LOCK:
        event = CANCEL_EVENTS.get(run_id)
        if event is None:
            event = threading.Event()
            CANCEL_EVENTS[run_id] = event
        return event


def clear_cancel_event(run_id: str) -> None:
    with CANCEL_LOCK:
        CANCEL_EVENTS.pop(run_id, None)


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
#scroll-top {{
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 44px;
  height: 44px;
  border: 1px solid #999;
  background: #fff;
  color: #111;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  display: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
}}
#scroll-top.is-visible {{ display: block; }}
</style>
<h1>OForecast</h1>
<form id="forecast-form" method="post" action="/forecast/form">
  <textarea id="raw" name="raw" placeholder="Paste data here (same format as data.txt)"></textarea>
  <div>
    <label><input type="checkbox" id="fill_missing_with_mean" name="fill_missing_with_mean"{fill_checked}> Fill missing recognized periods by interpolation</label>
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
<div style="display: flex; align-items: center; gap: 12px;">
  <h2 style="margin: 0;">Progress</h2>
  <button id="copy-log" type="button">Copy output</button>
  <button id="cancel-run" type="button" disabled>Cancel</button>
  <span id="timer">00:00</span>
</div>
<pre id="log"></pre>
<button id="scroll-top" type="button" aria-label="Back to top" title="Back to top">↑</button>
<script>
const form = document.getElementById("forecast-form");
const log = document.getElementById("log");
const copyBtn = document.getElementById("copy-log");
const cancelBtn = document.getElementById("cancel-run");
const timer = document.getElementById("timer");
const rawInput = document.getElementById("raw");
const modelsSelect = document.getElementById("models");
const useAll = document.getElementById("use_all");
const fillMissing = document.getElementById("fill_missing_with_mean");
const scrollTopBtn = document.getElementById("scroll-top");
let abortController = null;
let timerId = null;
let startTs = 0;
let runId = null;
const syncModels = () => {{
  modelsSelect.disabled = useAll.checked;
}};
useAll.addEventListener("change", syncModels);
syncModels();
const syncScrollTop = () => {{
  scrollTopBtn.classList.toggle("is-visible", window.scrollY > window.innerHeight / 2);
}};
window.addEventListener("scroll", syncScrollTop, {{ passive: true }});
scrollTopBtn.addEventListener("click", () => {{
  window.scrollTo({{ top: 0, behavior: "smooth" }});
}});
syncScrollTop();
form.addEventListener("submit", async (e) => {{
  e.preventDefault();
  log.textContent = "";
  if (timerId) clearInterval(timerId);
  timerId = null;
  cancelBtn.disabled = false;
  startTs = Date.now();
  timer.textContent = "00:00";
  timerId = setInterval(() => {{
    const elapsed = Math.floor((Date.now() - startTs) / 1000);
    const minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const seconds = String(elapsed % 60).padStart(2, "0");
    timer.textContent = `${{minutes}}:${{seconds}}`;
  }}, 1000);
  const selected = Array.from(modelsSelect.selectedOptions).map((o) => o.value);
  runId = (crypto.randomUUID && crypto.randomUUID()) || (Date.now().toString(36) + Math.random().toString(36).slice(2));
  const payload = {{
    raw: rawInput.value,
    models: selected,
    use_all: useAll.checked,
    fill_missing_with_mean: fillMissing.checked,
    run_id: runId
  }};
  abortController = new AbortController();
  try {{
    const resp = await fetch("/forecast/stream", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
      signal: abortController.signal
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
  }} catch (err) {{
    if (err.name === "AbortError") {{
      log.textContent += "cancelled by user\\n";
    }} else {{
      log.textContent += `error: ${{err}}\\n`;
    }}
  }} finally {{
    abortController = null;
    cancelBtn.disabled = true;
    if (timerId) clearInterval(timerId);
    timerId = null;
    runId = null;
  }}
}});
cancelBtn.addEventListener("click", async () => {{
  if (abortController) {{
    abortController.abort();
  }}
  if (runId) {{
    try {{
      await fetch("/forecast/cancel", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ run_id: runId }})
      }});
    }} catch (err) {{}}
  }}
}});
copyBtn.addEventListener("click", async () => {{
  const text = log.textContent.trim();
  if (!text) return;
  try {{
    await navigator.clipboard.writeText(text);
  }} catch (err) {{
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "absolute";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    document.body.removeChild(area);
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
        missing_periods_filled=res.missing_periods_filled,
        chosen_dataset=res.chosen_dataset,
        chosen_model=res.chosen_model,
        metrics=res.metrics.to_dict(orient="records"),
        backtest=res.backtest.to_dict(orient="records"),
        next_period=res.next_period,
        intervals=[res.intervals],
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


@app.post("/forecast/cancel")
def forecast_cancel(run_id: str = Body(..., embed=True)) -> dict:
    event = get_cancel_event(run_id)
    event.set()
    return {"status": "ok"}


@app.post("/forecast/stream")
def forecast_stream(payload: ForecastRequest) -> StreamingResponse:
    q: queue.Queue[tuple[str, str]] = queue.Queue()
    done = threading.Event()
    run_id = payload.run_id or str(uuid.uuid4())
    cancel_event = get_cancel_event(run_id)

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
                should_abort=cancel_event.is_set,
            )
            q.put(("result", format_result_text(res)))
        except Exception as exc:
            q.put(("error", f"ERROR: {exc}"))
        finally:
            clear_cancel_event(run_id)
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
