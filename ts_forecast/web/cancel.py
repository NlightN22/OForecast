from __future__ import annotations

import threading
import time

CANCEL_TTL_SECONDS = 3600

CANCEL_EVENTS: dict[str, threading.Event] = {}
CANCEL_CREATED_AT: dict[str, float] = {}
CANCEL_LOCK = threading.Lock()


def get_cancel_event(run_id: str) -> threading.Event:
    with CANCEL_LOCK:
        event = CANCEL_EVENTS.get(run_id)
        if event is None:
            event = threading.Event()
            CANCEL_EVENTS[run_id] = event
            CANCEL_CREATED_AT[run_id] = time.monotonic()
        return event


def clear_cancel_event(run_id: str) -> None:
    with CANCEL_LOCK:
        CANCEL_EVENTS.pop(run_id, None)
        CANCEL_CREATED_AT.pop(run_id, None)


def sweep_stale_cancel_events(
    active_run_ids: frozenset[str] = frozenset(), max_age_seconds: float = CANCEL_TTL_SECONDS
) -> None:
    """Drop cancel events that were created (e.g. by a cancel request racing
    ahead of its job, or an orphan cancel for an unknown run_id) and never
    cleared by a finished worker, so CANCEL_EVENTS does not grow unbounded.

    `active_run_ids` must list every run_id with a worker still running, so a
    long-running job's event is never swept out from under it: the worker
    thread holds its Event by direct reference, and a cancel request that
    arrives after the sweep would otherwise create a new, unobserved Event.
    """
    now = time.monotonic()
    with CANCEL_LOCK:
        stale = [
            rid
            for rid, created in CANCEL_CREATED_AT.items()
            if rid not in active_run_ids and now - created > max_age_seconds
        ]
        for rid in stale:
            CANCEL_EVENTS.pop(rid, None)
            CANCEL_CREATED_AT.pop(rid, None)
