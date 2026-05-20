"""
service/report_queries.py
--------------------------
Query functions for the 7 individual downloadable reports:
users, projects, storage, activity, syncs, quotas, incidents.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import func, desc, asc

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.project_member import ProjectMember
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun
from app.model.entities.role import Role
from app.model.entities.system_alert import SystemAlert

from ._helpers import _INACTIVE_DAYS, _LARGE_BYTES, _fmt_bytes


# ─── Users ───────────────────────────────────────────────────────────────────

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
        "email":         OverleafUser.email,
        "first_name":    OverleafUser.first_name,
        "last_name":     OverleafUser.last_name,
        "signup_date":   OverleafUser.signup_date,
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
            if quota_filter == "exceeded":  return pct is not None and pct >= 100
            if quota_filter == "warning":   return pct is not None and 80 <= pct < 100
            if quota_filter == "ok":        return pct is not None and pct < 80
            if quota_filter == "unlimited": return u.max_quota_bytes is None
            return True
        items = [u for u in items if _keep(u)]

    all_users = OverleafUser.query.all()
    total    = len(all_users)
    admins   = sum(1 for u in all_users if u.is_admin)
    exceeded = sum(1 for u in all_users if u.quota_exceeded)
    unlimited = sum(1 for u in all_users if u.max_quota_bytes is None)

    return {
        "pagination": pagination,
        "items": items,
        "stats": {
            "total": total, "admins": admins,
            "exceeded": exceeded, "unlimited": unlimited,
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


# ─── Projects ────────────────────────────────────────────────────────────────

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
        "name":           OverleafProject.name,
        "size_bytes":     OverleafProject.size_bytes,
        "last_updated_at":OverleafProject.last_updated_at,
        "created_at":     OverleafProject.created_at,
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
    large_count    = OverleafProject.query.filter(
        OverleafProject.size_bytes >= _LARGE_BYTES
    ).count()
    inactive_count = OverleafProject.query.filter(
        db.or_(
            OverleafProject.last_updated_at < cutoff_inactive,
            OverleafProject.last_updated_at == None,
        )
    ).count()
    total_size = db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0

    owner_id_rows  = (
        db.session.query(OverleafProject.owner_id)
        .filter(OverleafProject.owner_id != None)
        .distinct().all()
    )
    owner_id_list = [r[0] for r in owner_id_rows]
    owners = (
        OverleafUser.query
        .filter(OverleafUser.id.in_(owner_id_list))
        .order_by(OverleafUser.email)
        .all()
    ) if owner_id_list else []

    return {
        "pagination":   pagination,
        "member_counts":member_counts,
        "owners":       owners,
        "stats": {
            "total":          total_projects,
            "large":          large_count,
            "inactive":       inactive_count,
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


# ─── Storage ─────────────────────────────────────────────────────────────────

def get_storage_report() -> dict[str, Any]:
    """Aggregate storage stats per user + global totals."""
    total_bytes    = db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    total_projects = OverleafProject.query.count()
    total_users    = OverleafUser.query.count()

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
        used  = row.used or 0
        quota = u.max_quota_bytes
        pct   = round((used / quota) * 100, 1) if quota else None
        rows.append({
            "user":       u,
            "used_bytes": used,
            "used_fmt":   _fmt_bytes(used),
            "quota_fmt":  _fmt_bytes(quota) if quota else "Sin limite",
            "quota_pct":  pct,
            "proj_count": row.proj_count,
        })

    avg_per_user    = float(total_bytes) / total_users    if total_users    else 0
    avg_per_project = float(total_bytes) / total_projects if total_projects else 0

    return {
        "total_bytes":        total_bytes,
        "total_bytes_fmt":    _fmt_bytes(total_bytes),
        "total_projects":     total_projects,
        "total_users":        total_users,
        "avg_per_user_fmt":   _fmt_bytes(avg_per_user),
        "avg_per_project_fmt":_fmt_bytes(avg_per_project),
        "rows":               rows,
    }


# ─── Activity ────────────────────────────────────────────────────────────────

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
    if level:  q = q.filter(AuditLog.level == level)
    if action: q = q.filter(AuditLog.action == action)
    if actor:  q = q.filter(AuditLog.actor == actor)
    if date_from: q = q.filter(AuditLog.created_at >= date_from)
    if date_to:   q = q.filter(AuditLog.created_at <= date_to)

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    total    = AuditLog.query.count()
    errors   = AuditLog.query.filter(AuditLog.level == "error").count()
    warnings = AuditLog.query.filter(AuditLog.level == "warning").count()

    action_names = [
        r[0] for r in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    ]
    actor_names = [
        r[0] for r in db.session.query(AuditLog.actor).distinct().order_by(AuditLog.actor).all()
    ]

    return {
        "pagination":   pagination,
        "stats":        {"total": total, "errors": errors, "warnings": warnings},
        "action_names": action_names,
        "actor_names":  actor_names,
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
    if level:     q = q.filter(AuditLog.level == level)
    if action:    q = q.filter(AuditLog.action == action)
    if actor:     q = q.filter(AuditLog.actor == actor)
    if date_from: q = q.filter(AuditLog.created_at >= date_from)
    if date_to:   q = q.filter(AuditLog.created_at <= date_to)
    return q.all()


# ─── Syncs ───────────────────────────────────────────────────────────────────

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

    if status:        q = q.filter(SyncRun.status == status)
    if triggered_by:  q = q.filter(SyncRun.triggered_by == triggered_by)
    if date_from:     q = q.filter(SyncRun.started_at >= date_from)
    if date_to:       q = q.filter(SyncRun.started_at <= date_to)

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    total   = SyncRun.query.count()
    errors  = SyncRun.query.filter(SyncRun.status == "error").count()
    success = SyncRun.query.filter(SyncRun.status == "success").count()

    finished_runs = (
        SyncRun.query
        .filter(SyncRun.finished_at != None, SyncRun.started_at != None)
        .all()
    )
    if finished_runs:
        durations  = [(r.finished_at - r.started_at).total_seconds() for r in finished_runs]
        avg_dur_s  = round(sum(durations) / len(durations), 1)
    else:
        avg_dur_s = None

    return {
        "pagination": pagination,
        "stats": {
            "total": total, "success": success,
            "errors": errors, "avg_duration_s": avg_dur_s,
        },
    }


def get_syncs_report_all(
    *,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[SyncRun]:
    q = SyncRun.query.order_by(desc(SyncRun.started_at))
    if status:    q = q.filter(SyncRun.status == status)
    if date_from: q = q.filter(SyncRun.started_at >= date_from)
    if date_to:   q = q.filter(SyncRun.started_at <= date_to)
    return q.all()


# ─── Quotas ──────────────────────────────────────────────────────────────────

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
        if pct is None:      st = "unlimited"
        elif pct >= 100:     st = "exceeded"
        elif pct >= 80:      st = "warning"
        else:                st = "ok"

        if status_filter and st != status_filter:
            continue

        role      = u.role
        max_proj  = role.max_projects if role else None
        owned_cnt = u.projects_owned.count()
        collab_cnt= u.memberships.count()

        rows.append({
            "user":                 u,
            "used_bytes":           u.quota_used_bytes,
            "used_fmt":             u.quota_used_fmt,
            "quota_bytes":          u.max_quota_bytes,
            "quota_fmt":            u.quota_max_fmt,
            "pct":                  pct,
            "status":               st,
            "projects_count":       owned_cnt,
            "collab_count":         collab_cnt,
            "role_name":            role.name if role else "Sin rol",
            "max_projects":         max_proj,
            "exceeds_project_limit":(max_proj is not None and owned_cnt > max_proj),
        })

    total      = len(rows)
    exceeded   = sum(1 for r in rows if r["status"] == "exceeded")  if not status_filter else None
    warning    = sum(1 for r in rows if r["status"] == "warning")   if not status_filter else None

    start       = (page - 1) * per_page
    page_items  = rows[start:start + per_page]
    total_pages = max(1, (total + per_page - 1) // per_page)

    return {
        "items":    page_items,
        "total":    total,
        "page":     page,
        "pages":    total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "stats": {
            "total_users": len(all_users),
            "exceeded": exceeded if exceeded is not None else sum(1 for r in rows if r["status"] == "exceeded"),
            "warning":  warning  if warning  is not None else sum(1 for r in rows if r["status"] == "warning"),
        },
    }


def get_quotas_report_all(*, status_filter: str | None = None) -> list[dict[str, Any]]:
    """All quota rows without pagination (for CSV/PDF export)."""
    return get_quotas_report(status_filter=status_filter, page=1, per_page=999999)["items"]


# ─── Incidents ────────────────────────────────────────────────────────────────

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

    if level:     q = q.filter(AuditLog.level == level)
    if date_from: q = q.filter(AuditLog.created_at >= date_from)
    if date_to:   q = q.filter(AuditLog.created_at <= date_to)

    pagination     = q.paginate(page=page, per_page=per_page, error_out=False)
    total_errors   = AuditLog.query.filter(AuditLog.level == "error").count()
    total_warnings = AuditLog.query.filter(AuditLog.level == "warning").count()

    return {
        "pagination": pagination,
        "stats": {
            "total_incidents": total_errors + total_warnings,
            "errors":   total_errors,
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
    if level:     q = q.filter(AuditLog.level == level)
    if date_from: q = q.filter(AuditLog.created_at >= date_from)
    if date_to:   q = q.filter(AuditLog.created_at <= date_to)
    return q.all()


# ─── Alerts (SystemAlert) ───────────────────────────────────────────────────

def get_alerts_report_all(
    *,
    level: str | None = None,
    alert_type: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[SystemAlert]:
    """All system alerts for CSV/PDF export."""
    q = SystemAlert.query.order_by(desc(SystemAlert.created_at))
    if level:      q = q.filter(SystemAlert.level == level)
    if alert_type: q = q.filter(SystemAlert.type == alert_type)
    if status == "active":
        q = q.filter(SystemAlert.is_resolved == False)
    elif status == "resolved":
        q = q.filter(SystemAlert.is_resolved == True)
    if date_from:  q = q.filter(SystemAlert.created_at >= date_from)
    if date_to:    q = q.filter(SystemAlert.created_at <= date_to)
    return q.all()
