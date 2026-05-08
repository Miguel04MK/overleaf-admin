"""
app/modules/reports/service.py
-------------------------------
Query functions for all report types.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from flask import current_app
from flask_login import current_user
from sqlalchemy import func, desc, asc, text

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.project_member import ProjectMember
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun
from app.model.entities.role import Role
from app.model.entities.role_change_log import RoleChangeLog
from app.model.entities.report_export_log import ReportExportLog
from app.model.entities.admin_user import AdminUser

log = logging.getLogger(__name__)

# ─── constants ───────────────────────────────────────────────────────────────

_INACTIVE_DAYS = 90
_LARGE_BYTES = 10 * 1024 * 1024  # 10 MB


# ─── helpers ─────────────────────────────────────────────────────────────────

def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return None


def _fmt_bytes(n) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _split_bytes(n) -> tuple[str, str]:
    """Split a byte count into (number_string, unit) for separate display."""
    if n is None or n == 0:
        return ("0", "B")
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return (f"{n:.1f}", unit)
        n /= 1024.0
    return (f"{n:.1f}", "PB")


def _trend(current: int, previous: int) -> int:
    """Percentage change from previous to current."""
    if previous == 0:
        return 0 if current == 0 else 100
    return round(((current - previous) / previous) * 100)


def _actor_name() -> str:
    """Current admin username or 'system'."""
    if current_user and current_user.is_authenticated:
        return current_user.username
    return "system"


# ─── Export logging ──────────────────────────────────────────────────────────

def log_report_export(
    report_type: str,
    fmt: str,
    file_name: str,
    filters: dict | None = None,
    status: str = "completed",
    error_message: str | None = None,
) -> ReportExportLog:
    """Record an export in ReportExportLog and AuditLog."""
    entry = ReportExportLog(
        report_type=report_type,
        format=fmt,
        generated_by=_actor_name(),
        file_name=file_name,
        filters_json=json.dumps(filters, default=str) if filters else None,
        status=status,
        error_message=error_message,
    )
    db.session.add(entry)

    # Also write to AuditLog for backward compat
    audit = AuditLog(
        actor=_actor_name(),
        action="export",
        detail=f"{report_type}|{file_name}",
        level="info" if status == "completed" else "warning",
    )
    db.session.add(audit)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return entry


def get_export_history(
    *,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    """Paginated export history from ReportExportLog."""
    q = ReportExportLog.query.order_by(desc(ReportExportLog.generated_at))
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "pagination": pagination,
        "items": pagination.items,
    }


def get_recent_exports(limit: int = 5) -> list[dict[str, Any]]:
    """Fetch the most recent exports for the index sidebar."""
    entries = (
        ReportExportLog.query
        .filter(ReportExportLog.status == "completed")
        .order_by(desc(ReportExportLog.generated_at))
        .limit(limit)
        .all()
    )
    results = []
    for e in entries:
        results.append({
            "actor": e.generated_by,
            "report_type": e.report_type,
            "format": e.format,
            "filename": e.file_name or "",
            "date": e.generated_at,
            "status": e.status,
        })
    return results


# ─── Users report ────────────────────────────────────────────────────────────

def get_users_report(
    *,
    search: str | None = None,
    role_id: int | None = None,
    is_admin: bool | None = None,
    quota_filter: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "email",
    order: str = "asc",
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Paginated, filterable users report."""
    q = OverleafUser.query

    if search:
        like = f"%{search}%"
        q = q.filter(
            db.or_(
                OverleafUser.email.ilike(like),
                OverleafUser.first_name.ilike(like),
                OverleafUser.last_name.ilike(like),
            )
        )

    if role_id is not None:
        q = q.filter(OverleafUser.role_id == role_id)

    if is_admin is not None:
        q = q.filter(OverleafUser.is_admin == is_admin)

    if date_from:
        q = q.filter(OverleafUser.signup_date >= date_from)
    if date_to:
        q = q.filter(OverleafUser.signup_date <= date_to)

    col_map = {
        "email": OverleafUser.email,
        "first_name": OverleafUser.first_name,
        "last_name": OverleafUser.last_name,
        "signup_date": OverleafUser.signup_date,
        "last_login_at": OverleafUser.last_login_at,
        "max_quota_bytes": OverleafUser.max_quota_bytes,
    }
    sort_col = col_map.get(sort, OverleafUser.email)
    q = q.order_by(asc(sort_col) if order == "asc" else desc(sort_col))

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items

    if quota_filter:
        def _keep(u: OverleafUser) -> bool:
            pct = u.quota_percent
            if quota_filter == "exceeded":
                return pct is not None and pct >= 100
            if quota_filter == "warning":
                return pct is not None and 80 <= pct < 100
            if quota_filter == "ok":
                return pct is not None and pct < 80
            if quota_filter == "unlimited":
                return u.max_quota_bytes is None
            return True
        items = [u for u in items if _keep(u)]

    # Summary stats
    all_users = OverleafUser.query.all()
    total = len(all_users)
    admins = sum(1 for u in all_users if u.is_admin)
    exceeded = sum(1 for u in all_users if u.quota_exceeded)
    unlimited = sum(1 for u in all_users if u.max_quota_bytes is None)

    return {
        "pagination": pagination,
        "items": items,
        "stats": {
            "total": total,
            "admins": admins,
            "exceeded": exceeded,
            "unlimited": unlimited,
        },
        "roles": Role.query.order_by(Role.name).all(),
    }


