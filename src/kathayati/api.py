"""The public API: notify() and history lookups."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping

from .channels import get_channel
from .config import get_settings
from .store import get_store
from .templates import get_loader

log = logging.getLogger("kathayati")


def init_db() -> None:
    """Create the notifications table if it doesn't exist (idempotent)."""
    get_store().init_db()


def notify(
    template: str,
    channel: str,
    recipient: Any,
    data: Mapping[str, Any] | None = None,
    *,
    save_history: bool = True,
    max_attempts: int | None = None,
    connection=None,
    fail_silently: bool = False,
) -> str | None:
    """Render a notification now and queue it for delivery. Returns its ID.

    The app says WHAT (template, data, recipient); Kathayati decides HOW.

    Rendering happens here, while your objects are alive, so the worker only
    ever handles a finished payload. Programmer errors (unknown template or
    channel, bad recipient, missing template variable) raise immediately.

    connection:    a SQLAlchemy Connection (e.g. ``session.connection()``) to enqueue
                   inside your own transaction, so the notification exists only if
                   your business write commits. Requires the same database.
    fail_silently: if the *queue insert* fails (database down), log and return None
                   instead of raising. Ignored when ``connection`` is given.
    save_history:  False -> the row is deleted after successful delivery.
    """
    settings = get_settings()
    chan = get_channel(channel)
    recipient = chan.validate_recipient(recipient)
    tpl = get_loader().load(template)
    payload = chan.render(tpl, data or {})

    notification_id = str(uuid.uuid4())
    store = get_store()
    try:
        store.insert(
            id=notification_id, template=template, channel=channel, recipient=recipient,
            payload=payload, save_history=save_history,
            max_attempts=max_attempts or settings.max_attempts, connection=connection,
        )
    except Exception:
        if fail_silently and connection is None:
            log.exception("Kathayati: could not enqueue %s via %s", template, channel)
            return None
        raise
    return notification_id


def get_notification(notification_id: str, *, include_payload: bool = False) -> dict | None:
    return get_store().get(notification_id, include_payload=include_payload)


def list_notifications(**filters) -> list[dict]:
    """Filters: recipient, status, template, channel, limit, include_payload."""
    return get_store().list_notifications(**filters)
