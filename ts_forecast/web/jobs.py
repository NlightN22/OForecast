from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Literal

from fastapi import APIRouter, HTTPException, Response

from ..core.service import run_forecast
from ..interfaces.schemas import ForecastRequest, ForecastResponse, forecast_response_from_result
from .cancel import clear_cancel_event, get_cancel_event

JobState = Literal["running", "done", "error"]


@dataclass
class Job:
    status: JobState = "running"
    result: ForecastResponse | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()

router = APIRouter()


def _run_job(run_id: str, payload: ForecastRequest) -> None:
    cancel_event = get_cancel_event(run_id)
    job = JOBS[run_id]
    try:
        res = run_forecast(
            payload.raw,
            models=payload.models,
            use_all=payload.use_all,
            fill_missing_with_mean=payload.fill_missing_with_mean,
            should_abort=cancel_event.is_set,
        )
        with job.lock:
            job.status = "done"
            job.result = forecast_response_from_result(res)
    except Exception as exc:
        with job.lock:
            job.status = "error"
            job.error = str(exc)
    finally:
        clear_cancel_event(run_id)


@router.post("/forecast/jobs", status_code=202)
def create_forecast_job(payload: ForecastRequest, response: Response) -> dict:
    run_id = payload.run_id or str(uuid.uuid4())

    with JOBS_LOCK:
        existing = JOBS.get(run_id)
        if existing is not None:
            response.status_code = 200 if existing.status != "running" else 202
            return {"run_id": run_id, "status": existing.status}
        JOBS[run_id] = Job()

    thread = threading.Thread(target=_run_job, args=(run_id, payload), daemon=True)
    thread.start()
    return {"run_id": run_id, "status": "running"}


@router.get("/forecast/jobs/{run_id}")
def get_forecast_job(run_id: str) -> dict:
    with JOBS_LOCK:
        job = JOBS.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown run_id")

    with job.lock:
        body = {"run_id": run_id, "status": job.status}
        if job.status == "done":
            body["result"] = job.result
        elif job.status == "error":
            body["error"] = job.error
        return body
