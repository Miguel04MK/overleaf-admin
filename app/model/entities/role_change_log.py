"""
RoleChangeLog entity — audit trail for all role assignment changes.

Records every assign / change / remove action on a user's role.

The ``role_from_name`` / ``role_to_name`` columns are **snapshot fields**:
they capture the role name at the time of the change so the history stays
readable even after a role is deleted (which SET NULLs the FK).
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

    # Snapshot: role name at the time of the change (survives role deletion)
    role_from_name = db.Column(db.String(64), nullable=True)
    role_to_name   = db.Column(db.String(64), nullable=True)

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

    # ── Display helpers ──────────────────────────────────────────────────────

    @property
    def display_role_from(self) -> str:
        """Human-readable label for the *previous* role."""
        # 1. FK relationship still alive → role exists
        if self.role_from is not None:
            return self.role_from.name
        # 2. No FK but we have a snapshot name → role was deleted
        if self.role_from_name:
            return f"{self.role_from_name} (eliminado)"
        # 3. No FK id at all → user had no role
        if self.role_from_id is None:
            return "Sin rol"
        # 4. FK id present but relationship is None and no snapshot → unknown
        return "Rol no disponible"

    @property
    def display_role_to(self) -> str:
        """Human-readable label for the *new* role."""
        if self.role_to is not None:
            return self.role_to.name
        if self.role_to_name:
            return f"{self.role_to_name} (eliminado)"
        if self.role_to_id is None:
            return "Sin rol"
        return "Rol no disponible"

    @property
    def display_role_from_color(self) -> str:
        """Bootstrap color for the previous role badge."""
        if self.role_from is not None:
            return self.role_from.color
        return "secondary"

    @property
    def display_role_to_color(self) -> str:
        """Bootstrap color for the new role badge."""
        if self.role_to is not None:
            return self.role_to.color
        return "secondary"

    def __repr__(self) -> str:
        return f"<RoleChangeLog user={self.user_id} {self.action} at {self.changed_at}>"
