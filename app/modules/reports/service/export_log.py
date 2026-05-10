"""
service/export_log.py
----------------------
Export logging: write to ReportExportLog + AuditLog, read history.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import desc, func

from app.config.extensions import db
from app.model.entities.audit_log import AuditLog
from app.model.entities.report_export_log import ReportExportLog

from ._helpers import _actor_name

log = logging.getLogger(__name__)


def log_report_export(
    report_type: str,
    fmt: str,
    file_name: str,
    filters: dict | None = None,
    status: str = "completed",
    error_message: str | None = None,
) -> ReportExportLog:
    """Record an export in ReportExportLog and AuditLog."""
    entry = ReportExportLog(
        report_type=report_type,
        format=fmt,
        generated_by=_actor_name(),
        file_name=file_name,
        filters_json=json.dumps(filters, default=str) if filters else None,
        status=status,
        error_message=error_message,
    )
    db.session.add(entry)

    audit = AuditLog(
        actor=_actor_name(),
        action="export",
        detail=f"{report_type}|{file_name}",
        level="info" if status == "completed" else "warning",
    )
    db.session.add(audit)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return entry


def get_export_history(*, page: int = 1, per_page: int = 25) -> dict[str, Any]:
    """Paginated export history from ReportExportLog."""
    q = ReportExportLog.query.order_by(desc(ReportExportLog.generated_at))
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "pagination": pagination,
        "items": pagination.items,
    }


def get_recent_exports(limit: int = 5) -> list[dict[str, Any]]:
    """Fetch the most recent exports for the index sidebar."""
    entries = (
        ReportExportLog.query
        .filter(ReportExportLog.status == "completed")
        .order_by(desc(ReportExportLog.generated_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "actor":       e.generated_by,
            "report_type": e.report_type,
            "format":      e.format,
            "filename":    e.file_name or "",
            "date":        e.generated_at,
            "status":      e.status,
        }
        for e in entries
    ]


def get_last_exports_by_type() -> dict[str, ReportExportLog]:
    """Return the most recent completed export for each report_type."""
    subq = (
        db.session.query(
            ReportExportLog.report_type,
            func.max(ReportExportLog.generated_at).label("max_at"),
        )
        .filter(ReportExportLog.status == "completed")
        .group_by(ReportExportLog.report_type)
        .subquery()
    )

    rows = (
        ReportExportLog.query
        .join(
            subq,
            db.and_(
                ReportExportLog.report_type == subq.c.report_type,
                ReportExportLog.generated_at == subq.c.max_at,
            ),
        )
        .all()
    )

    return {r.report_type: r for r in rows}


def get_last_general_export():
    """Return last completed general export (or None)."""
    return (
        ReportExportLog.query
        .filter(
            ReportExportLog.report_type == "general",
            ReportExportLog.status == "completed",
        )
        .order_by(desc(ReportExportLog.generated_at))
        .first()
    )
