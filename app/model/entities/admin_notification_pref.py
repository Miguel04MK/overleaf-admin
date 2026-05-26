"""
AdminNotificationPref entity — per-admin email notification preferences.

Cada AdminUser tiene como mucho una fila. Por cada tipo de alerta hay DOS
columnas independientes:

  - notify_X (bool): el tipo dispara un email inmediato cuando se genera.
  - notify_X_digest_only (bool): el tipo se incluye en el resumen periódico.

Un tipo puede estar activo en ambos modos a la vez (inmediato Y resumen).

Además, `digest_frequency` decide cada cuánto se envía el resumen
('disabled' / 'daily' / 'weekly').

Cuando no existe fila, notification_service usa defaults conservadores:
critical + danger + sync_failed + quota_exceeded + repeated_errors,
todos en modo "immediate".
"""
from app.config.extensions import db


# Frecuencias soportadas por el resumen periódico
DIGEST_FREQUENCY_CHOICES: list[str] = [
    "disabled",
    "12h",
    "daily",
    "3days",
    "5days",
    "weekly",
    "2weeks",
    "monthly",
]

# Etiquetas legibles para cada frecuencia
DIGEST_FREQUENCY_LABELS: dict[str, str] = {
    "disabled": "Desactivado",
    "12h":      "Cada 12 horas",
    "daily":    "Cada día",
    "3days":    "Cada 3 días",
    "5days":    "Cada 5 días",
    "weekly":   "Cada semana",
    "2weeks":   "Cada 2 semanas",
    "monthly":  "Cada mes",
}

# Horas seleccionables (0-23)
DIGEST_HOUR_CHOICES: list[tuple[int, str]] = [
    (h, f"{h:02d}:00") for h in range(24)
]


