"""
AuditLog entity — records administrative actions on the platform.
"""
from datetime import datetime, timezone

from app.config.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    # Who performed the action (admin username or "system")
    actor = db.Column(db.String(64), nullable=False, default="system")

    # Action type: "login", "logout", "sync_start", "sync_ok", "sync_error", etc.
    action = db.Column(db.String(64), nullable=False, index=True)

    detail = db.Column(db.Text, nullable=True)

    # "info" | "warning" | "error"
    level = db.Column(db.String(16), nullable=False, default="info")

    ip_address = db.Column(db.String(45), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<AuditLog [{self.level}] {self.actor}: {self.action}>"
