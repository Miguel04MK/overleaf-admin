"""
service/index_stats.py
-----------------------
Lightweight stats for the reports index page and bundle data gatherer.
Also contains get_reports_overview (kept for backward compat with tests).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, desc

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun
from app.model.entities.report_export_log import ReportExportLog

from ._helpers import _fmt_bytes, _split_bytes, _trend
from .report_queries import (
    get_users_report_all, get_projects_report_all, get_storage_report,
    get_quotas_report_all, get_activity_report_all,
    get_incidents_report_all, get_syncs_report_all,
)
from .general_queries import get_general_report_data


def get_index_stats() -> dict[str, Any]:
    """Fast, lightweight stats for the index page — no heavy queries."""
    last_general_export = (
        ReportExportLog.query
        .filter(ReportExportLog.report_type == "general",
                ReportExportLog.status == "completed")
        .order_by(desc(ReportExportLog.generated_at))
        .first()
    )
    last_bundle_export = (
        ReportExportLog.query
        .filter(ReportExportLog.report_type == "todos",
                ReportExportLog.status == "completed")
        .order_by(desc(ReportExportLog.generated_at))
        .first()
    )
    return {
        "last_general_export": last_general_export,
        "last_bundle_export":  last_bundle_export,
    }


def get_all_reports_data() -> dict:
    """Gather data for every individual report in a single call."""
    storage = get_storage_report()
    return {
        "users":        get_users_report_all(),
        "projects":     get_projects_report_all(),
        "storage_rows": storage["rows"],
        "storage":      storage,
        "quotas":       get_quotas_report_all(),
        "activity":     get_activity_report_all(),
        "incidents":    get_incidents_report_all(),
        "syncs":        get_syncs_report_all(),
        "general":      get_general_report_data(),
    }


def get_reports_overview() -> dict[str, Any]:
    """Summary numbers shown on the reports index page (backward compat)."""
    now        = datetime.now(timezone.utc)
    this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month = (
        this_month.replace(year=this_month.year - 1, month=12)
        if this_month.month == 1
        else this_month.replace(month=this_month.month - 1)
    )

    total_users    = OverleafUser.query.count()
    total_projects = OverleafProject.query.count()
    total_bytes    = db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    total_syncs    = SyncRun.query.count()
    audit_errors   = AuditLog.query.filter(AuditLog.level == "error").count()
    audit_warnings = AuditLog.query.filter(AuditLog.level == "warning").count()
    exceeded_users = sum(
        1 for u in OverleafUser.query.filter(OverleafUser.max_quota_bytes != None).all()
        if u.quota_exceeded
    )
    last_sync = SyncRun.query.order_by(desc(SyncRun.started_at)).first()

    users_this = OverleafUser.query.filter(OverleafUser.signup_date >= this_month).count()
    users_last = OverleafUser.query.filter(
        OverleafUser.signup_date >= last_month,
        OverleafUser.signup_date < this_month,
    ).count()

    proj_this = OverleafProject.query.filter(OverleafProject.created_at >= this_month).count()
    proj_last = OverleafProject.query.filter(
        OverleafProject.created_at >= last_month,
        OverleafProject.created_at < this_month,
    ).count()

    size_this = float(
        db.session.query(func.sum(OverleafProject.size_bytes))
        .filter(OverleafProject.created_at >= this_month)
        .scalar() or 0
    )
    size_last = float(
        db.session.query(func.sum(OverleafProject.size_bytes))
        .filter(OverleafProject.created_at >= last_month,
                OverleafProject.created_at < this_month)
        .scalar() or 0
    )

    syncs_this  = SyncRun.query.filter(SyncRun.started_at >= this_month).count()
    syncs_last  = SyncRun.query.filter(
        SyncRun.started_at >= last_month,
        SyncRun.started_at < this_month,
    ).count()

    errors_this = AuditLog.query.filter(
        AuditLog.level.in_(["error", "warning"]),
        AuditLog.created_at >= this_month,
    ).count()
    errors_last = AuditLog.query.filter(
        AuditLog.level.in_(["error", "warning"]),
        AuditLog.created_at >= last_month,
        AuditLog.created_at < this_month,
    ).count()

    storage_val, storage_unit = _split_bytes(total_bytes)

    return {
        "total_users":    total_users,
        "total_projects": total_projects,
        "total_bytes":    float(total_bytes),
        "total_bytes_fmt":_fmt_bytes(total_bytes),
        "storage_val":    storage_val,
        "storage_unit":   storage_unit,
        "total_syncs":    total_syncs,
        "audit_errors":   audit_errors,
        "audit_warnings": audit_warnings,
        "alerts_total":   audit_errors + audit_warnings,
        "exceeded_users": exceeded_users,
        "last_sync":      last_sync,
        "trends": {
            "users":    _trend(users_this, users_last),
            "projects": _trend(proj_this, proj_last),
            "storage":  _trend(int(size_this), int(size_last)),
            "syncs":    _trend(syncs_this, syncs_last),
            "alerts":   _trend(errors_this, errors_last),
        },
    }
