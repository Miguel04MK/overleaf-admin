"""
service/general_queries.py
---------------------------
Query functions for the general platform report:
  - AJAX section endpoints (one function per section)
  - Full combined data fetch (get_general_report_data)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import func, desc

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.project_member import ProjectMember
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun
from app.model.entities.role import Role
from app.model.entities.role_change_log import RoleChangeLog
from app.model.entities.admin_user import AdminUser
from app.model.entities.system_alert import SystemAlert

from ._helpers import _INACTIVE_DAYS, _LARGE_BYTES, _fmt_bytes


# ─── AJAX section endpoints ───────────────────────────────────────────────────

def get_general_section_resumen() -> dict[str, Any]:
    now      = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    total_users    = OverleafUser.query.count()
    total_projects = OverleafProject.query.count()
    total_storage  = float(
        db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    )
    total_syncs    = SyncRun.query.count()
    success_syncs  = SyncRun.query.filter(SyncRun.status == "success").count()
    success_pct    = round((success_syncs / total_syncs) * 100, 1) if total_syncs else 0
    total_admins_internal = AdminUser.query.count()
    total_roles    = Role.query.count()
    active_alerts_count = (
        AuditLog.query
        .filter(AuditLog.level.in_(["error", "warning"]),
                AuditLog.created_at >= last_24h)
        .count()
    )

    return {
        "total_users":           total_users,
        "total_projects":        total_projects,
        "total_storage_fmt":     _fmt_bytes(total_storage),
        "total_syncs":           total_syncs,
        "success_pct":           success_pct,
        "total_admins_internal": total_admins_internal,
        "total_roles":           total_roles,
        "active_alerts_count":   active_alerts_count,
    }


def get_general_section_usuarios() -> dict[str, Any]:
    all_users   = OverleafUser.query.all()
    total_users = len(all_users)

    roles        = Role.query.order_by(Role.name).all()
    users_by_role = [
        {"name": r.name, "count": r.users.count(), "color": r.color or "#6c757d"}
        for r in roles
    ]

    users_no_role = OverleafUser.query.filter(OverleafUser.role_id == None).count()

    users_near_quota     = []
    users_exceeded_quota = []
    for u in all_users:
        pct = u.quota_percent
        if pct is None:
            continue
        entry = {
            "email":     u.email or u.overleaf_id,
            "pct":       pct,
            "used_fmt":  u.quota_used_fmt,
            "quota_fmt": u.quota_max_fmt,
        }
        if pct >= 100:
            users_exceeded_quota.append(entry)
        elif pct >= 80:
            users_near_quota.append(entry)

    return {
        "total_users":         total_users,
        "users_by_role":       users_by_role,
        "users_no_role":       users_no_role,
        "users_near_quota":    users_near_quota,
        "users_exceeded_quota":users_exceeded_quota,
    }


def get_general_section_proyectos() -> dict[str, Any]:
    cutoff_inactive = datetime.now(timezone.utc) - timedelta(days=_INACTIVE_DAYS)

    total_projects    = OverleafProject.query.count()
    large_projects    = OverleafProject.query.filter(
        OverleafProject.size_bytes >= _LARGE_BYTES
    ).count()
    inactive_projects = OverleafProject.query.filter(
        db.or_(
            OverleafProject.last_updated_at < cutoff_inactive,
            OverleafProject.last_updated_at == None,
        )
    ).count()
    collaborative_projects = len(
        db.session.query(ProjectMember.project_id).distinct().all()
    )

    top_projects_size = (
        OverleafProject.query
        .filter(OverleafProject.size_bytes != None, OverleafProject.size_bytes > 0)
        .order_by(desc(OverleafProject.size_bytes))
        .limit(5)
        .all()
    )
    top_projects = [
        {
            "name":        p.name or p.overleaf_id,
            "owner_email": p.owner.email if p.owner else "N/A",
            "size_fmt":    _fmt_bytes(p.size_bytes),
        }
        for p in top_projects_size
    ]

    return {
        "total_projects":        total_projects,
        "large_projects":        large_projects,
        "inactive_projects":     inactive_projects,
        "collaborative_projects":collaborative_projects,
        "top_projects_size":     top_projects,
    }


def get_general_section_almacenamiento() -> dict[str, Any]:
    total_users    = OverleafUser.query.count()
    total_projects = OverleafProject.query.count()
    total_storage  = float(
        db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    )
    avg_per_user    = total_storage / total_users    if total_users    else 0
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
    top_users_map: dict[int, OverleafUser] = {}
    if top_user_ids:
        for u in OverleafUser.query.filter(OverleafUser.id.in_(top_user_ids)).all():
            top_users_map[u.id] = u
    top_users = [
        {"email": top_users_map[r.owner_id].email or top_users_map[r.owner_id].overleaf_id,
         "used_fmt": _fmt_bytes(r.used)}
        for r in top_users_storage
        if r.owner_id in top_users_map
    ]

    return {
        "total_storage_fmt":          _fmt_bytes(total_storage),
        "avg_storage_per_user_fmt":   _fmt_bytes(avg_per_user),
        "avg_storage_per_project_fmt":_fmt_bytes(avg_per_project),
        "top_users_storage":          top_users,
    }


def get_general_section_sincronizacion() -> dict[str, Any]:
    total_syncs   = SyncRun.query.count()
    success_syncs = SyncRun.query.filter(SyncRun.status == "success").count()
    success_pct   = round((success_syncs / total_syncs) * 100, 1) if total_syncs else 0

    finished_runs = (
        SyncRun.query
        .filter(SyncRun.finished_at != None, SyncRun.started_at != None)
        .all()
    )
    if finished_runs:
        durations         = [(r.finished_at - r.started_at).total_seconds() for r in finished_runs]
        avg_sync_duration = round(sum(durations) / len(durations), 1)
    else:
        avg_sync_duration = None

    last_sync      = SyncRun.query.order_by(desc(SyncRun.started_at)).first()
    last_sync_data = None
    if last_sync:
        last_sync_data = {
            "started_at": last_sync.started_at.strftime("%d/%m/%Y %H:%M") if last_sync.started_at else None,
            "status":     last_sync.status,
        }

    failed_syncs_recent = (
        SyncRun.query
        .filter(SyncRun.status == "error")
        .order_by(desc(SyncRun.started_at))
        .limit(5)
        .all()
    )
    failed_list = [
        {
            "started_at":   sr.started_at.strftime("%d/%m/%Y %H:%M") if sr.started_at else "",
            "triggered_by": sr.triggered_by,
            "message":      sr.message or "",
        }
        for sr in failed_syncs_recent
    ]

    return {
        "total_syncs":        total_syncs,
        "success_pct":        success_pct,
        "avg_sync_duration":  avg_sync_duration,
        "last_sync":          last_sync_data,
        "failed_syncs_recent":failed_list,
    }


def get_general_section_auditoria() -> dict[str, Any]:
    now      = datetime.now(timezone.utc)
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
    errors_list = [
        {
            "created_at": e.created_at.strftime("%d/%m/%Y %H:%M") if e.created_at else "",
            "level":      e.level,
            "actor":      e.actor,
            "action":     e.action,
            "detail":     (e.detail or "")[:100],
        }
        for e in recent_errors
    ]

    recent_role_changes = (
        RoleChangeLog.query
        .order_by(desc(RoleChangeLog.changed_at))
        .limit(5)
        .all()
    )
    role_changes_list = [
        {
            "changed_at": rc.changed_at.strftime("%d/%m/%Y %H:%M") if rc.changed_at else "",
            "changed_by": rc.changed_by,
            "action":     rc.action,
            "role_from":  rc.role_from.name if rc.role_from else "",
            "role_to":    rc.role_to.name   if rc.role_to   else "",
        }
        for rc in recent_role_changes
    ]

    return {
        "active_alerts_count":  active_alerts_count,
        "recent_errors":        errors_list,
        "recent_role_changes":  role_changes_list,
    }


# ─── Full general report data (for PDF/CSV export) ───────────────────────────

def get_general_report_data() -> dict[str, Any]:
    """Gather ALL data needed for the general platform report PDF/CSV."""
    now             = datetime.now(timezone.utc)
    cutoff_inactive = now - timedelta(days=_INACTIVE_DAYS)
    last_24h        = now - timedelta(hours=24)

    # Users
    all_users             = OverleafUser.query.all()
    total_users           = len(all_users)
    total_admins_internal = AdminUser.query.count()
    total_roles           = Role.query.count()

    roles        = Role.query.order_by(Role.name).all()
    users_by_role = [
        {"name": r.name, "count": r.users.count(), "color": r.color}
        for r in roles
    ]
    users_no_role = OverleafUser.query.filter(OverleafUser.role_id == None).count()

    users_near_quota     = []
    users_exceeded_quota = []
    for u in all_users:
        pct = u.quota_percent
        if pct is None:
            continue
        entry = {
            "email":     u.email or u.overleaf_id,
            "pct":       pct,
            "used_fmt":  u.quota_used_fmt,
            "quota_fmt": u.quota_max_fmt,
        }
        if pct >= 100:    users_exceeded_quota.append(entry)
        elif pct >= 80:   users_near_quota.append(entry)

    # Projects
    total_projects    = OverleafProject.query.count()
    large_projects    = OverleafProject.query.filter(
        OverleafProject.size_bytes >= _LARGE_BYTES
    ).count()
    inactive_projects = OverleafProject.query.filter(
        db.or_(
            OverleafProject.last_updated_at < cutoff_inactive,
            OverleafProject.last_updated_at == None,
        )
    ).count()
    collaborative_projects = len(
        db.session.query(ProjectMember.project_id).distinct().all()
    )

    # Storage
    total_storage = float(
        db.session.query(func.sum(OverleafProject.size_bytes)).scalar() or 0
    )
    avg_storage_per_user    = total_storage / total_users    if total_users    else 0
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
    top_users_map: dict[int, OverleafUser] = {}
    if top_user_ids:
        for u in OverleafUser.query.filter(OverleafUser.id.in_(top_user_ids)).all():
            top_users_map[u.id] = u
    top_users = [
        {"email": top_users_map[r.owner_id].email or top_users_map[r.owner_id].overleaf_id,
         "used_fmt": _fmt_bytes(r.used)}
        for r in top_users_storage
        if r.owner_id in top_users_map
    ]

    top_projects_size = (
        OverleafProject.query
        .filter(OverleafProject.size_bytes != None, OverleafProject.size_bytes > 0)
        .order_by(desc(OverleafProject.size_bytes))
        .limit(5)
        .all()
    )
    top_projects = [
        {
            "name":        p.name or p.overleaf_id,
            "owner_email": p.owner.email if p.owner else "N/A",
            "size_fmt":    _fmt_bytes(p.size_bytes),
        }
        for p in top_projects_size
    ]

    # Sync
    total_syncs   = SyncRun.query.count()
    success_syncs = SyncRun.query.filter(SyncRun.status == "success").count()
    success_pct   = round((success_syncs / total_syncs) * 100, 1) if total_syncs else 0

    finished_runs = (
        SyncRun.query
        .filter(SyncRun.finished_at != None, SyncRun.started_at != None)
        .all()
    )
    if finished_runs:
        durations         = [(r.finished_at - r.started_at).total_seconds() for r in finished_runs]
        avg_sync_duration = round(sum(durations) / len(durations), 1)
    else:
        avg_sync_duration = None

    last_sync           = SyncRun.query.order_by(desc(SyncRun.started_at)).first()
    failed_syncs_recent = (
        SyncRun.query
        .filter(SyncRun.status == "error")
        .order_by(desc(SyncRun.started_at))
        .limit(5)
        .all()
    )

    # Audit
    recent_role_changes = (
        RoleChangeLog.query.order_by(desc(RoleChangeLog.changed_at)).limit(5).all()
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

    # System alerts
    system_alerts_active = (
        SystemAlert.query
        .filter(SystemAlert.is_resolved == False)
        .order_by(desc(SystemAlert.created_at))
        .limit(10)
        .all()
    )
    system_alerts_total = SystemAlert.query.count()
    system_alerts_unresolved = SystemAlert.query.filter(SystemAlert.is_resolved == False).count()
    system_alerts_critical = SystemAlert.query.filter(
        SystemAlert.level.in_(["critical", "danger"]),
        SystemAlert.is_resolved == False,
    ).count()

    return {
        # Users
        "total_users":           total_users,
        "total_admins_internal": total_admins_internal,
        "total_roles":           total_roles,
        "users_by_role":         users_by_role,
        "users_no_role":         users_no_role,
        "users_near_quota":      users_near_quota,
        "users_exceeded_quota":  users_exceeded_quota,
        # Projects
        "total_projects":        total_projects,
        "large_projects":        large_projects,
        "inactive_projects":     inactive_projects,
        "collaborative_projects":collaborative_projects,
        # Storage
        "total_storage_fmt":           _fmt_bytes(total_storage),
        "total_storage_bytes":         total_storage,
        "avg_storage_per_user_fmt":    _fmt_bytes(avg_storage_per_user),
        "avg_storage_per_project_fmt": _fmt_bytes(avg_storage_per_project),
        "top_users_storage":           top_users,
        "top_projects_size":           top_projects,
        # Sync
        "total_syncs":          total_syncs,
        "success_pct":          success_pct,
        "avg_sync_duration":    avg_sync_duration,
        "last_sync":            last_sync,
        "failed_syncs_recent":  failed_syncs_recent,
        # Audit
        "recent_role_changes":  recent_role_changes,
        "recent_errors":        recent_errors,
        "active_alerts_count":  active_alerts_count,
        # System alerts
        "system_alerts_active":     system_alerts_active,
        "system_alerts_total":      system_alerts_total,
        "system_alerts_unresolved": system_alerts_unresolved,
        "system_alerts_critical":   system_alerts_critical,
        # Meta
        "generated_at": now,
    }
