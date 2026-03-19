"""
DashboardService — aggregate metrics for the main dashboard.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

from app.models.overleaf_user import OverleafUser
from app.models.overleaf_project import OverleafProject
from app.models.sync_run import SyncRun

logger = logging.getLogger(__name__)


@dataclass
class DashboardStats:
    total_users: int = 0
    total_projects: int = 0
    last_sync: datetime | None = None
    last_sync_status: str = "never"
    recent_syncs: list = field(default_factory=list)


def get_stats() -> DashboardStats:
    """Collect summary statistics for the dashboard."""
    stats = DashboardStats()
    try:
        stats.total_users = OverleafUser.query.count()
        stats.total_projects = OverleafProject.query.count()
        last_run = SyncRun.query.order_by(SyncRun.started_at.desc()).first()
        if last_run:
            stats.last_sync = last_run.finished_at or last_run.started_at
            stats.last_sync_status = last_run.status
        stats.recent_syncs = (
            SyncRun.query.order_by(SyncRun.started_at.desc()).limit(5).all()
        )
    except Exception as exc:
        logger.error("Error collecting dashboard stats: %s", exc)
    return stats
