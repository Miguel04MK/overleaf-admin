"""
Role entity — administrative roles for Overleaf platform users.

Roles are platform-managed (not synced from Overleaf).
Each role carries default quota limits that are applied when a role is assigned.
"""
from datetime import datetime, timezone

from app.config.extensions import db

# ── Quota presets used when seeding default roles ─────────────────────────────
MB = 1024 ** 2
GB = 1024 ** 3

ROLE_PRESETS = {
    "alumno": {
        "description": "Estudiante con acceso estándar a la plataforma.",
        "storage_quota_bytes": 500 * MB,   # 500 MB
        "max_projects": 20,
        "is_default": True,
        "color": "primary",
    },
    "profesor": {
        "description": "Docente con mayor capacidad de almacenamiento.",
        "storage_quota_bytes": 5 * GB,     # 5 GB
        "max_projects": 50,
        "is_default": False,
        "color": "info",
    },
    "admin": {
        "description": "Administrador de la plataforma. Sin límites aplicados.",
        "storage_quota_bytes": None,       # unlimited
        "max_projects": None,              # unlimited
        "is_default": False,
        "color": "warning",
    },
}


class Role(db.Model):
    __tablename__ = "roles"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(64), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)

    # Quota settings (NULL = unlimited)
    storage_quota_bytes = db.Column(db.BigInteger, nullable=True)
    max_projects        = db.Column(db.Integer,    nullable=True)

    # Metadata
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    color      = db.Column(db.String(32), default="secondary", nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    users = db.relationship(
        "OverleafUser", back_populates="role", lazy="dynamic"
    )

    # ── Computed helpers ──────────────────────────────────────────────────────
    @property
    def storage_quota_fmt(self) -> str:
        n = self.storage_quota_bytes
        if n is None:
            return "Ilimitado"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(n) < 1024.0:
                return f"{n:.0f} {unit}"
            n /= 1024.0
        return f"{n:.1f} PB"

    @property
    def max_projects_fmt(self) -> str:
        return str(self.max_projects) if self.max_projects is not None else "Ilimitado"

    @property
    def user_count(self) -> int:
        return self.users.count()

    def __repr__(self) -> str:
        return f"<Role {self.name}>"
