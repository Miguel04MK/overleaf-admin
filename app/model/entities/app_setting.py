"""
AppSetting entity — key-value store for configurable platform settings.

Keys are plain strings; values are stored as strings and cast on read.
Used for alert thresholds and similar global parameters.
"""
from datetime import datetime, timezone

from app.config.extensions import db

# Default thresholds.  (value, human-readable description)
DEFAULT_THRESHOLDS: dict[str, tuple[str, str]] = {
    "alert.quota_warning_pct":   ("80",  "% de cuota para aviso"),
    "alert.quota_exceeded_pct":  ("100", "% de cuota para alerta de exceso"),
    "alert.repeated_errors_n":   ("5",   "Nº de errores para alerta de repetición"),
    "alert.repeated_errors_hrs": ("24",  "Ventana de horas para errores repetidos"),
    "alert.sync_max_hours":      ("24",  "Horas sin sync antes de alertar"),
}


class AppSetting(db.Model):
    __tablename__ = "app_settings"

    key         = db.Column(db.String(64),  primary_key=True)
    value       = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    updated_at  = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
    )
    updated_by = db.Column(db.String(64), nullable=True)

    # ── Typed accessors ───────────────────────────────────────────────────────

    def as_int(self, default: int = 0) -> int:
        try:
            return int(self.value)
        except (ValueError, TypeError):
            return default

    def as_float(self, default: float = 0.0) -> float:
        try:
            return float(self.value)
        except (ValueError, TypeError):
            return default

    def __repr__(self) -> str:
        return f"<AppSetting {self.key}={self.value!r}>"


def seed_defaults(actor: str = "system") -> None:
    """Create default AppSetting rows if they don't exist yet (idempotent)."""
    now = datetime.now(timezone.utc)
    for key, (value, description) in DEFAULT_THRESHOLDS.items():
        if db.session.get(AppSetting, key) is None:
            db.session.add(AppSetting(
                key=key, value=value,
                description=description,
                updated_at=now, updated_by=actor,
            ))
    db.session.commit()