def get_users_report_all(
    *,
    search: str | None = None,
    role_id: int | None = None,
    is_admin: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[OverleafUser]:
    """Return ALL matching users (for CSV/PDF export)."""
    q = OverleafUser.query
    if search:
        like = f"%{search}%"
        q = q.filter(
            db.or_(
                OverleafUser.email.ilike(like),
                OverleafUser.first_name.ilike(like),
                OverleafUser.last_name.ilike(like),
            )
        )
    if role_id is not None:
        q = q.filter(OverleafUser.role_id == role_id)
    if is_admin is not None:
        q = q.filter(OverleafUser.is_admin == is_admin)
    if date_from:
        q = q.filter(OverleafUser.signup_date >= date_from)
    if date_to:
        q = q.filter(OverleafUser.signup_date <= date_to)
    return q.order_by(OverleafUser.email).all()


# ─── Projects report ─────────────────────────────────────────────────────────

def get_projects_report(
    *,
    search: str | None = None,
    owner_id: int | None = None,
    size_filter: str | None = None,
    activity_filter: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "name",
    order: str = "asc",
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Paginated, filterable projects report."""
    q = OverleafProject.query

    if search:
        q = q.filter(OverleafProject.name.ilike(f"%{search}%"))
    if owner_id:
        q = q.filter(OverleafProject.owner_id == owner_id)
    if size_filter == "large":
        q = q.filter(OverleafProject.size_bytes >= _LARGE_BYTES)
    elif size_filter == "empty":
        q = q.filter(
            db.or_(OverleafProject.size_bytes == 0, OverleafProject.size_bytes == None)
        )

    cutoff_inactive = datetime.now(timezone.utc) - timedelta(days=_INACTIVE_DAYS)
    if activity_filter == "inactive":
        q = q.filter(
            db.or_(
                OverleafProject.last_updated_at < cutoff_inactive,
                OverleafProject.last_updated_at == None,
            )
        )
    elif activity_filter == "recent":
        thirty_days = datetime.now(timezone.utc) - timedelta(days=30)
        q = q.filter(OverleafProject.last_updated_at >= thirty_days)

    if date_from:
        q = q.filter(OverleafProject.last_updated_at >= date_from)
    if date_to:
        q = q.filter(OverleafProject.last_updated_at <= date_to)

    col_map = {
        "name": OverleafProject.name,
        "size_bytes": OverleafProject.size_bytes,
        "last_updated_at": OverleafProject.last_updated_at,
        "created_at": OverleafProject.created_at,
    }
    sort_col = col_map.get(sort, OverleafProject.name)
    q = q.order_by(asc(sort_col) if order == "asc" else desc(sort_col))

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    project_ids = [p.id for p in pagination.items]
    member_counts: dict[int, int] = {}
    if project_ids:
        rows = (
            db.session.query(ProjectMember.project_id, func.count(ProjectMember.id))
            .filter(ProjectMember.project_id.in_(project_ids))
            .group_by(ProjectMember.project_id)
            .all()
        )
        member_counts = {pid: cnt for pid, cnt in rows}

    total_projects = OverleafProject.query.count()
    large_count = OverleafProject.query.filter(
        OverleafProject.size_bytes >= _LARGE_BYTES
    ).count()
    inactive_count = OverleafProject.query.filter(
        db.or_(
            OverleafProject.last_updated_at < cutoff_inactive,
            OverleafProject.last_updated_at == None,
        )
    ).count()
    total_size = db.session.query(
        func.sum(OverleafProject.size_bytes)
    ).scalar() or 0

    owner_id_rows = (
        db.session.query(OverleafProject.owner_id)
        .filter(OverleafProject.owner_id != None)
        .distinct()
        .all()
    )
    owner_id_list = [r[0] for r in owner_id_rows]
    owners = (
        OverleafUser.query
        .filter(OverleafUser.id.in_(owner_id_list))
        .order_by(OverleafUser.email)
        .all()
    ) if owner_id_list else []

    return {
        "pagination": pagination,
        "member_counts": member_counts,
        "owners": owners,
        "stats": {
            "total": total_projects,
            "large": large_count,
            "inactive": inactive_count,
            "total_size_fmt": _fmt_bytes(total_size),
        },
    }


def get_projects_report_all(
    *,
    search: str | None = None,
    owner_id: int | None = None,
    size_filter: str | None = None,
    activity_filter: str | None = None,
) -> list[OverleafProject]:
    """Return ALL matching projects (for CSV/PDF export)."""
    q = OverleafProject.query
    if search:
        q = q.filter(OverleafProject.name.ilike(f"%{search}%"))
    if owner_id:
        q = q.filter(OverleafProject.owner_id == owner_id)
    if size_filter == "large":
        q = q.filter(OverleafProject.size_bytes >= _LARGE_BYTES)
    elif size_filter == "empty":
        q = q.filter(
            db.or_(OverleafProject.size_bytes == 0, OverleafProject.size_bytes == None)
        )
    cutoff = datetime.now(timezone.utc) - timedelta(days=_INACTIVE_DAYS)
    if activity_filter == "inactive":
        q = q.filter(
            db.or_(
                OverleafProject.last_updated_at < cutoff,
                OverleafProject.last_updated_at == None,
            )
        )
    elif activity_filter == "recent":
        thirty = datetime.now(timezone.utc) - timedelta(days=30)
        q = q.filter(OverleafProject.last_updated_at >= thirty)
    return q.order_by(OverleafProject.name).all()


# ─── Storage report ──────────────────────────────────────────────────────────

def get_storage_report() -> dict[str, Any]:
    """Aggregate storage stats per user + global totals."""
    total_bytes = db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    total_projects = OverleafProject.query.count()
    total_users = OverleafUser.query.count()

    project_sizes = (
        db.session.query(
            OverleafProject.owner_id,
            func.sum(OverleafProject.size_bytes).label("used"),
            func.count(OverleafProject.id).label("proj_count"),
        )
        .filter(OverleafProject.owner_id != None)
        .group_by(OverleafProject.owner_id)
        .order_by(desc("used"))
        .all()
    )

    user_ids = [row.owner_id for row in project_sizes]
    users_by_id: dict[int, OverleafUser] = {}
    if user_ids:
        for u in OverleafUser.query.filter(OverleafUser.id.in_(user_ids)).all():
            users_by_id[u.id] = u

    rows = []
    for row in project_sizes:
        u = users_by_id.get(row.owner_id)
        if not u:
            continue
        used = row.used or 0
        quota = u.max_quota_bytes
        pct = round((used / quota) * 100, 1) if quota else None
        rows.append({
            "user": u,
            "used_bytes": used,
            "used_fmt": _fmt_bytes(used),
            "quota_fmt": _fmt_bytes(quota) if quota else "Sin limite",
            "quota_pct": pct,
            "proj_count": row.proj_count,
        })

    avg_per_user = float(total_bytes) / total_users if total_users else 0
    avg_per_project = float(total_bytes) / total_projects if total_projects else 0

    return {
        "total_bytes": total_bytes,
        "total_bytes_fmt": _fmt_bytes(total_bytes),
        "total_projects": total_projects,
        "total_users": total_users,
        "avg_per_user_fmt": _fmt_bytes(avg_per_user),
        "avg_per_project_fmt": _fmt_bytes(avg_per_project),
        "rows": rows,
    }


# ─── Activity / audit report ─────────────────────────────────────────────────

def get_activity_report(
    *,
    search: str | None = None,
    level: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Paginated audit log entries."""
    q = AuditLog.query.order_by(desc(AuditLog.created_at))

    if search:
        like = f"%{search}%"
        q = q.filter(
            db.or_(
                AuditLog.actor.ilike(like),
                AuditLog.action.ilike(like),
                AuditLog.detail.ilike(like),
            )
        )
    if level:
        q = q.filter(AuditLog.level == level)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor == actor)
    if date_from:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.created_at <= date_to)

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    total = AuditLog.query.count()
    errors = AuditLog.query.filter(AuditLog.level == "error").count()
    warnings = AuditLog.query.filter(AuditLog.level == "warning").count()

    action_names = [
        r[0] for r in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    ]
    actor_names = [
        r[0] for r in db.session.query(AuditLog.actor).distinct().order_by(AuditLog.actor).all()
    ]

    return {
        "pagination": pagination,
        "stats": {"total": total, "errors": errors, "warnings": warnings},
        "action_names": action_names,
        "actor_names": actor_names,
    }


