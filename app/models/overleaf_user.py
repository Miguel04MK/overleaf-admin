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

    @property
    def display_name(self) -> str:
        parts = [self.first_name, self.last_name]
        name = " ".join(p for p in parts if p)
        return name or self.email or self.overleaf_id

    def __repr__(self) -> str:
        return f"<OverleafUser {self.email or self.overleaf_id}>"
