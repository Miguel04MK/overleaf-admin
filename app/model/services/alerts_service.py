"""
AlertsService — generate, query and manage SystemAlert records.

Alert generation uses an event-driven model:
  - check_user_quota(user_id)        → called after quota change
  - check_user_project_limit(user_id)→ called after role assignment/removal
  - check_role_users(role_id)        → called after role config update
  - check_last_sync()                → called after every sync (success or error)
  - check_all_quotas()               → bulk quota sweep
  - check_all_project_limits()       → bulk project-limit sweep
  - check_repeated_errors()          → called after sync or on demand
  - recalculate_alerts(actor)        → manual button / scheduled tasks only

Deduplication is handled by _upsert():
  - If an active alert with same (type, entity_type, entity_id) exists,
    it is updated (no duplicate created, no extra email sent).
  - If the alert was previously resolved and the condition recurs,
    a brand-new alert is created (and a notification email is sent).

Thresholds are read from the app_settings table with fallback to constants.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import case, or_

from app.config.extensions import db
from app.model.entities.system_alert import SystemAlert
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.sync_run import SyncRun
from app.model.entities.audit_log import AuditLog
from app.model.services.admin.admin_service import log_action

logger = logging.getLogger(__name__)

# Hard-coded fallback thresholds (used when app_settings row is absent)
_QUOTA_WARNING_PCT_DEFAULT   = 80
_QUOTA_EXCEEDED_PCT_DEFAULT  = 100
_REPEATED_ERRORS_N_DEFAULT   = 5
_REPEATED_ERRORS_HRS_DEFAULT = 24
_SYNC_MAX_HOURS_DEFAULT      = 24

# SQL expression: severity order (critical=0 … info=3, unknown=99)
_LEVEL_ORDER = case(
    (SystemAlert.level == "critical", 0),
    (SystemAlert.level == "danger",   1),
    (SystemAlert.level == "warning",  2),
    (SystemAlert.level == "info",     3),
    else_=99,
)


# ── Threshold helpers ─────────────────────────────────────────────────────────

def _threshold(key: str, default: int | float) -> int | float:
    """Read a threshold from app_settings; fall back to the hardcoded default."""
    try:
        from app.model.entities.app_setting import AppSetting
        setting = db.session.get(AppSetting, key)
        if setting is not None:
            return type(default)(setting.value)
    except Exception:
        pass
    return default


def get_thresholds() -> dict:
    """Return all alert thresholds as a dict of {key: {value, description}}."""
    from app.model.entities.app_setting import AppSetting, DEFAULT_THRESHOLDS
    result = {}
    for key, (default_value, description) in DEFAULT_THRESHOLDS.items():
        setting = db.session.get(AppSetting, key)
        result[key] = {
            "value":       int(setting.value) if setting else int(default_value),
            "description": description,
        }
    return result


def update_thresholds(data: dict, actor: str) -> None:
    """Persist updated threshold values to app_settings."""
    from app.model.entities.app_setting import AppSetting, DEFAULT_THRESHOLDS
    now = datetime.now(timezone.utc)
    for key, raw_value in data.items():
        if key not in DEFAULT_THRESHOLDS:
            continue
        setting = db.session.get(AppSetting, key)
        if setting:
            setting.value      = str(int(raw_value))
            setting.updated_at = now
            setting.updated_by = actor
        else:
            _, description = DEFAULT_THRESHOLDS[key]
            db.session.add(AppSetting(
                key=key, value=str(int(raw_value)),
                description=description,
                updated_at=now, updated_by=actor,
            ))
    db.session.commit()
    log_action(
        action="thresholds_update", actor=actor,
        detail=f"Umbrales actualizados: {list(data.keys())}",
        level="info",
    )


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_alerts_page(
    page: int = 1,
    per_page: int = 10,
    status: str = "active",
    level: str | None = None,
    type_: str | None = None,
    unread: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """
    Return a paginated, server-side-sorted page of alerts.

    Sort order: active first, then by severity (critical→info), then newest.
    Pagination and sorting happen entirely in PostgreSQL — the frontend
    receives only the rows for the requested page.
    """
    query = SystemAlert.query

    if status == "active":
        query = query.filter_by(is_resolved=False)
    elif status == "resolved":
        query = query.filter_by(is_resolved=True)
    # "all" → no status filter

    if level:
        query = query.filter(SystemAlert.level == level)
    if type_:
        query = query.filter(SystemAlert.type == type_)
    if unread == "yes":
        query = query.filter_by(is_read=False)
    elif unread == "no":
        query = query.filter_by(is_read=True)

    if q:
        term = f"%{q}%"
        query = query.filter(
            or_(
                SystemAlert.title.ilike(term),
                SystemAlert.message.ilike(term),
                SystemAlert.entity_id.ilike(term),
            )
        )

    if date_from:
        try:
            df = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.filter(SystemAlert.created_at >= df)
        except ValueError:
            pass

    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            query = query.filter(SystemAlert.created_at <= dt)
        except ValueError:
            pass

    # SQL sort: active first, then severity (critical→info), then newest
    query = query.order_by(
        SystemAlert.is_resolved.asc(),
        _LEVEL_ORDER.asc(),
        SystemAlert.created_at.desc(),
    )

    return query.paginate(page=page, per_page=per_page, error_out=False)


def get_active_count() -> int:
    return SystemAlert.query.filter_by(is_resolved=False).count()


def get_unread_count() -> int:
    return SystemAlert.query.filter_by(is_resolved=False, is_read=False).count()


def get_critical_count() -> int:
    return SystemAlert.query.filter(
        SystemAlert.is_resolved == False,          # noqa: E712
        SystemAlert.level.in_(["danger", "critical"]),
    ).count()


def get_resolved_count() -> int:
    return SystemAlert.query.filter_by(is_resolved=True).count()


def get_recent_alerts(limit: int = 5) -> list:
    return (
        SystemAlert.query
        .filter_by(is_resolved=False)
        .order_by(SystemAlert.created_at.desc())
        .limit(limit)
        .all()
    )


def get_last_recalc_time():
    entry = (
        AuditLog.query
        .filter_by(action="alerts_recalculate")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    return entry.created_at if entry else None


# ── State mutations — individual ──────────────────────────────────────────────

def mark_as_read(alert_id: int, actor: str) -> tuple[bool, str]:
    alert = db.session.get(SystemAlert, alert_id)
    if not alert:
        return False, "Alerta no encontrada."
    alert.is_read = True
    db.session.commit()
    log_action(
        action="alert_mark_read", actor=actor,
        detail=f"Alerta #{alert_id} ({alert.type}, {alert.level}) marcada como leída.",
        level="info",
    )
    return True, "Alerta marcada como leída."


def mark_as_resolved(
    alert_id: int,
    actor: str,
    comment: str | None = None,
) -> tuple[bool, str]:
    alert = db.session.get(SystemAlert, alert_id)
    if not alert:
        return False, "Alerta no encontrada."
    if alert.is_resolved:
        return False, "La alerta ya está resuelta."
    now = datetime.now(timezone.utc)
    alert.is_resolved        = True
    alert.is_read            = True
    alert.resolved_at        = now
    alert.resolved_by        = actor
    alert.resolution_comment = comment or None
    db.session.commit()
    detail = f"Alerta #{alert_id} ({alert.type}, {alert.level}) resuelta."
    if comment:
        detail += f" Comentario: {comment}"
    log_action(action="alert_resolve", actor=actor, detail=detail, level="info")
    return True, "Alerta resuelta correctamente."


def reopen_alert(alert_id: int, actor: str) -> tuple[bool, str]:
    alert = db.session.get(SystemAlert, alert_id)
    if not alert:
        return False, "Alerta no encontrada."
    if not alert.is_resolved:
        return False, "La alerta no está resuelta."
    alert.is_resolved = False
    alert.resolved_at = None
    alert.resolved_by = None
    db.session.commit()
    log_action(
        action="alert_reopen", actor=actor,
        detail=f"Alerta #{alert_id} ({alert.type}, {alert.level}) reabierta.",
        level="info",
    )
    return True, "Alerta reabierta."


# ── State mutations — bulk ────────────────────────────────────────────────────

def mark_many_read(alert_ids: list[int], actor: str) -> int:
    """Mark multiple alerts as read. Returns number actually updated."""
    count = 0
    for aid in alert_ids:
        alert = db.session.get(SystemAlert, aid)
        if alert and not alert.is_read:
            alert.is_read = True
            count += 1
    if count:
        db.session.commit()
        log_action(
            action="alert_mark_read_bulk", actor=actor,
            detail=f"{count} alertas marcadas como leídas en bloque.",
            level="info",
        )
    return count


def resolve_many(
    alert_ids: list[int],
    actor: str,
    comment: str | None = None,
) -> int:
    """Resolve multiple alerts. Returns number actually updated."""
    now   = datetime.now(timezone.utc)
    count = 0
    for aid in alert_ids:
        alert = db.session.get(SystemAlert, aid)
        if alert and not alert.is_resolved:
            alert.is_resolved        = True
            alert.is_read            = True
            alert.resolved_at        = now
            alert.resolved_by        = actor
            alert.resolution_comment = comment or None
            count += 1
    if count:
        db.session.commit()
        detail = f"{count} alertas resueltas en bloque."
        if comment:
            detail += f" Comentario: {comment}"
        log_action(action="alert_resolve_bulk", actor=actor, detail=detail, level="info")
    return count


def reopen_many(alert_ids: list[int], actor: str) -> int:
    """Reopen multiple resolved alerts. Returns number actually updated."""
    count = 0
    for aid in alert_ids:
        alert = db.session.get(SystemAlert, aid)
        if alert and alert.is_resolved:
            alert.is_resolved = False
            alert.resolved_at = None
            alert.resolved_by = None
            count += 1
    if count:
        db.session.commit()
        log_action(
            action="alert_reopen_bulk", actor=actor,
            detail=f"{count} alertas reabiertas en bloque.",
            level="info",
        )
    return count


# ── Internal helpers ──────────────────────────────────────────────────────────

def _upsert(
    type: str,
    level: str,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    source: str | None = None,
    extra_data: dict | None = None,
) -> SystemAlert:
    """
    Create a new alert or update an existing active one with the same key.

    Deduplication key: (type, entity_type, entity_id, is_resolved=False).
    - If an active alert with this key exists → update it (no email sent).
    - If no active alert exists → create a new one and send notifications.
    - If the problem previously resolved and recurs → new alert + notification.
    """
    existing = SystemAlert.query.filter_by(
        type=type,
        entity_type=entity_type,
        entity_id=entity_id,
        is_resolved=False,
    ).first()

    if existing:
        # Update in place — no notification (not genuinely new)
        existing.level   = level
        existing.title   = title
        existing.message = message
        if extra_data is not None:
            existing.extra_data_json = json.dumps(extra_data)
        db.session.commit()
        return existing

    # Genuinely new alert — persist (email notification is sent in batch via
    # send_summary_emails(), not per-alert; email_notified_at stays NULL until then)
    alert = SystemAlert(
        type=type, level=level, title=title, message=message,
        entity_type=entity_type, entity_id=entity_id, source=source,
        extra_data_json=json.dumps(extra_data) if extra_data is not None else None,
    )
    db.session.add(alert)
    db.session.commit()
    logger.info("New alert created: #%d [%s] %s — pending email notification.",
                alert.id, alert.level, alert.type)

    return alert


def _auto_resolve(type: str, entity_type: str | None, entity_id: str | None) -> None:
    """Silently resolve an active alert when its condition no longer holds."""
    alert = SystemAlert.query.filter_by(
        type=type,
        entity_type=entity_type,
        entity_id=entity_id,
        is_resolved=False,
    ).first()
    if alert:
        alert.is_resolved = True
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = "system"
        db.session.commit()


# ── Single-entity helpers (shared by bulk and targeted checks) ────────────────

def _check_single_user_quota(user: OverleafUser) -> None:
    pct = user.quota_percent
    if pct is None:
        return
    uid   = str(user.id)
    label = user.email or user.overleaf_id

    warn_pct     = _threshold("alert.quota_warning_pct",  _QUOTA_WARNING_PCT_DEFAULT)
    exceeded_pct = _threshold("alert.quota_exceeded_pct", _QUOTA_EXCEEDED_PCT_DEFAULT)

    if pct >= exceeded_pct:
        _upsert(
            type="quota_exceeded", level="danger",
            title="Usuario con cuota excedida",
            message=f"El usuario {label} ha superado su cuota asignada ({pct:.1f}%).",
            entity_type="user", entity_id=uid, source="quota_checker",
            extra_data={"quota_percent": pct, "email": user.email,
                        "max_quota_bytes": user.max_quota_bytes},
        )
        _auto_resolve("quota_warning", "user", uid)

    elif pct >= warn_pct:
        _upsert(
            type="quota_warning", level="warning",
            title="Usuario cerca del límite de cuota",
            message=f"El usuario {label} ha utilizado el {pct:.1f}% de su cuota.",
            entity_type="user", entity_id=uid, source="quota_checker",
            extra_data={"quota_percent": pct, "email": user.email,
                        "max_quota_bytes": user.max_quota_bytes},
        )
        _auto_resolve("quota_exceeded", "user", uid)

    else:
        _auto_resolve("quota_warning",  "user", uid)
        _auto_resolve("quota_exceeded", "user", uid)


def _check_single_user_project_limit(user: OverleafUser) -> None:
    role = user.role
    if role is None or role.max_projects is None:
        _auto_resolve("project_limit_exceeded", "user", str(user.id))
        _auto_resolve("project_limit_warning",  "user", str(user.id))
        return

    count = user.projects_owned.count()
    uid   = str(user.id)
    label = user.email or user.overleaf_id
    limit = role.max_projects

    if count > limit:
        excess = count - limit
        level  = "critical" if excess > 10 else ("danger" if excess > 5 else "warning")
        _upsert(
            type="project_limit_exceeded", level=level,
            title="Límite de proyectos superado",
            message=(
                f"El usuario {label} tiene {count} proyectos como propietario, "
                f"superando el límite de {limit} del rol '{role.name}'."
            ),
            entity_type="user", entity_id=uid, source="quota_checker",
            extra_data={"project_count": count, "max_projects": limit, "email": user.email},
        )
        _auto_resolve("project_limit_warning", "user", uid)

    elif limit >= 2 and count >= limit * 0.8:
        _upsert(
            type="project_limit_warning", level="warning",
            title="Cerca del límite de proyectos",
            message=(
                f"El usuario {label} tiene {count} proyectos como propietario, "
                f"cerca del límite de {limit} del rol '{role.name}'."
            ),
            entity_type="user", entity_id=uid, source="quota_checker",
            extra_data={"project_count": count, "max_projects": limit, "email": user.email},
        )
        _auto_resolve("project_limit_exceeded", "user", uid)

    else:
        _auto_resolve("project_limit_exceeded", "user", uid)
        _auto_resolve("project_limit_warning",  "user", uid)


# ── Targeted check functions (event-driven) ───────────────────────────────────

def check_user_quota(user_id: int) -> None:
    user = db.session.get(OverleafUser, user_id)
    if user is None:
        return
    if user.max_quota_bytes is None:
        _auto_resolve("quota_warning",  "user", str(user_id))
        _auto_resolve("quota_exceeded", "user", str(user_id))
        return
    _check_single_user_quota(user)


def check_user_project_limit(user_id: int) -> None:
    user = db.session.get(OverleafUser, user_id)
    if user is None:
        return
    _check_single_user_project_limit(user)


def check_role_users(role_id: int) -> None:
    from app.model.entities.role import Role
    role = db.session.get(Role, role_id)
    if role is None:
        return
    for user in role.users.all():
        _check_single_user_quota(user)
        _check_single_user_project_limit(user)


def check_last_sync() -> None:
    generate_sync_alerts()


def check_all_quotas() -> None:
    generate_quota_alerts()


def check_all_project_limits() -> None:
    generate_project_limit_alerts()


def check_repeated_errors() -> None:
    generate_audit_alerts()



# ── Bulk generators ───────────────────────────────────────────────────────────

def generate_quota_alerts() -> None:
    users = OverleafUser.query.filter(OverleafUser.max_quota_bytes.isnot(None)).all()
    for user in users:
        _check_single_user_quota(user)


def generate_project_limit_alerts() -> None:
    users = OverleafUser.query.filter(OverleafUser.role_id.isnot(None)).all()
    for user in users:
        _check_single_user_project_limit(user)


def generate_sync_alerts() -> None:
    last_run = SyncRun.query.order_by(SyncRun.started_at.desc()).first()
    if last_run is None:
        return

    entity_type = "sync_run"
    entity_id   = "latest"

    if last_run.status in ("error", "failed"):
        recent_failed = (
            SyncRun.query
            .filter(SyncRun.status.in_(["error", "failed"]))
            .order_by(SyncRun.started_at.desc())
            .limit(3)
            .count()
        )
        level     = "critical" if recent_failed >= 3 else "danger"
        msg_extra = f" Mensaje: {last_run.message}" if last_run.message else ""
        _upsert(
            type="sync_failed", level=level,
            title="Fallo de sincronización",
            message=f"La última sincronización (#{last_run.id}) finalizó con errores.{msg_extra}",
            entity_type=entity_type, entity_id=entity_id, source="sync_checker",
            extra_data={"sync_run_id": last_run.id, "status": last_run.status},
        )
    else:
        _auto_resolve("sync_failed", entity_type, entity_id)


def generate_audit_alerts() -> None:
    hours  = int(_threshold("alert.repeated_errors_hrs", _REPEATED_ERRORS_HRS_DEFAULT))
    n      = int(_threshold("alert.repeated_errors_n",   _REPEATED_ERRORS_N_DEFAULT))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    count  = (
        AuditLog.query
        .filter(AuditLog.level == "error", AuditLog.created_at >= cutoff)
        .count()
    )
    entity_type = "audit_log"
    entity_id   = "repeated_errors"

    if count >= n:
        level = "danger" if count >= n * 3 else "warning"
        _upsert(
            type="repeated_errors", level=level,
            title="Errores repetidos detectados",
            message=f"Se han registrado {count} errores en las últimas {hours} horas.",
            entity_type=entity_type, entity_id=entity_id, source="audit_checker",
            extra_data={"error_count": count, "hours": hours},
        )
    else:
        _auto_resolve("repeated_errors", entity_type, entity_id)




# ── Orchestrator ──────────────────────────────────────────────────────────────

def recalculate_alerts(actor: str = "system") -> None:
    """Full recalculation — for the manual button and scheduled tasks only."""
    try:
        generate_quota_alerts()
        generate_project_limit_alerts()
        generate_sync_alerts()
        generate_audit_alerts()
    except Exception as exc:
        logger.error("Error during alert recalculation: %s", exc)

    log_action(
        action="alerts_recalculate", actor=actor,
        detail="Recálculo de alertas ejecutado.", level="info",
    )


# ── Notification preferences (service-layer wrappers) ─────────────────────────

def get_alert_by_id(alert_id: int) -> SystemAlert | None:
    """Fetch a single alert by primary key."""
    return db.session.get(SystemAlert, alert_id)


def get_or_create_notif_prefs(admin_id: int):
    """Return the admin's notification preferences, creating defaults if absent."""
    from app.model.entities.admin_notification_pref import AdminNotificationPref
    pref = AdminNotificationPref.query.filter_by(admin_id=admin_id).first()
    if pref is None:
        pref = AdminNotificationPref(admin_id=admin_id)
        db.session.add(pref)
        db.session.commit()
    return pref


def update_notif_prefs(admin_id: int, data: dict):
    """Update the admin's notification preferences. Creates defaults if absent."""
    from app.model.entities.admin_notification_pref import AdminNotificationPref
    pref = AdminNotificationPref.query.filter_by(admin_id=admin_id).first()
    if pref is None:
        pref = AdminNotificationPref(admin_id=admin_id)
        db.session.add(pref)
    pref.update_from_dict(data)
    db.session.commit()
    return pref
