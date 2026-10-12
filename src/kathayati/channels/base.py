from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from ..templates import Template


class Channel(ABC):
    """A delivery channel.

    render() runs inside notify(), in the caller's process, while the live data
    is available, and returns a JSON-serialisable payload. send() runs later in
    the worker and only ever sees that payload, never the app's objects.
    """

    name: str

    def validate_recipient(self, recipient: Any) -> str:
        """Return the normalised recipient or raise InvalidRecipientError."""
        return str(recipient)

    @abstractmethod
    def render(self, template: Template, data: Mapping[str, Any]) -> dict:
        ...

    @abstractmethod
    def send(self, recipient: str, payload: dict) -> None:
        """Deliver. Raise DeliveryError (retry) or PermanentDeliveryError (give up)."""
