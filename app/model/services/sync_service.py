"""
SyncService — query layer + settings layer for the /sincronizacion/ module.

Exposes:
  - get_recent_syncs(limit)           — most recent (dashboard widget compatible)
  - get_syncs_paginated(...)          — paginated history with filters
  - get_sync_by_id(id)                — detail
  - get_project_logs_for_sync(id)     — per-project ProjectSyncLog entries
  - get_sync_status()                 — quick view (running / last / next)
  - is_sync_running()                 — bool (re-exported from runner)
  - get_sync_settings()               — read scheduled-sync config from AppSetting
  - update_sync_settings(data, actor) — write scheduled-sync config
  - mark_scheduled_run(at)            — bookkeeping for the (external) scheduler

The actual ETL entry point is run_sync() from app.etl.runners.runner; it's
re-exported here for backward compatibility.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import desc

from app.config.extensions import db
from app.model.entities.sync_run import SyncRun, SYNC_TYPES, SYNC_TYPE_LABELS  # noqa: F401
from app.model.entities.sync_schedule import (
    SyncSchedule, INTERVAL_PRESETS, SYNC_TYPE_CHOICES, MIN_INTERVAL_MINUTES,
)
from app.model.entities.project_sync_log import ProjectSyncLog
from app.model.entities.app_setting import AppSetting
from app.etl.runners.runner import run_sync, is_sync_running  # noqa: F401

logger = logging.getLogger(__name__)


# ── Lecturas básicas ──────────────────────────────────────────────────────────

def get_recent_syncs(limit: int = 20) -> list[SyncRun]:
    """Most recent SyncRuns ordered by start time desc."""
    return (
        SyncRun.query
        .order_by(desc(SyncRun.started_at))
        .limit(max(1, limit))
        .all()
    )


def get_syncs_paginated(
    *,
    page: int = 1,
    per_page: int = 15,
    status: str | None = None,
    sync_type: str | None = None,
    triggered_by: str | None = None,
    triggered_by_user: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Paginated history with filters. Devuelve un objeto Pagination."""
    q = SyncRun.query.order_by(desc(SyncRun.started_at))

    if status:
        q = q.filter(SyncRun.status == status)
    if sync_type:
        q = q.filter(SyncRun.sync_type == sync_type)
    if triggered_by:
        q = q.filter(SyncRun.triggered_by == triggered_by)
    if triggered_by_user:
        q = q.filter(SyncRun.triggered_by_user == triggered_by_user)

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df:
        q = q.filter(SyncRun.started_at >= df)
    if dt:
        q = q.filter(SyncRun.started_at < dt + timedelta(days=1))

    return q.paginate(
        page=max(1, page),
        per_page=max(1, min(per_page, 100)),
        error_out=False,
    )


def get_sync_by_id(sync_id: int) -> SyncRun | None:
    return db.session.get(SyncRun, sync_id)


def get_project_logs_for_sync(sync_id: int, limit: int = 50) -> list:
    """ProjectSyncLog asociados a un SyncRun, más recientes primero."""
    return (
        ProjectSyncLog.query
        .filter_by(sync_run_id=sync_id)
        .order_by(desc(ProjectSyncLog.synced_at))
        .limit(max(1, min(limit, 200)))
        .all()
    )


# ── Estado vivo ──────────────────────────────────────────────────────────────

def _abbr_run(s: SyncRun | None) -> dict | None:
    if not s:
        return None
    return {
        "id":                s.id,
        "status":            s.status,
        "sync_type":         s.sync_type,
        "sync_type_label":   s.sync_type_label,
        "triggered_by":      s.triggered_by,
        "triggered_by_user": s.triggered_by_user,
        "started_at":        s.started_at.isoformat() if s.started_at else None,
        "finished_at":       s.finished_at.isoformat() if s.finished_at else None,
        "duration_seconds":  s.duration_seconds,
        "users_synced":      s.users_synced,
        "projects_synced":   s.projects_synced,
        "errors_count":      s.errors_count,
        "message":           s.message,
    }


