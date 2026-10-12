# Kathayati

A small, reusable notification system. The app says **what** to send; Kathayati decides **how** to render, queue and deliver it.

```python
from kathayati import notify

notify(
    template="task-assigned",
    channel="email",
    recipient=user.email,
    data={"task": task, "user": user, "assigned_by": admin},
    save_history=True,   # default
)
```

## Install

```bash
pip install /path/to/project      # or: pip install -e /path/to/project
```

Install the `kathayati` distribution and import from `kathayati`.

## Setup (per project)

1. **Templates**: create a `notification-template/` folder in your project and add Markdown files (see below).
2. **Configure** via environment variables (recommended: the worker reads the same ones) or `configure(...)`:

| Variable | Default | Meaning |
|---|---|---|
| `KATHAYATI_DATABASE_URL` | `sqlite:///kathayati.db` | Any SQLAlchemy URL (use the app's DB to enqueue transactionally) |
| `KATHAYATI_TEMPLATE_DIR` | `notification-template` | Where the `.md` templates live |
| `KATHAYATI_FROM_ADDRESS` | `noreply@localhost` | `"Name <addr>"` is fine |
| `KATHAYATI_SMTP_HOST` / `_PORT` / `_USERNAME` / `_PASSWORD` | – / 587 | Any SMTP server |
| `KATHAYATI_SMTP_SECURITY` | `starttls` | `starttls`, `ssl` or `none` |
| `KATHAYATI_RESEND_API_KEY` | – | Resend API key; required when using `channel="resend"` |
| `KATHAYATI_MAX_ATTEMPTS` | 5 | Delivery attempts before a notification is marked `failed` |

3. **Create the table** once: `kathayati init-db` (or call `init_db()` at app startup).
4. **Run the worker** as its own process next to the app: `kathayati worker`.
   Without a worker, notifications are queued but never sent.

See `examples/fastapi_example.py`.

Resend is available as an alternative email provider. Set `KATHAYATI_RESEND_API_KEY`, use a verified sender domain in `KATHAYATI_FROM_ADDRESS`, and call `notify(..., channel="resend", ...)`. SMTP settings are not used by this channel.

## Templates

`notification-template/task-assigned.md`:

```markdown
---
subject: "Task assigned: {{ task.title }}"
---
# Task Assigned

You have been assigned **{{ task.title }}**.

Assigned by: {{ assigned_by.name }}
```

- `{{ ... }}` is Jinja2 (attribute access, dict access, `{% if %}`, `{% for %}`, filters). It runs in a sandbox.
- A variable that isn't provided raises `TemplateRenderError` at `notify()` time, so typos fail in development, not silently in production.
- Interpolated **values are escaped** for the target channel, so a task title like `<script>` or `# heading` can't inject HTML or Markdown structure. Only the template author controls formatting.
- Supported Markdown subset: headings, paragraphs, bold, italic, inline code, links, lists, blockquotes, horizontal rules. Each channel maps these as well as its platform allows.
- Front matter currently supports `subject` (used by email; defaults to the first line).

## How it works

```
notify()  ->  validate -> load template -> render (channel-specific) -> INSERT row (status=pending)
worker    ->  claim row -> channel.send(payload) -> sent | retry with backoff | failed
```

- **Rendering happens in `notify()`**, while your objects are alive. The queue stores only a finished, JSON payload, so the worker never needs your models, and the email reflects the data as it was when `notify()` was called.
- **The queue is the history table** (`kathayati_notifications`): `id, template, channel, recipient, status, attempts, max_attempts, created_at, updated_at, next_attempt_at, sent_at, last_error, payload, meta`.
- **Retries**: exponential backoff (30s, 60s, 2m, 4m ... capped at 1h). Temporary SMTP failures retry; a rejected recipient (`PermanentDeliveryError`) does not.
- **Delivery is at-least-once.** If a worker crashes after SMTP accepted a message but before recording it, the row is reclaimed after `lock_timeout_seconds` and may send twice. That's rare and the standard trade-off.
- **Multiple workers are safe** (atomic claim). Run as many as you need.

### `save_history=False`

The notification is delivered normally, and the row is **deleted after successful delivery**. Use it for sensitive messages (password resets, one-time codes). Note:
- While pending, the row (with the rendered message) exists, since the queue needs it.
- If delivery ultimately fails, the row is kept (so you can see that something failed and why) but its payload is wiped.

### Transactional enqueue (optional)

```python
with session.begin():
    task.assignee = user
    notify(template="task-assigned", channel="email", recipient=user.email,
           data={...}, connection=session.connection())
```
The notification exists only if your transaction commits. Requires `KATHAYATI_DATABASE_URL` to be the app's database.

### Error policy

- `notify()` raises for programmer errors: unknown template/channel, invalid recipient, missing template variable.
- If the *queue insert* fails (database down), it raises, or with `fail_silently=True` logs and returns `None`.
- Delivery failures never reach your app; they're recorded on the row.

## History

```python
from kathayati import get_notification, list_notifications
get_notification(notification_id)
list_notifications(recipient="bob@example.com", status="failed", limit=20)
```
All timestamps are naive UTC.

## Adding a channel (e.g. Telegram)

```python
from kathayati import Channel, register_channel
from kathayati.markdown_utils import markdown_to_html
from kathayati.templates import render_string

class TelegramChannel(Channel):
    name = "telegram"
    def __init__(self, settings): self.token = ...
    def render(self, template, data):
        md = render_string(template.body, data, escape=escape_for_telegram, name=template.name)
        return {"text": md_to_telegram_html(md)}     # your renderer for the Markdown subset
    def send(self, recipient, payload):
        ...  # call the Bot API; raise DeliveryError (retry) or PermanentDeliveryError (give up)

register_channel("telegram", TelegramChannel)   # callable(settings) or an instance
```
Register it in code that **both the app and the worker import**. Application calls don't change:
`notify(template=..., channel="telegram", recipient=user.telegram_id, data=...)`.

## Not in v1 (on purpose)

Redis/Celery, a central service, user preferences, scheduling, batching, attachments, per-channel template overrides, delivery tracking (opens/bounces), rate limiting, history retention/purge. The store and channel interfaces are where these would plug in.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests     # or: pytest
```
The worker suite runs against both an in-memory store and the real SQLAlchemy store (the latter requires SQLAlchemy installed).
