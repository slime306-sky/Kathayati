"""Minimal FastAPI integration. Run the worker separately: `kathayati worker`."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from kathayati import SMTPSettings, configure, init_db, notify

# Reads KATHAYATI_* env vars by default; explicit configuration shown for clarity.
configure(
    database_url="sqlite:///app.db",           # same DB as your app -> transactional enqueue possible
    template_dir="notification-template",
    from_address="My App <noreply@example.com>",
    smtp=SMTPSettings(host="smtp.example.com", port=587, username="user", password="secret"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # creates the table if missing
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/tasks/{task_id}/assign")
def assign(task_id: int):  # plain `def`: FastAPI runs it in a threadpool, so the DB insert doesn't block the loop
    task = {"title": "Write the report", "url": f"https://app.example.com/tasks/{task_id}"}
    admin = {"name": "Ada"}
    notify(
        template="task-assigned",
        channel="email",
        recipient="bob@example.com",
        data={"task": task, "assigned_by": admin},
    )
    return {"ok": True}
