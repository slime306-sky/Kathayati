"""Template loading and rendering (Markdown source + Jinja2 placeholders)."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import jinja2
import yaml
from jinja2.sandbox import SandboxedEnvironment

from .errors import TemplateNotFoundError, TemplateRenderError

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$")
_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


@dataclass(frozen=True)
class Template:
    name: str
    body: str
    meta: dict = field(default_factory=dict)


def parse_template(name: str, source: str) -> Template:
    meta: dict = {}
    body = source
    match = _FRONT_MATTER_RE.match(source)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise TemplateRenderError(f"Template {name!r}: invalid front matter: {exc}") from exc
        if not isinstance(meta, dict):
            raise TemplateRenderError(f"Template {name!r}: front matter must be a mapping")
        body = source[match.end():]
    return Template(name=name, body=body.lstrip("\n"), meta=meta)


class TemplateLoader:
    """Loads <directory>/<name>.md, caching until the file changes."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self._cache: dict[str, tuple[int, Template]] = {}

    def load(self, name: str) -> Template:
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise TemplateNotFoundError(f"Invalid template name: {name!r}")
        path = self.directory / f"{name}.md"
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            raise TemplateNotFoundError(f"Template {name!r} not found (looked for {path})") from None
        cached = self._cache.get(name)
        if cached and cached[0] == mtime:
            return cached[1]
        template = parse_template(name, path.read_text(encoding="utf-8"))
        self._cache[name] = (mtime, template)
        return template


# --- rendering ---------------------------------------------------------------

_envs: dict[Any, SandboxedEnvironment] = {}


def _get_env(escape: Callable[[Any], str] | None) -> SandboxedEnvironment:
    env = _envs.get(escape)
    if env is None:
        def finalize(value, _escape=escape):
            if value is None:
                return ""
            return _escape(value) if _escape else value

        env = SandboxedEnvironment(
            undefined=jinja2.StrictUndefined,  # a typo like {{ task.titel }} fails loudly
            finalize=finalize,
            autoescape=False,
            keep_trailing_newline=True,
        )
        _envs[escape] = env
    return env


def render_string(source: str, data: Mapping[str, Any], *,
                  escape: Callable[[Any], str] | None = None,
                  name: str = "<string>") -> str:
    """Render Jinja placeholders. `escape` is applied to every interpolated value."""
    try:
        return _get_env(escape).from_string(source).render(dict(data))
    except jinja2.TemplateError as exc:
        raise TemplateRenderError(f"Template {name!r}: {exc}") from exc


# --- loader singleton ----------------------------------------------------------

_loader: TemplateLoader | None = None
_loader_lock = threading.Lock()


def get_loader() -> TemplateLoader:
    global _loader
    from .config import get_settings

    with _loader_lock:
        if _loader is None:
            _loader = TemplateLoader(get_settings().template_dir)
        return _loader


def reset_loader() -> None:
    global _loader
    with _loader_lock:
        _loader = None
