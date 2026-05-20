"""SyncService — thin wrapper around the ETL runner + sync history queries."""
from app.etl.runners.runner import run_sync  # noqa: F401
from app.model.entities import sync_run_dao


def get_recent_syncs(limit: int = 20):
    """Return the most recent sync runs ordered by start time descending."""
    return sync_run_dao.get_recent_runs(limit=limit)
