"""Settings. Configure explicitly with configure(...) or via KATHAYATI_* env vars."""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

from .errors import ConfigurationError


@dataclass
class SMTPSettings:
    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    security: str = "starttls"  # "starttls" | "ssl" | "none"
    timeout: float = 20.0

    def __post_init__(self) -> None:
        if self.security not in ("starttls", "ssl", "none"):
            raise ConfigurationError("SMTP security must be 'starttls', 'ssl' or 'none'")

    def __repr__(self) -> str:  # never leak the password into logs
        return (f"SMTPSettings(host={self.host!r}, port={self.port}, "
                f"username={self.username!r}, security={self.security!r})")


@dataclass
class Settings:
    database_url: str = "sqlite:///kathayati.db"
    template_dir: str | Path = "notification-template"
    from_address: str = "noreply@localhost"
    smtp: SMTPSettings | None = None
    resend_api_key: str | None = field(default=None, repr=False)
    max_attempts: int = 5
    retry_base_seconds: float = 30.0   # delay after attempt n: base * 2**(n-1) ...
    retry_max_seconds: float = 3600.0  # ... capped here
    lock_timeout_seconds: float = 300.0  # a 'sending' row older than this is presumed orphaned

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        d = cls()
        smtp = None
        if env.get("KATHAYATI_SMTP_HOST"):
            smtp = SMTPSettings(
                host=env["KATHAYATI_SMTP_HOST"],
                port=int(env.get("KATHAYATI_SMTP_PORT", 587)),
                username=env.get("KATHAYATI_SMTP_USERNAME") or None,
                password=env.get("KATHAYATI_SMTP_PASSWORD") or None,
                security=env.get("KATHAYATI_SMTP_SECURITY", "starttls"),
            )
        return cls(
            database_url=env.get("KATHAYATI_DATABASE_URL", d.database_url),
            template_dir=env.get("KATHAYATI_TEMPLATE_DIR", d.template_dir),
            from_address=env.get("KATHAYATI_FROM_ADDRESS", d.from_address),
            smtp=smtp,
            resend_api_key=env.get("KATHAYATI_RESEND_API_KEY") or None,
            max_attempts=int(env.get("KATHAYATI_MAX_ATTEMPTS", d.max_attempts)),
        )


_settings: Settings | None = None
_lock = threading.Lock()


def get_settings() -> Settings:
    """Current settings; falls back to KATHAYATI_* environment variables."""
    global _settings
    with _lock:
        if _settings is None:
            _settings = Settings.from_env()
        return _settings


def configure(settings: Settings | None = None, **overrides) -> Settings:
    """Set configuration. Pass a Settings object and/or keyword overrides."""
    global _settings
    base = settings or Settings.from_env()
    with _lock:
        _settings = replace(base, **overrides) if overrides else base
    _reset_runtime()
    return _settings


def _reset_runtime() -> None:
    from . import channels, store, templates

    store.reset_store()
    templates.reset_loader()
    channels.reset_channels()
