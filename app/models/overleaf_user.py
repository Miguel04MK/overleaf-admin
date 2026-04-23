"""
OverleafUser model — represents a user synchronized from Overleaf CE.

Field mapping from MongoDB (sharelatex.users collection):
    _id          -> overleaf_id  (stored as string, was ObjectId)
    email        -> email
    first_name   -> first_name
    last_name    -> last_name
    isAdmin      -> is_admin
    signUpDate   -> signup_date
    lastLoggedIn -> last_login_at

NOTE: Field names may vary across Overleaf CE versions.
All extraction logic is encapsulated in app/sync/extractor.py.
"""
from datetime import datetime, timezone

from app.extensions import db

# Quota status thresholds
QUOTA_WARNING_PCT = 80   # amber warning
QUOTA_DANGER_PCT  = 95   # red danger


def _fmt_bytes(n) -> str:
    """Return a human-readable size string (e.g. '4.2 MB')."""
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


class OverleafUser(db.Model):
    __tablename__ = "overleaf_users"

    # Internal platform ID
    id = db.Column(db.Integer, primary_key=True)

    # Overleaf MongoDB ObjectId (as string), unique key for upsert
    overleaf_id = db.Column(db.String(64), unique=True, nullable=False, index=True)

    email = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(255), nullable=True)
    last_name = db.Column(db.String(255), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Dates from Overleaf (may be None if not available in that version)
    signup_date = db.Column(db.DateTime(timezone=True), nullable=True)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Storage quota assigned by the platform admin (NULL = unlimited)
    max_quota_bytes = db.Column(db.BigInteger, nullable=True)

    # Sync metadata
    synced_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    projects_owned = db.relationship(
        "OverleafProject",
        back_populates="owner",
        foreign_keys="OverleafProject.owner_id",
        lazy="dynamic",
    )
    memberships = db.relationship(
        "ProjectMember", back_populates="user", lazy="dynamic"
    )

    # ------------------------------------------------------------------
    # Computed quota properties (no extra DB columns needed beyond max_quota_bytes)
    # NOTE: size_bytes in projects only counts binary file attachments.
    # .tex source files are stored in git history and are not reflected here.
    # ------------------------------------------------------------------

    @property
    def quota_used_bytes(self) -> int:
        """Sum of size_bytes of all projects owned by this user."""
        return sum(p.size_bytes or 0 for p in self.projects_owned)

    @property
    def quota_used_fmt(self) -> str:
        return _fmt_bytes(self.quota_used_bytes)

    @property
    def quota_max_fmt(self) -> str:
        return _fmt_bytes(self.max_quota_bytes) if self.max_quota_bytes else "Sin limite"

    @property
    def quota_percent(self):
        """Usage percentage (0-100+). None if no quota is set."""
        if not self.max_quota_bytes:
            return None
        return round((self.quota_used_bytes / self.max_quota_bytes) * 100, 1)

    @property
    def quota_status(self) -> str:
        """Bootstrap colour keyword: 'success', 'warning', or 'danger'."""
        pct = self.quota_percent
        if pct is None:
            return "secondary"
        if pct >= QUOTA_DANGER_PCT:
            return "danger"
        if pct >= QUOTA_WARNING_PCT:
            return "warning"
        return "success"

    @property
    def quota_exceeded(self) -> bool:
        pct = self.quota_percent
        return pct is not None and pct >= 100

    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        parts = [self.first_name, self.last_name]
        name = " ".join(p for p in parts if p)
        return name or self.email or self.overleaf_id

    def __repr__(self) -> str:
        return f"<OverleafUser {self.email or self.overleaf_id}>"
