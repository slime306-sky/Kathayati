from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp. All timestamps in Kathayati are naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