def get_activity_report_all(
    *,
    level: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[AuditLog]:
    q = AuditLog.query.order_by(desc(AuditLog.created_at))
    if level:
        q = q.filter(AuditLog.level == level)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor == actor)
    if date_from:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.created_at <= date_to)
    return q.all()


# ─── Sync runs report ────────────────────────────────────────────────────────

def get_syncs_report(
    *,
    status: str | None = None,
    triggered_by: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    per_page: int = 30,
) -> dict[str, Any]:
    """Paginated sync run history."""
    q = SyncRun.query.order_by(desc(SyncRun.started_at))

    if status:
        q = q.filter(SyncRun.status == status)
    if triggered_by:
        q = q.filter(SyncRun.triggered_by == triggered_by)
    if date_from:
        q = q.filter(SyncRun.started_at >= date_from)
    if date_to:
        q = q.filter(SyncRun.started_at <= date_to)

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    total = SyncRun.query.count()
    errors = SyncRun.query.filter(SyncRun.status == "error").count()
    success = SyncRun.query.filter(SyncRun.status == "success").count()

    finished_runs = (
        SyncRun.query
        .filter(SyncRun.finished_at != None, SyncRun.started_at != None)
        .all()
    )
    if finished_runs:
        durations = [
            (r.finished_at - r.started_at).total_seconds()
            for r in finished_runs
        ]
        avg_dur_s = round(sum(durations) / len(durations), 1)
    else:
        avg_dur_s = None

    return {
        "pagination": pagination,
        "stats": {
            "total": total,
            "success": success,
            "errors": errors,
            "avg_duration_s": avg_dur_s,
        },
    }


