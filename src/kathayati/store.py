"""Store access. A store is any object implementing the SQLStore interface."""
from __future__ import annotations

import threading

from .config import get_settings

_store = None
_lock = threading.Lock()


def get_store():
    global _store
    with _lock:
        if _store is None:
            from .sql_store import SQLStore  # imported lazily: needs SQLAlchemy

            _store = SQLStore(get_settings().database_url)
        return _store


def set_store(store) -> None:
    """Inject a custom store (tests, or a non-SQL backend)."""
    global _store
    with _lock:
        _store = store


def reset_store() -> None:
    global _store
    with _lock:
        if _store is not None and hasattr(_store, "dispose"):
            _store.dispose()
        _store = None
