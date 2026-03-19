"""
ProjectMember model — relationship between OverleafUser and OverleafProject.

In Overleaf CE, projects have:
    collaberator_refs  -> users with read-write access
    readOnly_refs      -> users with read-only access
These are arrays of user ObjectIds in the projects collection.
"""
from datetime import datetime, timezone

from app.extensions import db


class ProjectMember(db.Model):
    __tablename__ = "project_members"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("overleaf_projects.id"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("overleaf_users.id"), nullable=False, index=True
    )
    # "collaborator" | "read_only" | "owner"
    role = db.Column(db.String(32), nullable=False, default="collaborator")
    synced_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    project = db.relationship("OverleafProject", back_populates="members")
    user = db.relationship("OverleafUser", back_populates="memberships")

    __table_args__ = (
        db.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
