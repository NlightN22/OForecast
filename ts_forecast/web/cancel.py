from __future__ import annotations

import threading

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