class AdminNotificationPref(db.Model):
    __tablename__ = "admin_notification_prefs"

    id       = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(
        db.Integer, db.ForeignKey("admin_users.id"),
        nullable=False, unique=True, index=True,
    )

    # ── Frecuencia y hora del resumen ─────────────────────────────────────────
    digest_frequency = db.Column(db.String(16), nullable=False, default="disabled")
    digest_hour      = db.Column(db.Integer,    nullable=True)   # 0-23, None = sin hora fija

    # ── By level ─────────────────────────────────────────────────────────────
    # notify_X        = True  → enviar email inmediato al generarse la alerta
    # notify_X_digest_only = True  → incluir en el resumen periódico
    # (Ambos pueden ser True al mismo tiempo)
    notify_critical              = db.Column(db.Boolean, default=True,  nullable=False)
    notify_critical_digest_only  = db.Column(db.Boolean, default=False, nullable=False)
    notify_danger                = db.Column(db.Boolean, default=True,  nullable=False)
    notify_danger_digest_only    = db.Column(db.Boolean, default=False, nullable=False)
    notify_warning               = db.Column(db.Boolean, default=False, nullable=False)
    notify_warning_digest_only   = db.Column(db.Boolean, default=False, nullable=False)
    notify_info                  = db.Column(db.Boolean, default=False, nullable=False)
    notify_info_digest_only      = db.Column(db.Boolean, default=False, nullable=False)

    # ── By type ───────────────────────────────────────────────────────────────
    # (notify_service_down se eliminó intencionadamente — no está soportado.)
    notify_sync_failed                        = db.Column(db.Boolean, default=True,  nullable=False)
    notify_sync_failed_digest_only            = db.Column(db.Boolean, default=False, nullable=False)
    notify_quota_exceeded                     = db.Column(db.Boolean, default=True,  nullable=False)
    notify_quota_exceeded_digest_only         = db.Column(db.Boolean, default=False, nullable=False)
    notify_quota_warning                      = db.Column(db.Boolean, default=False, nullable=False)
    notify_quota_warning_digest_only          = db.Column(db.Boolean, default=False, nullable=False)
    notify_project_limit_exceeded             = db.Column(db.Boolean, default=False, nullable=False)
    notify_project_limit_exceeded_digest_only = db.Column(db.Boolean, default=False, nullable=False)
    notify_project_limit_warning              = db.Column(db.Boolean, default=False, nullable=False)
    notify_project_limit_warning_digest_only  = db.Column(db.Boolean, default=False, nullable=False)
    notify_repeated_errors                    = db.Column(db.Boolean, default=True,  nullable=False)
    notify_repeated_errors_digest_only        = db.Column(db.Boolean, default=False, nullable=False)
    notify_administrative_warning             = db.Column(db.Boolean, default=False, nullable=False)
    notify_administrative_warning_digest_only = db.Column(db.Boolean, default=False, nullable=False)

    # ── Relationship ─────────────────────────────────────────────────────────
    admin = db.relationship(
        "AdminUser",
        backref=db.backref("notification_pref", uselist=False, lazy="select"),
    )

    # ── Listas auxiliares ────────────────────────────────────────────────────

    NOTIFY_KEYS: list[str] = [
        "notify_critical", "notify_danger", "notify_warning", "notify_info",
        "notify_sync_failed", "notify_quota_exceeded", "notify_quota_warning",
        "notify_project_limit_exceeded", "notify_project_limit_warning",
        "notify_repeated_errors", "notify_administrative_warning",
    ]

    BOOLEAN_FIELDS: list[str] = (
        NOTIFY_KEYS
        + [k + "_digest_only" for k in NOTIFY_KEYS]
    )

    # ── Helpers de lectura ────────────────────────────────────────────────────

    def is_immediate(self, key: str) -> bool:
        """True si el tipo activa un email inmediato (pestaña Inmediato)."""
        if key not in self.NOTIFY_KEYS:
            return False
        return bool(getattr(self, key, False))

    def is_in_digest(self, key: str) -> bool:
        """True si el tipo se incluye en el resumen periódico (pestaña Periódico)."""
        if key not in self.NOTIFY_KEYS:
            return False
        return bool(getattr(self, key + "_digest_only", False))

    # ── Compat helpers (mantener para código existente) ───────────────────────

    def get_mode(self, key: str) -> str:
        """Compat: 'off' | 'immediate' | 'digest'.
        Si está en ambas pestañas, devuelve 'immediate' (prioridad).
        """
        if key not in self.NOTIFY_KEYS:
            return "off"
        if self.is_immediate(key):
            return "immediate"
        if self.is_in_digest(key):
            return "digest"
        return "off"

    def set_mode(self, key: str, mode: str) -> None:
        """Compat: setea modo exclusivo (no usa las dos pestañas a la vez)."""
        if key not in self.NOTIFY_KEYS:
            return
        if mode == "immediate":
            setattr(self, key,                  True)
            setattr(self, key + "_digest_only", False)
        elif mode == "digest":
            setattr(self, key,                  False)
            setattr(self, key + "_digest_only", True)
        else:
            setattr(self, key,                  False)
            setattr(self, key + "_digest_only", False)

    # ── Serialización ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialización para los endpoints JSON.

        Estructura (nuevo formato de dos pestañas):
            {
              "digest_frequency": str,
              "digest_hour": int | None,
              "immediate": { "notify_critical": true, ... },
              "digest":    { "notify_critical": false, ... }
            }
        """
        return {
            "digest_frequency": self.digest_frequency,
            "digest_hour":      self.digest_hour,
            "immediate": {k: self.is_immediate(k) for k in self.NOTIFY_KEYS},
            "digest":    {k: self.is_in_digest(k) for k in self.NOTIFY_KEYS},
        }

    def update_from_dict(self, data: dict) -> None:
        """Acepta el formato de dos pestañas y formatos anteriores por compatibilidad.

        Formatos soportados (en orden de prioridad):
          1. Nuevo: { immediate: {k:bool}, digest: {k:bool}, digest_frequency }
          2. Anterior 3-estado: { modes: {k: "off"|"immediate"|"digest"}, digest_frequency }
          3. Antiguo plano: { notify_X: bool, ... }
        """
        if "immediate" in data and isinstance(data.get("immediate"), dict):
            # Formato nuevo — pestaña Inmediato
            for k, val in data["immediate"].items():
                if k in self.NOTIFY_KEYS:
                    setattr(self, k, bool(val))
            # Formato nuevo — pestaña Periódico
            if "digest" in data and isinstance(data.get("digest"), dict):
                for k, val in data["digest"].items():
                    if k in self.NOTIFY_KEYS:
                        setattr(self, k + "_digest_only", bool(val))

        elif "modes" in data and isinstance(data.get("modes"), dict):
            # Formato anterior 3-estado (un solo radio por tipo)
            for k, mode in data["modes"].items():
                if k in self.NOTIFY_KEYS:
                    self.set_mode(k, mode)

        else:
            # Formato más antiguo — booleans planos por clave
            for k in self.NOTIFY_KEYS:
                if k in data:
                    setattr(self, k, bool(data[k]))
            for k in self.NOTIFY_KEYS:
                dk = k + "_digest_only"
                if dk in data and getattr(self, k, False):
                    setattr(self, dk, bool(data[dk]))

        if "digest_frequency" in data:
            freq = data["digest_frequency"]
            if freq in DIGEST_FREQUENCY_CHOICES:
                self.digest_frequency = freq

        if "digest_hour" in data:
            h = data["digest_hour"]
            if h is None:
                self.digest_hour = None
            else:
                try:
                    h = int(h)
                    if 0 <= h <= 23:
                        self.digest_hour = h
                except (TypeError, ValueError):
                    pass

    def __repr__(self) -> str:
        return f"<AdminNotificationPref admin_id={self.admin_id}>"
