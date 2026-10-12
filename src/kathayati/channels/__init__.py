"""Channel registry. Add a channel with register_channel(); no other code changes."""
from __future__ import annotations

import threading
from typing import Callable, Union

from ..config import Settings, get_settings
from ..errors import UnknownChannelError
from .base import Channel
from .email import EmailChannel
from .resend import ResendChannel

ChannelFactory = Union[Channel, Callable[[Settings], Channel]]

_factories: dict[str, ChannelFactory] = {"email": EmailChannel, "resend": ResendChannel}
_instances: dict[str, Channel] = {}
_lock = threading.Lock()


def register_channel(name: str, channel: ChannelFactory) -> None:
    """Register a Channel instance, or a callable(settings) -> Channel.

    Must also run in the worker process (put it in the code both import).
    """
    with _lock:
        _factories[name] = channel
        _instances.pop(name, None)


def get_channel(name: str) -> Channel:
    with _lock:
        if name in _instances:
            return _instances[name]
        factory = _factories.get(name)
        if factory is None:
            raise UnknownChannelError(
                f"Unknown channel {name!r}. Registered: {', '.join(sorted(_factories))}")
        instance = factory if isinstance(factory, Channel) else factory(get_settings())
        _instances[name] = instance
        return instance


def reset_channels() -> None:
    with _lock:
        _instances.clear()


__all__ = ["Channel", "EmailChannel", "ResendChannel", "register_channel", "get_channel", "reset_channels"]