def get_sync_status() -> dict:
    """Resumen ligero para el polling AJAX y los chips de cabecera.

    Estructura:
      {
        "running":      bool,
        "running_run":  {...} | None,
        "last":         {...} | None,
        "next_run_at":  ISO | None,
        "totals_24h":   {"success": N, "error": N, "running": N},
      }
    """
    running = (
        SyncRun.query
        .filter_by(status="running")
        .order_by(desc(SyncRun.started_at))
        .first()
    )
    last = (
        SyncRun.query
        .filter(SyncRun.status.in_(["success", "error", "partial"]))
        .order_by(desc(SyncRun.started_at))
        .first()
    )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    totals_24h = {
        "success": SyncRun.query.filter(SyncRun.status == "success", SyncRun.started_at >= cutoff).count(),
        "error":   SyncRun.query.filter(SyncRun.status == "error",   SyncRun.started_at >= cutoff).count(),
        "running": SyncRun.query.filter(SyncRun.status == "running").count(),
    }

    return {
        "running":     running is not None,
        "running_run": _abbr_run(running),
        "last":        _abbr_run(last),
        "next_run_at": _earliest_next_run(),
        "totals_24h":  totals_24h,
    }


# ── Settings (sync periódica) ─────────────────────────────────────────────────

# Claves usadas en AppSetting
_KEY_ENABLED  = "sync.scheduled.enabled"
_KEY_INTERVAL = "sync.scheduled.interval_minutes"
_KEY_TYPE     = "sync.scheduled.type"
_KEY_LAST_RUN = "sync.scheduled.last_run_at"
_KEY_NEXT_RUN = "sync.scheduled.next_run_at"

ALLOWED_INTERVALS = [15, 30, 60, 360, 1440]   # 15m, 30m, 1h, 6h, 24h
SCHEDULED_TYPES   = ["full", "users", "projects"]


def _get_setting(key: str, default: str = "") -> str:
    s = db.session.get(AppSetting, key)
    return s.value if s else default


def _set_setting(key: str, value: str, actor: str) -> None:
    s = db.session.get(AppSetting, key)
    if s is None:
        s = AppSetting(key=key, value=str(value), updated_by=actor)
        db.session.add(s)
    else:
        s.value      = str(value)
        s.updated_by = actor
        s.updated_at = datetime.now(timezone.utc)


def get_sync_settings() -> dict:
    """Configuración persistida de la sync periódica."""
    enabled      = _get_setting(_KEY_ENABLED, "false").lower() == "true"
    try:
        interval_min = int(_get_setting(_KEY_INTERVAL, "60") or "60")
    except ValueError:
        interval_min = 60
    sync_type    = _get_setting(_KEY_TYPE, "full") or "full"
    last_run_iso = _get_setting(_KEY_LAST_RUN, "") or None
    next_run_iso = _get_setting(_KEY_NEXT_RUN, "") or None

    if sync_type not in SCHEDULED_TYPES:
        sync_type = "full"
    if interval_min < 1:
        interval_min = 60

    return {
        "enabled":          enabled,
        "interval_minutes": interval_min,
        "sync_type":        sync_type,
        "last_run_at":      last_run_iso,
        "next_run_at":      next_run_iso,
    }


