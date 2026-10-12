"""SQLAlchemy-backed store: history table and work queue in one."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import event

from .util import utcnow

TABLE_NAME = "kathayati_notifications"  # prefixed so it can't clash with an app's own table

metadata = sa.MetaData()

notifications = sa.Table(
    TABLE_NAME,
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("template", sa.String(200), nullable=False),
    sa.Column("channel", sa.String(50), nullable=False),
    sa.Column("recipient", sa.String(512), nullable=False),
    # pending -> sending -> sent | pending (retry) | failed
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False),
    sa.Column("max_attempts", sa.Integer, nullable=False),
    sa.Column("save_history", sa.Boolean, nullable=False),
    sa.Column("payload", sa.JSON, nullable=False),  # rendered, channel-specific
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("updated_at", sa.DateTime, nullable=False),
    sa.Column("next_attempt_at", sa.DateTime, nullable=False),
    sa.Column("locked_at", sa.DateTime),
    sa.Column("sent_at", sa.DateTime),
    sa.Column("last_error", sa.Text),
    sa.Column("meta", sa.JSON),  # free-form, for future extensions
    sa.Index("ix_kathayati_queue", "status", "next_attempt_at"),
    sa.Index("ix_kathayati_recipient", "recipient"),
)
_t = notifications


class SQLStore:
    def __init__(self, database_url: str):
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        is_sqlite = database_url.startswith("sqlite")
        if is_sqlite:
            kwargs["connect_args"] = {"timeout": 15}
        self.engine = sa.create_engine(database_url, **kwargs)
        if is_sqlite:
            @event.listens_for(self.engine, "connect")
            def _wal(dbapi_conn, _record):  # lets the app and the worker share a file
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()

    def dispose(self) -> None:
        self.engine.dispose()

    def init_db(self) -> None:
        metadata.create_all(self.engine)

    # -- producer ---------------------------------------------------------------

    def insert(self, *, id: str, template: str, channel: str, recipient: str, payload: dict,
               save_history: bool, max_attempts: int, meta: dict | None = None,
               connection=None) -> None:
        now = utcnow()
        stmt = sa.insert(_t).values(
            id=id, template=template, channel=channel, recipient=recipient,
            status="pending", attempts=0, max_attempts=max_attempts,
            save_history=save_history, payload=payload, meta=meta or {},
            created_at=now, updated_at=now, next_attempt_at=now,
        )
        if connection is not None:  # caller's transaction: enqueue commits/rolls back with it
            connection.execute(stmt)
        else:
            with self.engine.begin() as conn:
                conn.execute(stmt)

    # -- worker -----------------------------------------------------------------

    def claim_next(self, lock_timeout_seconds: float) -> dict | None:
        """Atomically claim one due notification (attempts is incremented on claim).

        Portable compare-and-swap: the UPDATE repeats the 'claimable' condition,
        so if another worker got there first, rowcount is 0 and we try the next.
        """
        now = utcnow()
        stale = now - timedelta(seconds=lock_timeout_seconds)
        claimable = sa.or_(
            sa.and_(_t.c.status == "pending", _t.c.next_attempt_at <= now),
            sa.and_(_t.c.status == "sending", _t.c.locked_at <= stale),
        )
        with self.engine.begin() as conn:
            ids = conn.execute(
                sa.select(_t.c.id).where(claimable).order_by(_t.c.next_attempt_at).limit(10)
            ).scalars().all()
            for nid in ids:
                res = conn.execute(
                    sa.update(_t).where(_t.c.id == nid, claimable)
                    .values(status="sending", locked_at=now, updated_at=now,
                            attempts=_t.c.attempts + 1)
                )
                if res.rowcount == 1:
                    return dict(conn.execute(sa.select(_t).where(_t.c.id == nid)).mappings().one())
        return None

    def mark_sent(self, id: str, *, delete: bool) -> None:
        now = utcnow()
        with self.engine.begin() as conn:
            if delete:
                conn.execute(sa.delete(_t).where(_t.c.id == id))
            else:
                conn.execute(sa.update(_t).where(_t.c.id == id).values(
                    status="sent", sent_at=now, updated_at=now, locked_at=None))

    def mark_retry(self, id: str, *, error: str, delay_seconds: float) -> None:
        now = utcnow()
        with self.engine.begin() as conn:
            conn.execute(sa.update(_t).where(_t.c.id == id).values(
                status="pending", last_error=error, updated_at=now, locked_at=None,
                next_attempt_at=now + timedelta(seconds=delay_seconds)))

    def mark_failed(self, id: str, *, error: str, scrub_payload: bool) -> None:
        now = utcnow()
        values: dict[str, Any] = dict(status="failed", last_error=error, updated_at=now, locked_at=None)
        if scrub_payload:
            values["payload"] = {}
        with self.engine.begin() as conn:
            conn.execute(sa.update(_t).where(_t.c.id == id).values(**values))

    # -- history ----------------------------------------------------------------

    def get(self, id: str, *, include_payload: bool = False) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(_t).where(_t.c.id == id)).mappings().first()
        return _clean(row, include_payload)

    def list_notifications(self, *, recipient: str | None = None, status: str | None = None,
                           template: str | None = None, channel: str | None = None,
                           limit: int = 50, include_payload: bool = False) -> list[dict]:
        stmt = sa.select(_t).order_by(_t.c.created_at.desc()).limit(limit)
        for col, val in ((_t.c.recipient, recipient), (_t.c.status, status),
                         (_t.c.template, template), (_t.c.channel, channel)):
            if val is not None:
                stmt = stmt.where(col == val)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [_clean(r, include_payload) for r in rows]


def _clean(row, include_payload: bool) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    if not include_payload:
        d.pop("payload", None)
    return d
