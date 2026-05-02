"""
SyncRunDao — queries sobre SyncRun.
"""
from app.model.entities.sync_run import SyncRun


def get_recent_runs(limit: int = 20):
    return SyncRun.query.order_by(SyncRun.started_at.desc()).limit(limit).all()


def get_runs_page(page: int, per_page: int = 20):
    return SyncRun.query.order_by(SyncRun.started_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
