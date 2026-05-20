"""
service/_helpers.py
--------------------
Shared constants and pure-function helpers for the reports service layer.
No Flask context or DB imports — safe to use at module level.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask_login import current_user


# ─── Constants ───────────────────────────────────────────────────────────────

_INACTIVE_DAYS = 90
_LARGE_BYTES   = 10 * 1024 * 1024  # 10 MB


# ─── Pure helpers ─────────────────────────────────────────────────────────────

def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return None


def _fmt_bytes(n) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _split_bytes(n) -> tuple[str, str]:
    """Split a byte count into (number_string, unit) for separate display."""
    if n is None or n == 0:
        return ("0", "B")
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return (f"{n:.1f}", unit)
        n /= 1024.0
    return (f"{n:.1f}", "PB")


def _trend(current: int, previous: int) -> int:
    """Percentage change from previous to current."""
    if previous == 0:
        return 0 if current == 0 else 100
    return round(((current - previous) / previous) * 100)


def _actor_name() -> str:
    """Current admin username or 'system'."""
    if current_user and current_user.is_authenticated:
        return current_user.username
    return "system"
