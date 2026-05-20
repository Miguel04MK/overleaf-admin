"""helpers.py — funciones auxiliares de uso general."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def parse_date(value: str) -> datetime | None:
    """Parse a 'YYYY-MM-DD' string to a UTC-aware datetime. Returns None on error."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def safe_int(value, name: str = "param") -> int | None:
    """Convert *value* to int, returning None if absent or non-numeric.

    Logs a warning instead of raising so a malformed query parameter cannot
    crash the endpoint.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning("safe_int: could not convert %s=%r to int", name, value)
        return None
