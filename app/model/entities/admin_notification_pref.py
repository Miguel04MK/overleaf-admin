"""
AdminNotificationPref entity — per-admin email notification preferences.

Each AdminUser has at most one row here (unique constraint on admin_id).
When no row exists the notification_service falls back to safe defaults
(critical + danger + service_down + sync_failed + quota_exceeded + repeated_errors).
"""
from app.config.extensions import db


class AdminNotificationPref(db.Model):
    __tablename__ = "admin_notification_prefs"

    id       = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(
        db.Integer, db.ForeignKey("admin_users.id"),
        nullable=False, unique=True, index=True,
    )

    # ── By level ──────────────────────────────────────────────────────────────
    notify_critical = db.Column(db.Boolean, default=True,  nullable=False)
    notify_danger   = db.Column(db.Boolean, default=True,  nullable=False)
    notify_warning  = db.Column(db.Boolean, default=False, nullable=False)
    notify_info     = db.Column(db.Boolean, default=False, nullable=False)

    # ── By type ───────────────────────────────────────────────────────────────
    notify_service_down            = db.Column(db.Boolean, default=True,  nullable=False)
    notify_sync_failed             = db.Column(db.Boolean, default=True,  nullable=False)
    notify_quota_exceeded          = db.Column(db.Boolean, default=True,  nullable=False)
    notify_quota_warning           = db.Column(db.Boolean, default=False, nullable=False)
    notify_project_limit_exceeded  = db.Column(db.Boolean, default=False, nullable=False)
    notify_project_limit_warning   = db.Column(db.Boolean, default=False, nullable=False)
    notify_repeated_errors         = db.Column(db.Boolean, default=True,  nullable=False)
    notify_administrative_warning  = db.Column(db.Boolean, default=False, nullable=False)

    # ── Relationship (adds .notification_pref to AdminUser) ───────────────────
    admin = db.relationship(
        "AdminUser",
        backref=db.backref("notification_pref", uselist=False, lazy="select"),
    )

    # ── Helpers ───────────────────────────────────────────────────────────────

    BOOLEAN_FIELDS: list[str] = [
        "notify_critical", "notify_danger", "notify_warning", "notify_info",
        "notify_service_down", "notify_sync_failed",
        "notify_quota_exceeded", "notify_quota_warning",
        "notify_project_limit_exceeded", "notify_project_limit_warning",
        "notify_repeated_errors", "notify_administrative_warning",
    ]

    def to_dict(self) -> dict:
        return {f: getattr(self, f) for f in self.BOOLEAN_FIELDS}

    def update_from_dict(self, data: dict) -> None:
        for f in self.BOOLEAN_FIELDS:
            if f in data:
                setattr(self, f, bool(data[f]))

    def __repr__(self) -> str:
        return f"<AdminNotificationPref admin_id={self.admin_id}>"
