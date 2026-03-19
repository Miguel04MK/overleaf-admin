"""
AuditService — records administrative actions to the audit log.
"""
import logging
from datetime import datetime, timezone

from app.extensions import db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def log_action(
    action: str,
    actor: str = "system",
    detail: str | None = None,
    level: str = "info",
    ip_address: str | None = None,
) -> None:
    """Write a single audit log entry. Silently swallows errors to avoid
    cascading failures when the audit log itself has a problem."""
    try:
        entry = AuditLog(
            actor=actor,
            action=action,
            detail=detail,
            level=level,
            ip_address=ip_address,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        logger.error("Failed to write audit log: %s", exc)
        db.session.rollback()


def get_recent_logs(limit: int = 200):
    """Return the most recent audit log entries."""
    return (
        AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    )


def get_paginated_logs(page: int = 1, per_page: int = 30):
    """Return paginated audit log entries."""
    return AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
