from __future__ import annotations

import html
import queue
import threading
import uuid

from fastapi import Body, FastAPI, Form
from fastapi.responses import HTMLResponse, StreamingResponse

from ..core.service import run_forecast, format_result_text
from ..interfaces.schemas import ForecastRequest, ForecastResponse, forecast_response_from_result
from .cancel import clear_cancel_event, get_cancel_event
from .form import render_form
from .jobs import router as jobs_router

app = FastAPI(title="OForecast", version="0.1.0")
app.include_router(jobs_router)


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
    return forecast_response_from_result(res)


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
