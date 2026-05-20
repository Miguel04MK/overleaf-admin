"""
exporters/_helpers.py
----------------------
Shared utility functions used by both CSV and PDF exporters.
No heavy dependencies — safe to import anywhere.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime


def _make_csv(filename: str, rows: list[list]) -> tuple[bytes, str, str]:
    """Build a UTF-8 CSV bytes object, filename and content-type."""
    buf = io.StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    data = buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
    return data, filename, "text/csv; charset=utf-8"


def _today_suffix() -> str:
    """Return today's date as dd-mm-yyyy for filenames."""
    return datetime.now().strftime("%d-%m-%Y")


def _ts(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _ts_short(dt: datetime | None) -> str:
    """Compact timestamp for PDF table cells: '07/05/2026 17:53'."""
    return dt.strftime("%d/%m/%Y %H:%M") if dt else ""


def _date(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d") if dt else ""


def _fmt_bytes(n) -> str:
    if n is None:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"
