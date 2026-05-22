import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("crm.utils")


def parse_json_field(value: str | None) -> dict | list | None:
    """Safely deserialise a JSON string stored in a text column.

    Returns None (not raises) on malformed input so bad data never crashes
    a read path.
    """
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("parse_json_field: could not parse value: %.80r", value)
        return None


def to_json_field(value: dict | list | None) -> str | None:
    """Serialise a dict or list to a compact JSON string for storage.

    Returns None when given None so callers can do direct column assignment.
    """
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def utcnow() -> datetime:
    """Return the current UTC datetime with timezone info attached."""
    return datetime.now(tz=timezone.utc)


def days_ago(n: int) -> datetime:
    """Return a timezone-aware UTC datetime exactly *n* days in the past."""
    return utcnow() - timedelta(days=n)
