from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Any, Mapping

from ..config import Settings, SMTPSettings
from ..errors import DeliveryError, InvalidRecipientError, PermanentDeliveryError
from ..markdown_utils import escape_for_html_markdown, html_to_text, markdown_to_html
from ..templates import Template, render_string
from .base import Channel

_HTML_PREFIX = (
    '<!doctype html><html><head><meta charset="utf-8"></head>'
    '<body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
    'max-width:600px;margin:0 auto;padding:16px;line-height:1.5;color:#222">'
)
_HTML_SUFFIX = "</body></html>"


class EmailChannel(Channel):
    """Email over SMTP. Markdown -> HTML part, plus a plain-text alternative."""

    name = "email"

    def __init__(self, settings: Settings):
        self.settings = settings

    def validate_recipient(self, recipient: Any) -> str:
        if not isinstance(recipient, str):
            raise InvalidRecipientError("Email recipient must be a string")
        value = recipient.strip()
        _, addr = parseaddr(value)
        if not addr or "@" not in addr or "\n" in value or "\r" in value:
            raise InvalidRecipientError(f"Invalid email recipient: {recipient!r}")
        return value

    def render(self, template: Template, data: Mapping[str, Any]) -> dict:
        md = render_string(template.body, data, escape=escape_for_html_markdown, name=template.name)
        body_html = markdown_to_html(md)
        text = html_to_text(body_html)

        subject_src = template.meta.get("subject")
        if subject_src:
            subject = render_string(str(subject_src), data, name=template.name)
        else:  # fall back to the first line of the rendered text (usually the heading)
            subject = text.strip().splitlines()[0] if text.strip() else template.name
        subject = " ".join(subject.split())  # one line, no header injection

        return {"subject": subject, "html": _HTML_PREFIX + body_html + _HTML_SUFFIX, "text": text}

    # -- delivery ---------------------------------------------------------------

    def _connect(self, smtp: SMTPSettings):
        if smtp.security == "ssl":
            server = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=smtp.timeout,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(smtp.host, smtp.port, timeout=smtp.timeout)
        try:
            server.ehlo()
            if smtp.security == "starttls":
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if smtp.username:
                server.login(smtp.username, smtp.password or "")
        except Exception:
            server.close()
            raise
        return server

    def send(self, recipient: str, payload: dict) -> None:
        smtp = self.settings.smtp
        if smtp is None:
            raise DeliveryError("SMTP is not configured (set KATHAYATI_SMTP_HOST or configure(smtp=...))")

        msg = EmailMessage()
        msg["From"] = self.settings.from_address
        msg["To"] = recipient
        msg["Subject"] = payload["subject"]
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        msg.set_content(payload["text"])
        msg.add_alternative(payload["html"], subtype="html")

        try:
            with self._connect(smtp) as server:
                server.send_message(msg)
        except smtplib.SMTPRecipientsRefused as exc:
            raise PermanentDeliveryError(f"Recipient refused: {exc.recipients}") from exc
        except smtplib.SMTPDataError as exc:
            if 500 <= exc.smtp_code < 600:
                raise PermanentDeliveryError(f"Message rejected: {exc.smtp_code} {exc.smtp_error!r}") from exc
            raise DeliveryError(f"SMTP data error: {exc.smtp_code} {exc.smtp_error!r}") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise DeliveryError(f"SMTP failure: {type(exc).__name__}: {exc}") from exc
