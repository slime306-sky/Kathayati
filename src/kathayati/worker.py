"""The delivery worker: claim -> send -> record, with retry and backoff."""
from __future__ import annotations

import logging
import signal
import threading

from .channels import get_channel
from .config import Settings, get_settings
from .errors import PermanentDeliveryError
from .store import get_store

log = logging.getLogger("kathayati.worker")


def backoff_seconds(attempts: int, settings: Settings) -> float:
    return min(settings.retry_base_seconds * 2 ** max(0, attempts - 1), settings.retry_max_seconds)


def process_one() -> bool:
    """Handle one due notification. Returns False if nothing was due."""
    settings = get_settings()
    store = get_store()
    row = store.claim_next(settings.lock_timeout_seconds)
    if row is None:
        return False

    nid, attempts = row["id"], row["attempts"]
    scrub = not row["save_history"]

    if attempts > row["max_attempts"]:  # a worker died mid-send on the last attempt
        store.mark_failed(nid, error="abandoned: worker died during final attempt", scrub_payload=scrub)
        log.error("notification %s abandoned after %s attempts", nid, attempts - 1)
        return True

    try:
        get_channel(row["channel"]).send(row["recipient"], row["payload"])
    except PermanentDeliveryError as exc:
        store.mark_failed(nid, error=_fmt(exc), scrub_payload=scrub)
        log.error("notification %s failed permanently: %s", nid, exc)
    except Exception as exc:  # DeliveryError and anything unexpected
        if attempts >= row["max_attempts"]:
            store.mark_failed(nid, error=_fmt(exc), scrub_payload=scrub)
            log.error("notification %s failed after %s attempts: %s", nid, attempts, exc)
        else:
            delay = backoff_seconds(attempts, settings)
            store.mark_retry(nid, error=_fmt(exc), delay_seconds=delay)
            log.warning("notification %s attempt %s failed (%s); retry in %.0fs", nid, attempts, exc, delay)
    else:
        store.mark_sent(nid, delete=scrub)
        log.info("notification %s sent via %s", nid, row["channel"])
    return True


def run_worker(*, poll_interval: float = 2.0, once: bool = False,
               stop_event: threading.Event | None = None) -> None:
    """Poll forever (or, with once=True, until nothing is due). SIGINT/SIGTERM stop it cleanly."""
    stop = stop_event or threading.Event()
    if stop_event is None and threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())

    while not stop.is_set():
        try:
            did_work = process_one()
        except Exception:  # e.g. database briefly unavailable
            log.exception("worker loop error")
            did_work = False
        if once and not did_work:
            break
        if not did_work:
            stop.wait(poll_interval)


def _fmt(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:2000]
