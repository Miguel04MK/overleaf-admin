"""
SyncRun entity — records each synchronization execution.
"""
from datetime import datetime, timezone

from app.config.extensions import db


# Tipos de sincronización aceptados (sync_type)
SYNC_TYPES: list[str] = ["full", "users", "projects", "resync_total", "scheduled"]

# Etiquetas legibles para mostrar en UI / informes
SYNC_TYPE_LABELS: dict[str, str] = {
    "full":         "Completa",
    "users":        "Solo usuarios",
    "projects":     "Solo proyectos",
    "resync_total": "Resincronización total",
    "scheduled":    "Programada",
}


class SyncRun(db.Model):
    __tablename__ = "sync_runs"

    id = db.Column(db.Integer, primary_key=True)

    started_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # "running" | "success" | "partial" | "error"
    status = db.Column(db.String(32), nullable=False, default="running")

    # Tipo de sincronización: full / users / projects / resync_total / scheduled
    sync_type = db.Column(db.String(32), nullable=False, default="full")

    # Contadores agregados (compatibilidad hacia atrás)
    users_found    = db.Column(db.Integer, default=0)
    users_synced   = db.Column(db.Integer, default=0)
    projects_found = db.Column(db.Integer, default=0)
    projects_synced= db.Column(db.Integer, default=0)

    # Desglose creados/actualizados (nuevos)
    users_created    = db.Column(db.Integer, default=0, nullable=False)
    users_updated    = db.Column(db.Integer, default=0, nullable=False)
    projects_created = db.Column(db.Integer, default=0, nullable=False)
    projects_updated = db.Column(db.Integer, default=0, nullable=False)
    members_synced   = db.Column(db.Integer, default=0, nullable=False)

    # Deltas respecto a la sync anterior con éxito (signed)
    users_delta    = db.Column(db.Integer, nullable=True)
    projects_delta = db.Column(db.Integer, nullable=True)

    # "manual" | "scheduled"
    triggered_by = db.Column(db.String(32), nullable=False, default="manual")

    # Username del admin que lanzó la sync manual (NULL si scheduled)
    triggered_by_user = db.Column(db.String(128), nullable=True)

    message      = db.Column(db.Text,    nullable=True)
    errors_count = db.Column(db.Integer, default=0, nullable=False)
    error_detail = db.Column(db.Text,    nullable=True)

    # ── Computed ──────────────────────────────────────────────────────────────
    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def sync_type_label(self) -> str:
        return SYNC_TYPE_LABELS.get(self.sync_type, self.sync_type or "—")

    def mark_finished(
        self,
        status: str,
        message: str | None = None,
        errors_count: int | None = None,
        error_detail: str | None = None,
    ) -> None:
        self.finished_at = datetime.now(timezone.utc)
        self.status = status
        if message is not None:
            self.message = message
        if errors_count is not None:
            self.errors_count = errors_count
        if error_detail is not None:
            self.error_detail = error_detail

    def __repr__(self) -> str:
        return f"<SyncRun #{self.id} {self.status} {self.sync_type} at {self.started_at}>"
