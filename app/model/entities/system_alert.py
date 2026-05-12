"""
SystemAlert entity — tracks platform incidents, quota issues, sync failures, etc.
"""
import json as _json
from datetime import datetime, timezone

from app.config.extensions import db

ALERT_TYPES = (
    "quota_warning",
    "quota_exceeded",
    "project_limit_warning",
    "project_limit_exceeded",
    "sync_failed",
    "service_down",
    "repeated_errors",
    "many_projects",
    "administrative_warning",
)

ALERT_LEVELS = ("info", "warning", "danger", "critical")

_TYPE_LABELS = {
    "quota_warning":          "Cuota cercana",
    "quota_exceeded":         "Cuota excedida",
    "project_limit_warning":  "Proyectos cercano al límite",
    "project_limit_exceeded": "Límite de proyectos superado",
    "sync_failed":            "Fallo de sincronización",
    "service_down":           "Servicio caído",
    "repeated_errors":        "Errores repetidos",
    "many_projects":          "Muchos proyectos",
    "administrative_warning": "Aviso administrativo",
}

_LEVEL_LABELS = {
    "info":     "Información",
    "warning":  "Aviso",
    "danger":   "Peligro",
    "critical": "Crítico",
}


class SystemAlert(db.Model):
    __tablename__ = "system_alerts"

    id    = db.Column(db.Integer, primary_key=True)

    # Classification
    type  = db.Column(db.String(64),  nullable=False, index=True)
    level = db.Column(db.String(16),  nullable=False, index=True)  # info|warning|danger|critical

    # Content
    title   = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text,        nullable=False)

    # What this alert refers to
    entity_type = db.Column(db.String(32), nullable=True, index=True)  # user|project|sync_run|service|…
    entity_id   = db.Column(db.String(64), nullable=True, index=True)

    # State
    is_read     = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_resolved = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # Timestamps
    created_at  = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Who resolved it and optional comment
    resolved_by        = db.Column(db.String(64), nullable=True)
    resolution_comment = db.Column(db.Text,       nullable=True)

    # Email notification tracking
    email_notified_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)

    # Origin
    created_by_system = db.Column(db.Boolean, default=True, nullable=False)
    source            = db.Column(db.String(64), nullable=True)  # quota_checker|sync_checker|…

    # Arbitrary JSON payload
    extra_data_json = db.Column(db.Text, nullable=True)

    # ── Computed helpers ──────────────────────────────────────────────────────

    @property
    def extra_data(self) -> dict:
        if self.extra_data_json:
            try:
                return _json.loads(self.extra_data_json)
            except Exception:
                return {}
        return {}

    @property
    def type_label(self) -> str:
        return _TYPE_LABELS.get(self.type, self.type)

    @property
    def level_label(self) -> str:
        return _LEVEL_LABELS.get(self.level, self.level)

    @property
    def level_badge_class(self) -> str:
        return {
            "info":     "bg-info text-dark",
            "warning":  "bg-warning text-dark",
            "danger":   "bg-danger",
            "critical": "bg-danger",
        }.get(self.level, "bg-secondary")

    @property
    def level_icon(self) -> str:
        return {
            "info":     "bi-info-circle",
            "warning":  "bi-exclamation-triangle",
            "danger":   "bi-x-octagon",
            "critical": "bi-exclamation-octagon-fill",
        }.get(self.level, "bi-bell")

    def __repr__(self) -> str:
        return f"<SystemAlert #{self.id} [{self.level}] {self.type}>"
