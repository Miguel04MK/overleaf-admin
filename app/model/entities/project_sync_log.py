"""
ProjectSyncLog — per-project sync history.

Each time the ETL loader touches a project (create or update) it writes
one row here, linked to the global SyncRun and the OverleafProject.

event values:
    "created"  — first time this project was seen
    "updated"  — project already existed; fields re-upserted
"""
from datetime import datetime, timezone

from app.config.extensions import db


class ProjectSyncLog(db.Model):
    __tablename__ = "project_sync_logs"

    id = db.Column(db.Integer, primary_key=True)

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("overleaf_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sync_run_id = db.Column(
        db.Integer,
        db.ForeignKey("sync_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    synced_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # "created" | "updated"
    event = db.Column(db.String(16), nullable=False, default="updated")

    # Snapshot at sync time
    size_bytes = db.Column(db.BigInteger, nullable=True)
    member_count = db.Column(db.Integer, nullable=True)

    project  = db.relationship("OverleafProject", back_populates="sync_logs")
    sync_run = db.relationship("SyncRun")

    def __repr__(self) -> str:
        return f"<ProjectSyncLog project={self.project_id} event={self.event} at={self.synced_at}>"
