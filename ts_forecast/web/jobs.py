from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from fastapi import APIRouter, HTTPException, Response

from ..core.service import run_forecast
from ..interfaces.schemas import ForecastRequest, ForecastResponse, forecast_response_from_result
from .cancel import clear_cancel_event, get_cancel_event, sweep_stale_cancel_events

JobState = Literal["running", "done", "error"]

JOB_TTL_SECONDS = 3600


@dataclass
class Job:
    status: JobState = "running"
    result: ForecastResponse | None = None
    error: str | None = None
    finished_at: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()

router = APIRouter()


def _sweep_finished_jobs(max_age_seconds: float = JOB_TTL_SECONDS) -> None:
    """Evict completed/errored jobs older than the TTL so JOBS does not grow
    unbounded over the process lifetime."""
    now = time.monotonic()
    with JOBS_LOCK:
        stale = [
            run_id
            for run_id, job in JOBS.items()
            if job.finished_at is not None and now - job.finished_at > max_age_seconds
        ]
        for run_id in stale:
            JOBS.pop(run_id, None)


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
            job.finished_at = time.monotonic()
    except Exception as exc:
        with job.lock:
            job.status = "error"
            job.error = str(exc)
            job.finished_at = time.monotonic()
    finally:
        clear_cancel_event(run_id)


@router.post("/forecast/jobs", status_code=202)
def create_forecast_job(payload: ForecastRequest, response: Response) -> dict:
    _sweep_finished_jobs()
    sweep_stale_cancel_events()
    run_id = payload.run_id or str(uuid.uuid4())

    with JOBS_LOCK:
        existing = JOBS.get(run_id)
        if existing is not None:
            with existing.lock:
                status = existing.status
            if status == "error":
                # Idempotent resubmit must allow retrying a failed run under the same run_id.
                JOBS[run_id] = Job()
            else:
                response.status_code = 200 if status != "running" else 202
                return {"run_id": run_id, "status": status}
        else:
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
