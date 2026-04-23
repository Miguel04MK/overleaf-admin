"""
SyncRun model — records each synchronization execution.
"""
from datetime import datetime, timezone

from app.extensions import db


class SyncRun(db.Model):
    __tablename__ = "sync_runs"

    id = db.Column(db.Integer, primary_key=True)

    # When the sync started and ended
    started_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # "running" | "success" | "partial" | "error"
    status = db.Column(db.String(32), nullable=False, default="running")

    # Counts
    users_found = db.Column(db.Integer, default=0)
    users_synced = db.Column(db.Integer, default=0)
    projects_found = db.Column(db.Integer, default=0)
    projects_synced = db.Column(db.Integer, default=0)

    # Net change vs previous state (post-sync count - pre-sync count).
    # Positive => new rows, negative => rows disappeared, 0 => no change.
    users_delta = db.Column(db.Integer, nullable=True)
    projects_delta = db.Column(db.Integer, nullable=True)

    # "manual" | "scheduled"
    triggered_by = db.Column(db.String(32), nullable=False, default="manual")

    # Error or info message
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
