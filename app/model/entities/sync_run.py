"""
SyncRun entity — records each synchronization execution.
"""
from datetime import datetime, timezone

from app.config.extensions import db


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

    users_found = db.Column(db.Integer, default=0)
    users_synced = db.Column(db.Integer, default=0)
    projects_found = db.Column(db.Integer, default=0)
    projects_synced = db.Column(db.Integer, default=0)

    users_delta = db.Column(db.Integer, nullable=True)
    projects_delta = db.Column(db.Integer, nullable=True)

    # "manual" | "scheduled"
    triggered_by = db.Column(db.String(32), nullable=False, default="manual")

    message = db.Column(db.Text, nullable=True)

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def mark_finished(self, status: str, message: str | None = None) -> None:
        self.finished_at = datetime.now(timezone.utc)
        self.status = status
        self.message = message

    def __repr__(self) -> str:
        return f"<SyncRun #{self.id} {self.status} at {self.started_at}>"