def get_syncs_report_all(
    *,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[SyncRun]:
    q = SyncRun.query.order_by(desc(SyncRun.started_at))
    if status:
        q = q.filter(SyncRun.status == status)
    if date_from:
        q = q.filter(SyncRun.started_at >= date_from)
    if date_to:
        q = q.filter(SyncRun.started_at <= date_to)
    return q.all()


# ─── Quotas report ───────────────────────────────────────────────────────────

def get_quotas_report(
    *,
    status_filter: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Quota-focused report: all users with quota info."""
    all_users = OverleafUser.query.order_by(OverleafUser.email).all()

    rows = []
    for u in all_users:
        pct = u.quota_percent
        if pct is None:
            st = "unlimited"
        elif pct >= 100:
            st = "exceeded"
        elif pct >= 80:
            st = "warning"
        else:
            st = "ok"

        if status_filter and st != status_filter:
            continue

        # Role-based project limits
        role = u.role
        max_proj = role.max_projects if role else None
        owned_count = u.projects_owned.count()
        collab_count = u.memberships.count()

        rows.append({
            "user": u,
            "used_bytes": u.quota_used_bytes,
            "used_fmt": u.quota_used_fmt,
            "quota_bytes": u.max_quota_bytes,
            "quota_fmt": u.quota_max_fmt,
            "pct": pct,
            "status": st,
            "projects_count": owned_count,
            "collab_count": collab_count,
            "role_name": role.name if role else "Sin rol",
            "max_projects": max_proj,
            "exceeds_project_limit": (
                max_proj is not None and owned_count > max_proj
            ),
        })

    total = len(rows)
    exceeded = sum(1 for r in rows if r["status"] == "exceeded") if not status_filter else None
    warning = sum(1 for r in rows if r["status"] == "warning") if not status_filter else None

    start = (page - 1) * per_page
    page_items = rows[start:start + per_page]
    total_pages = max(1, (total + per_page - 1) // per_page)

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "stats": {
            "total_users": len(all_users),
            "exceeded": exceeded if exceeded is not None else sum(1 for r in rows if r["status"] == "exceeded"),
            "warning": warning if warning is not None else sum(1 for r in rows if r["status"] == "warning"),
        },
    }


def get_quotas_report_all(
    *,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """All quota rows without pagination (for CSV/PDF export)."""
    data = get_quotas_report(status_filter=status_filter, page=1, per_page=999999)
    return data["items"]


# ─── Incidents report ─────────────────────────────────────────────────────────

def get_incidents_report(
    *,
    level: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Incidents based on AuditLog entries with warning/error levels."""
    q = AuditLog.query.filter(
        AuditLog.level.in_(["warning", "error", "danger"])
    ).order_by(desc(AuditLog.created_at))

    if level:
        q = q.filter(AuditLog.level == level)
    if date_from:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.created_at <= date_to)

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    total_errors = AuditLog.query.filter(AuditLog.level == "error").count()
    total_warnings = AuditLog.query.filter(AuditLog.level == "warning").count()

    return {
        "pagination": pagination,
        "stats": {
            "total_incidents": total_errors + total_warnings,
            "errors": total_errors,
            "warnings": total_warnings,
        },
    }


def get_incidents_report_all(
    *,
    level: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[AuditLog]:
    """All incident entries (for CSV/PDF export)."""
    q = AuditLog.query.filter(
        AuditLog.level.in_(["warning", "error", "danger"])
    ).order_by(desc(AuditLog.created_at))
    if level:
        q = q.filter(AuditLog.level == level)
    if date_from:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.created_at <= date_to)
    return q.all()


# ─── System status checks ────────────────────────────────────────────────────

def _check_postgresql() -> dict[str, str]:
    """Check PostgreSQL connectivity."""
    try:
        db.session.execute(text("SELECT 1"))
        return {"name": "PostgreSQL", "status": "ok", "detail": "Conexion correcta"}
    except Exception as exc:
        return {"name": "PostgreSQL", "status": "error", "detail": str(exc)[:120]}


def _check_mongodb() -> dict[str, str]:
    """Check MongoDB/Overleaf connectivity."""
    try:
        uri = current_app.config.get("MONGO_URI", "")
        if not uri:
            return {"name": "MongoDB / Overleaf", "status": "warn", "detail": "MONGO_URI no configurada"}
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        client.close()
        return {"name": "MongoDB / Overleaf", "status": "ok", "detail": "Conexion correcta"}
    except Exception as exc:
        # Connection failure is a warning, not a critical error —
        # MongoDB is the Overleaf source, not essential for the admin panel itself.
        return {"name": "MongoDB / Overleaf", "status": "warn", "detail": str(exc)[:120]}


def _check_docker() -> dict[str, str]:
    """Check Docker daemon connectivity (optional)."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        client.close()
        return {"name": "Docker", "status": "ok", "detail": "Daemon accesible"}
    except ImportError:
        return {"name": "Docker", "status": "warn", "detail": "SDK no disponible"}
    except Exception as exc:
        return {"name": "Docker", "status": "warn", "detail": str(exc)[:120]}


def check_system_status() -> list[dict[str, str]]:
    """Run all service checks."""
    return [_check_postgresql(), _check_mongodb(), _check_docker()]


# ─── Index stats (lightweight) ───────────────────────────────────────────────

def get_index_stats() -> dict[str, Any]:
    """Fast, lightweight stats for the index page — no heavy queries."""
    last_general_export = (
        ReportExportLog.query
        .filter(
            ReportExportLog.report_type == "general",
            ReportExportLog.status == "completed",
        )
        .order_by(desc(ReportExportLog.generated_at))
        .first()
    )
    last_bundle_export = (
        ReportExportLog.query
        .filter(
            ReportExportLog.report_type == "todos",
            ReportExportLog.status == "completed",
        )
        .order_by(desc(ReportExportLog.generated_at))
        .first()
    )
    return {
        "last_general_export": last_general_export,
        "last_bundle_export": last_bundle_export,
    }


def get_all_reports_data() -> dict:
    """Gather data for every individual report in a single call.

    Used by the bundle (ZIP) export routes so each dataset is fetched
    exactly once rather than once per route.
    """
    storage = get_storage_report()
    return {
        "users":        get_users_report_all(),
        "projects":     get_projects_report_all(),
        "storage_rows": storage["rows"],
        "storage":      storage,           # full dict for PDF (needs totals)
        "quotas":       get_quotas_report_all(),
        "activity":     get_activity_report_all(),
        "incidents":    get_incidents_report_all(),
        "syncs":        get_syncs_report_all(),
        "general":      get_general_report_data(),
    }


def get_last_exports_by_type() -> dict[str, ReportExportLog]:
    """Return the most recent completed export for each report_type.

    Returns a dict keyed by report_type (e.g. ``"usuarios"``) whose values
    are the latest :class:`ReportExportLog` row, regardless of format
    (CSV or PDF).
    """
    # Sub-query: max generated_at per report_type
    subq = (
        db.session.query(
            ReportExportLog.report_type,
            func.max(ReportExportLog.generated_at).label("max_at"),
        )
        .filter(ReportExportLog.status == "completed")
        .group_by(ReportExportLog.report_type)
        .subquery()
    )

    rows = (
        ReportExportLog.query
        .join(
            subq,
            db.and_(
                ReportExportLog.report_type == subq.c.report_type,
                ReportExportLog.generated_at == subq.c.max_at,
            ),
        )
        .all()
    )

    result: dict[str, ReportExportLog] = {}
    for r in rows:
        result[r.report_type] = r
    return result


def get_last_general_export():
    """Return last completed general export (or None)."""
    return (
        ReportExportLog.query
        .filter(
            ReportExportLog.report_type == "general",
            ReportExportLog.status == "completed",
        )
        .order_by(desc(ReportExportLog.generated_at))
        .first()
    )


# ─── AJAX section endpoints for general report ──────────────────────────────

def get_general_section_resumen() -> dict[str, Any]:
    """Lightweight summary for the general report resumen section."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    total_users = OverleafUser.query.count()
    total_projects = OverleafProject.query.count()
    total_storage = float(
        db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    )
    total_syncs = SyncRun.query.count()
    success_syncs = SyncRun.query.filter(SyncRun.status == "success").count()
    success_pct = round((success_syncs / total_syncs) * 100, 1) if total_syncs else 0
    total_admins_internal = AdminUser.query.count()
    total_roles = Role.query.count()
    active_alerts_count = (
        AuditLog.query
        .filter(AuditLog.level.in_(["error", "warning"]),
                AuditLog.created_at >= last_24h)
        .count()
    )

    return {
        "total_users": total_users,
        "total_projects": total_projects,
        "total_storage_fmt": _fmt_bytes(total_storage),
        "total_syncs": total_syncs,
        "success_pct": success_pct,
        "total_admins_internal": total_admins_internal,
        "total_roles": total_roles,
        "active_alerts_count": active_alerts_count,
    }


def get_general_section_usuarios() -> dict[str, Any]:
    """Users section data for the general report."""
    all_users = OverleafUser.query.all()
    total_users = len(all_users)

    roles = Role.query.order_by(Role.name).all()
    users_by_role = []
    for r in roles:
        cnt = r.users.count()
        users_by_role.append({"name": r.name, "count": cnt, "color": r.color or "#6c757d"})

    users_no_role = OverleafUser.query.filter(OverleafUser.role_id == None).count()

    users_near_quota = []
    users_exceeded_quota = []
    for u in all_users:
        pct = u.quota_percent
        if pct is None:
            continue
        if pct >= 100:
            users_exceeded_quota.append({
                "email": u.email or u.overleaf_id,
                "pct": pct,
                "used_fmt": u.quota_used_fmt,
                "quota_fmt": u.quota_max_fmt,
            })
        elif pct >= 80:
            users_near_quota.append({
                "email": u.email or u.overleaf_id,
                "pct": pct,
                "used_fmt": u.quota_used_fmt,
                "quota_fmt": u.quota_max_fmt,
            })

    return {
        "total_users": total_users,
        "users_by_role": users_by_role,
        "users_no_role": users_no_role,
        "users_near_quota": users_near_quota,
        "users_exceeded_quota": users_exceeded_quota,
    }


def get_general_section_proyectos() -> dict[str, Any]:
    """Projects section data for the general report."""
    cutoff_inactive = datetime.now(timezone.utc) - timedelta(days=_INACTIVE_DAYS)

    total_projects = OverleafProject.query.count()
    large_projects = OverleafProject.query.filter(
        OverleafProject.size_bytes >= _LARGE_BYTES
    ).count()
    inactive_projects = OverleafProject.query.filter(
        db.or_(
            OverleafProject.last_updated_at < cutoff_inactive,
            OverleafProject.last_updated_at == None,
        )
    ).count()
    collab_ids = db.session.query(ProjectMember.project_id).distinct().all()
    collaborative_projects = len(collab_ids)

    top_projects_size = (
        OverleafProject.query
        .filter(
            OverleafProject.size_bytes != None,
            OverleafProject.size_bytes > 0,
        )
        .order_by(desc(OverleafProject.size_bytes))
        .limit(5)
        .all()
    )
    top_projects = []
    for p in top_projects_size:
        top_projects.append({
            "name": p.name or p.overleaf_id,
            "owner_email": p.owner.email if p.owner else "N/A",
            "size_fmt": _fmt_bytes(p.size_bytes),
        })

    return {
        "total_projects": total_projects,
        "large_projects": large_projects,
        "inactive_projects": inactive_projects,
        "collaborative_projects": collaborative_projects,
        "top_projects_size": top_projects,
    }


def get_general_section_almacenamiento() -> dict[str, Any]:
    """Storage/quota section data for the general report."""
    total_users = OverleafUser.query.count()
    total_projects = OverleafProject.query.count()
    total_storage = float(
        db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    )
    avg_per_user = total_storage / total_users if total_users else 0
    avg_per_project = total_storage / total_projects if total_projects else 0

    top_users_storage = (
        db.session.query(
            OverleafProject.owner_id,
            func.sum(OverleafProject.size_bytes).label("used"),
        )
        .filter(OverleafProject.owner_id != None)
        .group_by(OverleafProject.owner_id)
        .having(func.sum(OverleafProject.size_bytes) > 0)
        .order_by(desc("used"))
        .limit(5)
        .all()
    )
    top_user_ids = [r.owner_id for r in top_users_storage]
    top_users_map = {}
    if top_user_ids:
        for u in OverleafUser.query.filter(OverleafUser.id.in_(top_user_ids)).all():
            top_users_map[u.id] = u
    top_users = []
    for r in top_users_storage:
        u = top_users_map.get(r.owner_id)
        if u:
            top_users.append({
                "email": u.email or u.overleaf_id,
                "used_fmt": _fmt_bytes(r.used),
            })

    return {
        "total_storage_fmt": _fmt_bytes(total_storage),
        "avg_storage_per_user_fmt": _fmt_bytes(avg_per_user),
        "avg_storage_per_project_fmt": _fmt_bytes(avg_per_project),
        "top_users_storage": top_users,
    }


def get_general_section_sincronizacion() -> dict[str, Any]:
    """Sync section data for the general report."""
    total_syncs = SyncRun.query.count()
    success_syncs = SyncRun.query.filter(SyncRun.status == "success").count()
    success_pct = round((success_syncs / total_syncs) * 100, 1) if total_syncs else 0

    finished_runs = (
        SyncRun.query
        .filter(SyncRun.finished_at != None, SyncRun.started_at != None)
        .all()
    )
    if finished_runs:
        durations = [(r.finished_at - r.started_at).total_seconds() for r in finished_runs]
        avg_sync_duration = round(sum(durations) / len(durations), 1)
    else:
        avg_sync_duration = None

    last_sync = SyncRun.query.order_by(desc(SyncRun.started_at)).first()
    last_sync_data = None
    if last_sync:
        last_sync_data = {
            "started_at": last_sync.started_at.strftime("%d/%m/%Y %H:%M") if last_sync.started_at else None,
            "status": last_sync.status,
        }

    failed_syncs_recent = (
        SyncRun.query
        .filter(SyncRun.status == "error")
        .order_by(desc(SyncRun.started_at))
        .limit(5)
        .all()
    )
    failed_list = []
    for sr in failed_syncs_recent:
        failed_list.append({
            "started_at": sr.started_at.strftime("%d/%m/%Y %H:%M") if sr.started_at else "",
            "triggered_by": sr.triggered_by,
            "message": sr.message or "",
        })

    return {
        "total_syncs": total_syncs,
        "success_pct": success_pct,
        "avg_sync_duration": avg_sync_duration,
        "last_sync": last_sync_data,
        "failed_syncs_recent": failed_list,
    }


def get_general_section_auditoria() -> dict[str, Any]:
    """Audit/incidents section data for the general report."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    active_alerts_count = (
        AuditLog.query
        .filter(AuditLog.level.in_(["error", "warning"]),
                AuditLog.created_at >= last_24h)
        .count()
    )

    recent_errors = (
        AuditLog.query
        .filter(AuditLog.level.in_(["error", "warning"]))
        .order_by(desc(AuditLog.created_at))
        .limit(5)
        .all()
    )
    errors_list = []
    for e in recent_errors:
        errors_list.append({
            "created_at": e.created_at.strftime("%d/%m/%Y %H:%M") if e.created_at else "",
            "level": e.level,
            "actor": e.actor,
            "action": e.action,
            "detail": (e.detail or "")[:100],
        })

    recent_role_changes = (
        RoleChangeLog.query
        .order_by(desc(RoleChangeLog.changed_at))
        .limit(5)
        .all()
    )
    role_changes_list = []
    for rc in recent_role_changes:
        role_changes_list.append({
            "changed_at": rc.changed_at.strftime("%d/%m/%Y %H:%M") if rc.changed_at else "",
            "changed_by": rc.changed_by,
            "action": rc.action,
            "role_from": rc.role_from.name if rc.role_from else "",
            "role_to": rc.role_to.name if rc.role_to else "",
        })

    return {
        "active_alerts_count": active_alerts_count,
        "recent_errors": errors_list,
        "recent_role_changes": role_changes_list,
    }


# ─── General platform report (full — for PDF/CSV export) ────────────────────

def get_general_report_data() -> dict[str, Any]:
    """Gather ALL data needed for the general platform report PDF/CSV.

    NOTE: Sections 'Estado del sistema' and 'Conclusion automatica'
    have been removed from the general report.
    """
    now = datetime.now(timezone.utc)
    cutoff_inactive = now - timedelta(days=_INACTIVE_DAYS)
    last_24h = now - timedelta(hours=24)

    # ── Users ────────────────────────────────────────────────────────────
    all_users = OverleafUser.query.all()
    total_users = len(all_users)
    total_admins_internal = AdminUser.query.count()
    total_roles = Role.query.count()

    roles = Role.query.order_by(Role.name).all()
    users_by_role = []
    for r in roles:
        cnt = r.users.count()
        users_by_role.append({"name": r.name, "count": cnt, "color": r.color})

    users_no_role = OverleafUser.query.filter(OverleafUser.role_id == None).count()

    users_near_quota = []
    users_exceeded_quota = []
    for u in all_users:
        pct = u.quota_percent
        if pct is None:
            continue
        if pct >= 100:
            users_exceeded_quota.append({
                "email": u.email or u.overleaf_id,
                "pct": pct,
                "used_fmt": u.quota_used_fmt,
                "quota_fmt": u.quota_max_fmt,
            })
        elif pct >= 80:
            users_near_quota.append({
                "email": u.email or u.overleaf_id,
                "pct": pct,
                "used_fmt": u.quota_used_fmt,
                "quota_fmt": u.quota_max_fmt,
            })

    # ── Projects ─────────────────────────────────────────────────────────
    total_projects = OverleafProject.query.count()
    large_projects = OverleafProject.query.filter(
        OverleafProject.size_bytes >= _LARGE_BYTES
    ).count()
    inactive_projects = OverleafProject.query.filter(
        db.or_(
            OverleafProject.last_updated_at < cutoff_inactive,
            OverleafProject.last_updated_at == None,
        )
    ).count()

    collab_ids = (
        db.session.query(ProjectMember.project_id)
        .distinct()
        .all()
    )
    collaborative_projects = len(collab_ids)

    # ── Storage ──────────────────────────────────────────────────────────
    total_storage = float(
        db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    )
    avg_storage_per_user = total_storage / total_users if total_users else 0
    avg_storage_per_project = total_storage / total_projects if total_projects else 0

    top_users_storage = (
        db.session.query(
            OverleafProject.owner_id,
            func.sum(OverleafProject.size_bytes).label("used"),
        )
        .filter(OverleafProject.owner_id != None)
        .group_by(OverleafProject.owner_id)
        .having(func.sum(OverleafProject.size_bytes) > 0)
        .order_by(desc("used"))
        .limit(5)
        .all()
    )
    top_user_ids = [r.owner_id for r in top_users_storage]
    top_users_map = {}
    if top_user_ids:
        for u in OverleafUser.query.filter(OverleafUser.id.in_(top_user_ids)).all():
            top_users_map[u.id] = u
    top_users = []
    for r in top_users_storage:
        u = top_users_map.get(r.owner_id)
        if u:
            top_users.append({
                "email": u.email or u.overleaf_id,
                "used_fmt": _fmt_bytes(r.used),
            })

    top_projects_size = (
        OverleafProject.query
        .filter(
            OverleafProject.size_bytes != None,
            OverleafProject.size_bytes > 0,
        )
        .order_by(desc(OverleafProject.size_bytes))
        .limit(5)
        .all()
    )
    top_projects = []
    for p in top_projects_size:
        top_projects.append({
            "name": p.name or p.overleaf_id,
            "owner_email": p.owner.email if p.owner else "N/A",
            "size_fmt": _fmt_bytes(p.size_bytes),
        })

    # ── Sync ─────────────────────────────────────────────────────────────
    total_syncs = SyncRun.query.count()
    success_syncs = SyncRun.query.filter(SyncRun.status == "success").count()
    success_pct = round((success_syncs / total_syncs) * 100, 1) if total_syncs else 0

    finished_runs = (
        SyncRun.query
        .filter(SyncRun.finished_at != None, SyncRun.started_at != None)
        .all()
    )
    if finished_runs:
        durations = [(r.finished_at - r.started_at).total_seconds() for r in finished_runs]
        avg_sync_duration = round(sum(durations) / len(durations), 1)
    else:
        avg_sync_duration = None

    last_sync = SyncRun.query.order_by(desc(SyncRun.started_at)).first()

    failed_syncs_recent = (
        SyncRun.query
        .filter(SyncRun.status == "error")
        .order_by(desc(SyncRun.started_at))
        .limit(5)
        .all()
    )

    # ── Audit ────────────────────────────────────────────────────────────
    recent_role_changes = (
        RoleChangeLog.query
        .order_by(desc(RoleChangeLog.changed_at))
        .limit(5)
        .all()
    )

    recent_errors = (
        AuditLog.query
        .filter(AuditLog.level.in_(["error", "warning"]))
        .order_by(desc(AuditLog.created_at))
        .limit(5)
        .all()
    )

    active_alerts_count = (
        AuditLog.query
        .filter(AuditLog.level.in_(["error", "warning"]),
                AuditLog.created_at >= last_24h)
        .count()
    )

    return {
        # Users
        "total_users": total_users,
        "total_admins_internal": total_admins_internal,
        "total_roles": total_roles,
        "users_by_role": users_by_role,
        "users_no_role": users_no_role,
        "users_near_quota": users_near_quota,
        "users_exceeded_quota": users_exceeded_quota,
        # Projects
        "total_projects": total_projects,
        "large_projects": large_projects,
        "inactive_projects": inactive_projects,
        "collaborative_projects": collaborative_projects,
        # Storage
        "total_storage_fmt": _fmt_bytes(total_storage),
        "total_storage_bytes": total_storage,
        "avg_storage_per_user_fmt": _fmt_bytes(avg_storage_per_user),
        "avg_storage_per_project_fmt": _fmt_bytes(avg_storage_per_project),
        "top_users_storage": top_users,
        "top_projects_size": top_projects,
        # Sync
        "total_syncs": total_syncs,
        "success_pct": success_pct,
        "avg_sync_duration": avg_sync_duration,
        "last_sync": last_sync,
        "failed_syncs_recent": failed_syncs_recent,
        # Audit
        "recent_role_changes": recent_role_changes,
        "recent_errors": recent_errors,
        "active_alerts_count": active_alerts_count,
        # Meta
        "generated_at": now,
    }


# ─── Index / overview (kept for backward compat with tests) ──────────────────

def get_reports_overview() -> dict[str, Any]:
    """Summary numbers shown on the reports index page."""
    now = datetime.now(timezone.utc)
    this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if this_month.month == 1:
        last_month = this_month.replace(year=this_month.year - 1, month=12)
    else:
        last_month = this_month.replace(month=this_month.month - 1)

    total_users = OverleafUser.query.count()
    total_projects = OverleafProject.query.count()
    total_bytes = db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    total_syncs = SyncRun.query.count()
    audit_errors = AuditLog.query.filter(AuditLog.level == "error").count()
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
        .filter(
            OverleafProject.created_at >= last_month,
            OverleafProject.created_at < this_month,
        )
        .scalar() or 0
    )

    syncs_this = SyncRun.query.filter(SyncRun.started_at >= this_month).count()
    syncs_last = SyncRun.query.filter(
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
        "total_users": total_users,
        "total_projects": total_projects,
        "total_bytes": float(total_bytes),
        "total_bytes_fmt": _fmt_bytes(total_bytes),
        "storage_val": storage_val,
        "storage_unit": storage_unit,
        "total_syncs": total_syncs,
        "audit_errors": audit_errors,
        "audit_warnings": audit_warnings,
        "alerts_total": audit_errors + audit_warnings,
        "exceeded_users": exceeded_users,
        "last_sync": last_sync,
        "trends": {
            "users":    _trend(users_this, users_last),
            "projects": _trend(proj_this, proj_last),
            "storage":  _trend(int(size_this), int(size_last)),
            "syncs":    _trend(syncs_this, syncs_last),
            "alerts":   _trend(errors_this, errors_last),
        },
    }
