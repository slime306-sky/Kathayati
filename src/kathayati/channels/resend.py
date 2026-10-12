from __future__ import annotations

from typing import Any

import resend

from ..config import Settings
from ..errors import ConfigurationError, DeliveryError, PermanentDeliveryError
from .email import EmailChannel


class ResendChannel(EmailChannel):
    """Email delivery through the Resend API."""

    name = "resend"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not settings.resend_api_key:
            raise ConfigurationError("Resend is not configured (set RESEND_API_KEY)")
        self.api_key = settings.resend_api_key

    def send(self, recipient: str, payload: dict[str, Any]) -> None:
        resend.api_key = self.api_key
        params = {
            "from": self.settings.from_address,
            "to": [recipient],
            "subject": payload["subject"],
            "html": payload["html"],
            "text": payload["text"],
        }

        try:
            resend.Emails.send(params)
        except (resend.exceptions.InvalidApiKeyError, resend.exceptions.ValidationError) as exc:
            raise PermanentDeliveryError(f"Resend rejected the email: {exc}") from exc
        except resend.exceptions.ResendError as exc:
            raise DeliveryError(f"Resend API failure: {exc}") from exc