def update_sync_settings(data: dict, *, actor: str = "system") -> tuple[bool, str]:
    """Persiste la configuración y recalcula `next_run_at`."""
    enabled = bool(data.get("enabled"))
    try:
        interval_min = int(data.get("interval_minutes", 60))
        if interval_min < 1:
            return False, "El intervalo debe ser al menos 1 minuto."
    except (TypeError, ValueError):
        return False, "Intervalo no válido."

    sync_type = data.get("sync_type", "full")
    if sync_type not in SCHEDULED_TYPES:
        return False, f"Tipo de sync no válido (permitidos: {', '.join(SCHEDULED_TYPES)})."

    _set_setting(_KEY_ENABLED,  "true" if enabled else "false", actor)
    _set_setting(_KEY_INTERVAL, str(interval_min),               actor)
    _set_setting(_KEY_TYPE,     sync_type,                       actor)

    if enabled:
        next_run = datetime.now(timezone.utc) + timedelta(minutes=interval_min)
        _set_setting(_KEY_NEXT_RUN, next_run.isoformat(), actor)
    else:
        _set_setting(_KEY_NEXT_RUN, "", actor)

    db.session.commit()

    try:
        from app.model.services.admin import admin_service as audit_service
        audit_service.log_action(
            action="sync_settings_update",
            actor=actor,
            detail=(
                f"Sync periódica: enabled={enabled}, intervalo={interval_min}min, "
                f"tipo={sync_type}"
            ),
            level="info",
        )
    except Exception as exc:
        logger.warning("AuditLog de sync_settings_update falló: %s", exc)

    return True, "Configuración guardada correctamente."


def mark_scheduled_run(at: datetime | None = None) -> None:
    """Apuntar la hora de la última ejecución programada y recalcular la próxima."""
    at = at or datetime.now(timezone.utc)
    _set_setting(_KEY_LAST_RUN, at.isoformat(), actor="scheduler")
    settings = get_sync_settings()
    next_run = at + timedelta(minutes=settings["interval_minutes"])
    _set_setting(_KEY_NEXT_RUN, next_run.isoformat(), actor="scheduler")
    db.session.commit()


