"""
SyncSchedule entity — múltiples programaciones de sincronización periódica.

Cada fila representa un "job" que ejecuta `run_sync(sync_type=...)` cada
`interval_minutes`. El campo `enabled` permite pausar sin perder la config.
`scheduled_hour` (0-23) fija la hora del día a la que se ejecuta; si es None
se usa el intervalo puro (próxima ejecución = última + intervalo).
"""
from datetime import datetime, timezone

from app.config.extensions import db


# Mínimo: 12 horas. Presets disponibles en la UI.
INTERVAL_PRESETS: list[tuple[int, str]] = [
    (720,   "Cada 12 horas"),
    (1440,  "Cada día"),
    (4320,  "Cada 3 días"),
    (7200,  "Cada 5 días"),
    (10080, "Cada semana"),
    (20160, "Cada 2 semanas"),
    (43200, "Cada mes"),
]

# Intervalo mínimo permitido (12 h)
MIN_INTERVAL_MINUTES: int = 720

SYNC_TYPE_CHOICES: list[str] = ["full", "users", "projects"]

# Horas seleccionables (0-23)
HOUR_CHOICES: list[tuple[int, str]] = [
    (h, f"{h:02d}:00") for h in range(24)
]


class SyncSchedule(db.Model):
    __tablename__ = "sync_schedules"

    id   = db.Column(db.Integer,        primary_key=True)
    name = db.Column(db.String(128),    nullable=False)

    sync_type        = db.Column(db.String(32), nullable=False, default="full")
    interval_minutes = db.Column(db.Integer,    nullable=False, default=1440)
    scheduled_hour   = db.Column(db.Integer,    nullable=True)   # 0-23, None = sin hora fija
    enabled          = db.Column(db.Boolean,    nullable=False, default=True)

    last_run_at = db.Column(db.DateTime(timezone=True), nullable=True)
    next_run_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by = db.Column(db.String(128), nullable=True)

    @property
    def interval_label(self) -> str:
        """Etiqueta legible del intervalo."""
        for m, lbl in INTERVAL_PRESETS:
            if m == self.interval_minutes:
                return lbl
        d = self.interval_minutes // 1440
        if d and self.interval_minutes % 1440 == 0:
            return f"Cada {d} días"
        h = self.interval_minutes // 60
        if h and self.interval_minutes % 60 == 0:
            return f"Cada {h}h"
        return f"Cada {self.interval_minutes} min"

    @property
    def scheduled_hour_label(self) -> str | None:
        """Etiqueta legible de la hora programada, o None."""
        if self.scheduled_hour is None:
            return None
        return f"{self.scheduled_hour:02d}:00"

    @property
    def sync_type_label(self) -> str:
        return {
            "full":     "Completa",
            "users":    "Solo usuarios",
            "projects": "Solo proyectos",
        }.get(self.sync_type, self.sync_type)

    def __repr__(self) -> str:
        return f"<SyncSchedule #{self.id} {self.name} ({self.sync_type}/{self.interval_minutes}m)>"
