"""Exceptions raised by Kathayati."""


class NotifyError(Exception):
    """Base class for all Kathayati errors."""


class ConfigurationError(NotifyError):
    """Settings are missing or invalid."""


class UnknownChannelError(NotifyError):
    """The requested channel is not registered."""


class InvalidRecipientError(NotifyError):
    """The recipient is not valid for the channel."""


class TemplateNotFoundError(NotifyError):
    """No template file with that name exists."""


class TemplateRenderError(NotifyError):
    """A template is malformed or referenced data that was not provided."""


class DeliveryError(NotifyError):
    """Delivery failed for a reason that may be temporary. The worker retries."""


class PermanentDeliveryError(DeliveryError):
    """Delivery failed and retrying cannot help (e.g. recipient rejected)."""
