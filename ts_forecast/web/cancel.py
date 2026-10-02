from __future__ import annotations

import threading
import time

CANCEL_TTL_SECONDS = 3600

CANCEL_EVENTS: dict[str, threading.Event] = {}
CANCEL_CREATED_AT: dict[str, float] = {}
ACTIVE_RUN_IDS: set[str] = set()
CANCEL_LOCK = threading.Lock()


def get_cancel_event(run_id: str) -> threading.Event:
    with CANCEL_LOCK:
        event = CANCEL_EVENTS.get(run_id)
        if event is None:
            event = threading.Event()
            CANCEL_EVENTS[run_id] = event
            CANCEL_CREATED_AT[run_id] = time.monotonic()
        return event


def mark_run_active(run_id: str) -> None:
    """Every worker (job thread or /forecast/stream thread) must call this
    right after get_cancel_event(), so the TTL sweep below never evicts an
    event a running worker still holds by direct reference."""
    with CANCEL_LOCK:
        ACTIVE_RUN_IDS.add(run_id)


def clear_cancel_event(run_id: str) -> None:
    with CANCEL_LOCK:
        CANCEL_EVENTS.pop(run_id, None)
        CANCEL_CREATED_AT.pop(run_id, None)
        ACTIVE_RUN_IDS.discard(run_id)


def sweep_stale_cancel_events(max_age_seconds: float = CANCEL_TTL_SECONDS) -> None:
    """Drop cancel events that were created (e.g. by a cancel request racing
    ahead of its worker, or an orphan cancel for an unknown run_id) and never
    cleared by a finished worker, so CANCEL_EVENTS does not grow unbounded.

    Entries in ACTIVE_RUN_IDS are always skipped: a running worker holds its
    Event by direct reference, and a cancel request arriving after the sweep
    would otherwise create a new, unobserved Event, making the job silently
    uncancellable.
    """
    now = time.monotonic()
    with CANCEL_LOCK:
        stale = [
            rid
            for rid, created in CANCEL_CREATED_AT.items()
            if rid not in ACTIVE_RUN_IDS and now - created > max_age_seconds
        ]
        for rid in stale:
            CANCEL_EVENTS.pop(rid, None)
            CANCEL_CREATED_AT.pop(rid, None)
