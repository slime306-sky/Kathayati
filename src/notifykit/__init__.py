"""Kathayati: a small, reusable notification system.

    from kathayati import notify
    notify(template="task-assigned", channel="email",
           recipient=user.email, data={"task": task, "user": user})
"""
from .api import get_notification, init_db, list_notifications, notify
from .channels import Channel, register_channel
from .config import Settings, SMTPSettings, configure
from .errors import (ConfigurationError, DeliveryError, InvalidRecipientError, NotifyError,
                     PermanentDeliveryError, TemplateNotFoundError, TemplateRenderError,
                     UnknownChannelError)

__version__ = "0.1.0"

__all__ = [
    "notify", "init_db", "configure", "get_notification", "list_notifications",
    "register_channel", "Channel", "Settings", "SMTPSettings",
    "NotifyError", "ConfigurationError", "UnknownChannelError", "InvalidRecipientError",
    "TemplateNotFoundError", "TemplateRenderError", "DeliveryError", "PermanentDeliveryError",
]
