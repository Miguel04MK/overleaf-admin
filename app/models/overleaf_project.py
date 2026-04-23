"""
OverleafProject model — represents a project synchronized from Overleaf CE.

Field mapping from MongoDB (sharelatex.projects collection):
    _id          -> overleaf_id  (stored as string)
    name         -> name
    owner_ref    -> owner.overleaf_id  (foreign key resolved at transform time)
    created      -> created_at   (field name may vary by version: 'created' or 'date')
    lastUpdated  -> last_updated_at

NOTE: The 'owner_ref' in MongoDB is an ObjectId reference to users._id.
      This is resolved during the ETL transformation step.
      See app/sync/transformer.py for version-specific field handling.
"""
from datetime import datetime, timezone

from app.extensions import db


class OverleafProject(db.Model):
    __tablename__ = "overleaf_projects"

    # Internal platform ID
    id = db.Column(db.Integer, primary_key=True)

    # Overleaf MongoDB ObjectId (as string)
    overleaf_id = db.Column(db.String(64), unique=True, nullable=False, index=True)

    name = db.Column(db.String(512), nullable=True)

    # Owner: foreign key to OverleafUser.id (our internal ID)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("overleaf_users.id"), nullable=True, index=True
    )
    # Also store the raw overleaf owner ref for resilience
    owner_overleaf_id = db.Column(db.String(64), nullable=True)

    # Dates from Overleaf
    created_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_updated_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # File stats extracted from rootFolder (counts docs + fileRefs recursively)
    file_count = db.Column(db.Integer, nullable=True)
    # Sum of binary file sizes from rootFolder.fileRefs[].size (bytes)
    size_bytes = db.Column(db.BigInteger, nullable=True)

    # Sync metadata
    synced_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    owner = db.relationship(
        "OverleafUser",
        back_populates="projects_owned",
        foreign_keys=[owner_id],
    )
    members = db.relationship(
        "ProjectMember", back_populates="project", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<OverleafProject {self.name or self.overleaf_id}>"
