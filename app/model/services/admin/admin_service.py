"""
AdminService — audit logging.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_

from app.config.extensions import db
from app.model.entities.audit_log import AuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit categorization
# ---------------------------------------------------------------------------

# Categorías mostradas en la pantalla /auditoria/. Cada una agrupa varias
# `action` del AuditLog. El orden aquí define el orden visual de los chips.
CATEGORIES: dict[str, dict] = {
    "auth": {
        "label": "Acceso",
        "icon":  "bi-box-arrow-in-right",
        "color": "primary",
        "actions": ["login", "logout"],
    },
    "admin": {
        "label": "Administración",
        "icon":  "bi-shield-lock",
        "color": "info",
        "actions": [
            "admin_create", "admin_enable", "admin_disable", "admin_password_reset",
            "password_change", "notification_preferences_update",
            "alert_resolve", "alert_resolve_bulk",
            "alert_mark_read", "alert_mark_read_bulk",
            "alert_reopen", "alert_reopen_bulk",
            "alerts_recalculate", "thresholds_update",
            "email_summary_sent", "export",
            "role_create", "role_delete",
            "sync_settings_update",
            "sync_schedule_create", "sync_schedule_delete", "sync_schedule_toggle",
        ],
    },
    "quota": {
        "label": "Cuotas",
        "icon":  "bi-hdd",
        "color": "success",
        "actions": ["quota_change"],
    },
    "sync": {
        "label": "Sincronización",
        "icon":  "bi-arrow-repeat",
        "color": "warning",
        "actions": [
            "sync_start", "sync_ok", "sync_error", "sync_trigger",
            "sync_manual_full", "sync_manual_users", "sync_manual_projects",
            "sync_manual_resync_total", "sync_scheduled_run", "sync_skip",
        ],
    },
    "role": {
        "label": "Cambios de rol",
        "icon":  "bi-person-badge",
        "color": "dark",
        "actions": ["role_assigned", "role_changed", "role_removed"],
    },
}

# Inverso: action → category key (para clasificar rápido sin escanear el dict).
_ACTION_TO_CATEGORY: dict[str, str] = {
    a: cat for cat, data in CATEGORIES.items() for a in data["actions"]
}


def category_for_action(action: str) -> str | None:
    """Devuelve el key de la categoría para una acción, o None si no encaja."""
    return _ACTION_TO_CATEGORY.get(action)


# Etiquetas legibles por acción.
ACTION_LABELS: dict[str, str] = {
    "login":                          "Inicio de sesión",
    "logout":                         "Cierre de sesión",
    "password_change":                "Cambio de contraseña",
    "notification_preferences_update":"Preferencias de notificación",
    "admin_create":                   "Administrador creado",
    "admin_enable":                   "Administrador activado",
    "admin_disable":                  "Administrador desactivado",
    "admin_password_reset":           "Contraseña reseteada",
    "role_create":                    "Rol creado",
    "role_delete":                    "Rol eliminado",
    "role_assigned":                  "Rol asignado",
    "role_changed":                   "Rol cambiado",
    "role_removed":                   "Rol retirado",
    # Valores de RoleChangeLog.action (usados por los PDFs antiguos)
    "assigned":                       "Rol asignado",
    "changed":                        "Rol cambiado",
    "removed":                        "Rol retirado",
    "quota_change":                   "Cuota modificada",
    "sync_start":                     "Sincronización iniciada",
    "sync_ok":                        "Sincronización OK",
    "sync_error":                     "Sincronización con error",
    "sync_trigger":                   "Sincronización manual",
    "sync_manual_full":               "Sync manual (completa)",
    "sync_manual_users":              "Sync manual (solo usuarios)",
    "sync_manual_projects":           "Sync manual (solo proyectos)",
    "sync_manual_resync_total":       "Sync manual (resync total)",
    "sync_scheduled_run":             "Sync programada ejecutada",
    "sync_skip":                      "Sync omitida (otra en curso)",
    "sync_settings_update":           "Configuración de sync actualizada",
    "sync_schedule_create":           "Programación de sync creada",
    "sync_schedule_delete":           "Programación de sync eliminada",
    "sync_schedule_toggle":           "Programación de sync activada/desactivada",
    "alert_resolve":                  "Alerta resuelta",
    "alert_resolve_bulk":             "Alertas resueltas (lote)",
    "alert_mark_read":                "Alerta marcada leída",
    "alert_mark_read_bulk":           "Alertas marcadas leídas (lote)",
    "alert_reopen":                   "Alerta reabierta",
    "alert_reopen_bulk":              "Alertas reabiertas (lote)",
    "alerts_recalculate":             "Recálculo de alertas",
    "thresholds_update":              "Umbrales actualizados",
    "email_summary_sent":             "Resumen por email enviado",
    "export":                         "Exportación",
}


def label_for_action(action: str) -> str:
    """Traduce un AuditLog.action a una etiqueta legible."""
    return ACTION_LABELS.get(action, action.replace("_", " ").capitalize())


# ---------------------------------------------------------------------------
# Audit log functions
# ---------------------------------------------------------------------------

def log_action(
    action: str,
    actor: str = "system",
    detail: str | None = None,
    level: str = "info",
) -> None:
    """Write a single audit log entry. Silently swallows errors to avoid
    cascading failures when the audit log itself has a problem."""
    try:
        entry = AuditLog(
            actor=actor,
            action=action,
            detail=detail,
            level=level,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        logger.error("Failed to write audit log: %s", exc)
        db.session.rollback()


def get_recent_logs(limit: int = 200):
    return (
        AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    )


def get_paginated_logs(page: int = 1, per_page: int = 30):
    return AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )


def _parse_date(s: str | None):
    """Parse 'YYYY-MM-DD' a datetime UTC; None si vacío o inválido."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def get_filtered_logs(
    *,
    page: int = 1,
    per_page: int = 30,
    search: str | None = None,
    level: str | None = None,
    category: str | None = None,
    actor: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    last_24h: bool = False,
):
    """Devuelve una pagination de AuditLogs aplicando todos los filtros.

    - search:    texto libre, busca en `actor` y `detail` (ilike).
    - level:     'info' | 'warning' | 'error' | None
    - category:  clave de CATEGORIES (auth, admin, quota, sync, role) | None
    - actor:     match exacto contra `actor`.
    - date_from / date_to: 'YYYY-MM-DD' (incluyentes); también acepta None.
    - last_24h:  ignora date_from/to si True, fuerza created_at >= now-24h.
    """
    q = AuditLog.query

    if search:
        term = f"%{search.strip()}%"
        q = q.filter(or_(AuditLog.actor.ilike(term), AuditLog.detail.ilike(term)))

    if level in ("info", "warning", "error"):
        q = q.filter(AuditLog.level == level)

    if category and category in CATEGORIES:
        q = q.filter(AuditLog.action.in_(CATEGORIES[category]["actions"]))

    if actor:
        q = q.filter(AuditLog.actor == actor)

    if last_24h:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        q = q.filter(AuditLog.created_at >= cutoff)
    else:
        df = _parse_date(date_from)
        dt = _parse_date(date_to)
        if df:
            q = q.filter(AuditLog.created_at >= df)
        if dt:
            # date_to inclusivo: hasta el final del día
            q = q.filter(AuditLog.created_at < dt + timedelta(days=1))

    return q.order_by(AuditLog.created_at.desc()).paginate(
        page=max(1, page), per_page=max(1, min(per_page, 100)), error_out=False,
    )


