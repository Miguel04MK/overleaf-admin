"""
RoleChangeLog entity — audit trail for all role assignment changes.

Records every assign / change / remove action on a user's role.
"""
from datetime import datetime, timezone

from app.config.extensions import db


class RoleChangeLog(db.Model):
    __tablename__ = "role_change_logs"

    id = db.Column(db.Integer, primary_key=True)

    # Affected user
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("overleaf_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Roles (nullable so we can record "no previous role" or "removed")
    role_from_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )
    role_to_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Action: 'assigned' | 'changed' | 'removed'
    action = db.Column(db.String(16), nullable=False, default="changed")

    # Admin who performed the change (username string — not FK, survives admin deletion)
    changed_by = db.Column(db.String(128), nullable=False, default="system")

    changed_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    reason = db.Column(db.Text, nullable=True)

    # Relationships
    user      = db.relationship("OverleafUser", back_populates="role_change_logs")
    role_from = db.relationship("Role", foreign_keys=[role_from_id])
    role_to   = db.relationship("Role", foreign_keys=[role_to_id])

    def __repr__(self) -> str:
        return f"<RoleChangeLog user={self.user_id} {self.action} at {self.changed_at}>"