def get_distinct_actors() -> list[str]:
    """Usernames distintos que han lanzado sincronizaciones manuales."""
    rows = (
        db.session.query(SyncRun.triggered_by_user)
        .filter(SyncRun.triggered_by_user.isnot(None))
        .distinct()
        .order_by(SyncRun.triggered_by_user.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


# ── Programaciones múltiples (SyncSchedule) ─────────────────────────────────

def list_schedules() -> list[SyncSchedule]:
    """Todas las programaciones, las activas primero."""
    return (
        SyncSchedule.query
        .order_by(SyncSchedule.enabled.desc(), SyncSchedule.created_at.asc())
        .all()
    )


def get_schedule(schedule_id: int) -> SyncSchedule | None:
    return db.session.get(SyncSchedule, schedule_id)


def _earliest_next_run() -> str | None:
    """Próxima ejecución más cercana de entre todas las schedules activas."""
    rows = (
        SyncSchedule.query
        .filter(SyncSchedule.enabled.is_(True), SyncSchedule.next_run_at.isnot(None))
        .order_by(SyncSchedule.next_run_at.asc())
        .limit(1)
        .all()
    )
    return rows[0].next_run_at.isoformat() if rows else None


def _compute_next_run(
    interval_minutes: int,
    scheduled_hour: int | None,
    from_time: datetime,
) -> datetime:
    """Calcula next_run_at respetando scheduled_hour si está definido.

    - Sin hora fija: next = from_time + interval.
    - Con hora fija e intervalo < 1 día (12 h): hay dos disparos diarios
      en scheduled_hour y scheduled_hour+12; se elige el primero >= base.
    - Con hora fija e intervalo >= 1 día: se snap al scheduled_hour del
      día en que cae base, avanzando un día si ya pasó esa hora.
    """
    base = from_time + timedelta(minutes=interval_minutes)
    if scheduled_hour is None:
        return base

    h = scheduled_hour % 24

    if interval_minutes < 1440:
        # Intervalo sub-diario (12 h): slots en h y h+12
        slots = sorted([h, (h + 12) % 24])
        for offset_days in range(3):
            ref = (base + timedelta(days=offset_days)).replace(
                minute=0, second=0, microsecond=0
            )
            for slot in slots:
                candidate = ref.replace(hour=slot)
                if candidate >= base:
                    return candidate
    else:
        # Intervalo >= 1 día: un disparo al día a scheduled_hour
        t = base.replace(hour=h, minute=0, second=0, microsecond=0)
        if t < base:
            t += timedelta(days=1)
        return t

    return base  # fallback


def create_schedule(
    *,
    name: str,
    sync_type: str,
    interval_minutes: int,
    scheduled_hour: int | None = None,
    enabled: bool = True,
    actor: str = "system",
) -> tuple[bool, str, SyncSchedule | None]:
    """Crea una nueva programación. Devuelve (ok, msg, schedule|None)."""
    n = (name or "").strip()
    if not n:
        return False, "El nombre de la programación es obligatorio.", None
    if len(n) > 128:
        return False, "El nombre no puede tener más de 128 caracteres.", None
    if sync_type not in SYNC_TYPE_CHOICES:
        return False, f"Tipo no válido (permitidos: {', '.join(SYNC_TYPE_CHOICES)}).", None
    try:
        interval_minutes = int(interval_minutes)
    except (TypeError, ValueError):
        return False, "Intervalo no válido.", None
    if interval_minutes < MIN_INTERVAL_MINUTES:
        return False, f"El intervalo mínimo es de {MIN_INTERVAL_MINUTES // 60} horas.", None

    parsed_hour: int | None = None
    if scheduled_hour is not None:
        try:
            parsed_hour = int(scheduled_hour)
            if not (0 <= parsed_hour <= 23):
                return False, "La hora programada debe estar entre 0 y 23.", None
        except (TypeError, ValueError):
            return False, "Hora programada no válida.", None

    sch = SyncSchedule(
        name=n,
        sync_type=sync_type,
        interval_minutes=interval_minutes,
        scheduled_hour=parsed_hour,
        enabled=bool(enabled),
        created_by=actor,
    )
    if enabled:
        sch.next_run_at = _compute_next_run(interval_minutes, parsed_hour, datetime.now(timezone.utc))
    db.session.add(sch)
    db.session.commit()

    _audit("sync_schedule_create",
           actor, f"Nueva programación «{n}»: {sync_type} cada {interval_minutes} min.")
    return True, f"Programación «{n}» creada.", sch


def delete_schedule(schedule_id: int, *, actor: str = "system") -> tuple[bool, str]:
    sch = db.session.get(SyncSchedule, schedule_id)
    if not sch:
        return False, "Programación no encontrada."
    name = sch.name
    db.session.delete(sch)
    db.session.commit()
    _audit("sync_schedule_delete", actor, f"Programación «{name}» eliminada.")
    return True, f"Programación «{name}» eliminada."


def toggle_schedule(schedule_id: int, *, actor: str = "system") -> tuple[bool, str]:
    sch = db.session.get(SyncSchedule, schedule_id)
    if not sch:
        return False, "Programación no encontrada."
    sch.enabled = not sch.enabled
    if sch.enabled:
        sch.next_run_at = _compute_next_run(
            sch.interval_minutes, sch.scheduled_hour, datetime.now(timezone.utc)
        )
    else:
        sch.next_run_at = None
    db.session.commit()
    state = "activada" if sch.enabled else "desactivada"
    _audit("sync_schedule_toggle", actor, f"Programación «{sch.name}» {state}.")
    return True, f"Programación «{sch.name}» {state}."


def mark_schedule_run(schedule_id: int, *, at: datetime | None = None) -> None:
    """Marca una schedule como ejecutada y recalcula `next_run_at`."""
    sch = db.session.get(SyncSchedule, schedule_id)
    if not sch:
        return
    at = at or datetime.now(timezone.utc)
    sch.last_run_at = at
    sch.next_run_at = _compute_next_run(sch.interval_minutes, sch.scheduled_hour, at)
    db.session.commit()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _audit(action: str, actor: str, detail: str, level: str = "info") -> None:
    """Atajo para no llenar de try/except."""
    try:
        from app.model.services.admin import admin_service as audit_service
        audit_service.log_action(action=action, actor=actor, detail=detail, level=level)
    except Exception as exc:
        logger.warning("AuditLog %s falló: %s", action, exc)


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