def get_audit_summary() -> dict:
    """Devuelve los conteos para los chips superiores de /auditoria/.

    Estructura:
      {
        "total":      int,
        "last_24h":   int,
        "errors":     int,
        "by_category": {"auth": N, "admin": N, "quota": N, "sync": N, "role": N},
      }
    """
    total    = db.session.query(func.count(AuditLog.id)).scalar() or 0
    cutoff   = datetime.now(timezone.utc) - timedelta(hours=24)
    last_24h = db.session.query(func.count(AuditLog.id)).filter(
        AuditLog.created_at >= cutoff
    ).scalar() or 0
    errors   = db.session.query(func.count(AuditLog.id)).filter(
        AuditLog.level == "error"
    ).scalar() or 0

    by_category: dict[str, int] = {}
    for cat_key, cat_data in CATEGORIES.items():
        cnt = db.session.query(func.count(AuditLog.id)).filter(
            AuditLog.action.in_(cat_data["actions"])
        ).scalar() or 0
        by_category[cat_key] = int(cnt)

    return {
        "total":       int(total),
        "last_24h":    int(last_24h),
        "errors":      int(errors),
        "by_category": by_category,
    }


def get_distinct_actors() -> list[str]:
    """Lista de actores únicos para el dropdown del filtro."""
    rows = (
        db.session.query(AuditLog.actor)
        .distinct()
        .order_by(AuditLog.actor.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


