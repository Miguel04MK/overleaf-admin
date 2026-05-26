"""
SyncRunner — orchestrates the ETL pipeline with configurable scope.

Soporta los siguientes sync_type:
  - full           Extrae y carga usuarios + proyectos + memberships (todo)
  - users          Solo usuarios
  - projects       Solo proyectos (+ memberships; el user_map se construye en DB)
  - resync_total   Como `full` pero hace explícito el commit por etapas y se
                   marca semánticamente como "revisión completa"
  - scheduled      Igual que `full` por defecto, pero el triggered_by es "scheduled"

Punto de entrada único: run_sync(app, sync_type=..., triggered_by=..., triggered_by_user=...)
"""
import logging
import threading
from datetime import datetime, timezone

from flask import Flask

from app.config.extensions import db
from app.model.entities.sync_run import SyncRun, SYNC_TYPES
from app.model.services.admin import admin_service as audit_service
from app.etl.extractors.adapter import make_adapter
from app.etl.extractors.extractor import OverleafExtractor
from app.etl.loaders.loader import OverleafLoader

logger = logging.getLogger(__name__)

# Lock global: sólo una sync corriendo al mismo tiempo dentro del proceso.
_SYNC_LOCK = threading.Lock()


def _fmt_delta(delta: int | None) -> str:
    if delta is None:
        return "?"
    if delta > 0:
        return f"+{delta}"
    return str(delta)


def is_sync_running() -> bool:
    """True si actualmente hay una SyncRun con status='running'.

    Se basa en DB (más fiable que el lock en proceso, que se pierde si reinicias).
    """
    return SyncRun.query.filter_by(status="running").first() is not None


def run_sync(
    app: Flask,
    *,
    sync_type: str = "full",
    triggered_by: str = "manual",
    triggered_by_user: str | None = None,
) -> SyncRun:
    """Ejecuta una sincronización con el alcance indicado.

    Se debe llamar idealmente desde un hilo de fondo. Es seguro re-ejecutar
    (idempotente): los upserts trabajan por `overleaf_id`.
    """
    if sync_type not in SYNC_TYPES:
        logger.warning("sync_type desconocido '%s', se usa 'full'.", sync_type)
        sync_type = "full"

    with app.app_context():
        # Bloqueo global: si ya hay una sync corriendo, no la duplicamos.
        if not _SYNC_LOCK.acquire(blocking=False):
            logger.info("Otra sync ya está en marcha en este proceso — abortando.")
            audit_service.log_action(
                action="sync_skip",
                actor=triggered_by_user or "system",
                detail="Sincronización solicitada con otra en curso (ignorada).",
                level="warning",
            )
            # Devolvemos una SyncRun fantasma sin persistir para no romper callers.
            placeholder = SyncRun(
                status="error", sync_type=sync_type,
                triggered_by=triggered_by, triggered_by_user=triggered_by_user,
                message="Ya hay una sincronización en curso.",
            )
            return placeholder

        try:
            return _do_sync(app, sync_type, triggered_by, triggered_by_user)
        finally:
            _SYNC_LOCK.release()


def _do_sync(
    app: Flask, sync_type: str, triggered_by: str, triggered_by_user: str | None,
) -> SyncRun:
    sync_run = SyncRun(
        sync_type=sync_type,
        triggered_by=triggered_by,
        triggered_by_user=triggered_by_user,
    )
    db.session.add(sync_run)
    db.session.commit()
    logger.info("SyncRun #%d started (type=%s, triggered_by=%s)",
                sync_run.id, sync_type, triggered_by)

    audit_service.log_action(
        action="sync_start",
        actor=triggered_by_user or "system",
        detail=f"Sincronización iniciada (tipo: {sync_type}, modo: {triggered_by})",
        level="info",
    )

    adapter = make_adapter(app)

    # Referencia para los deltas: la última sync correcta del MISMO tipo.
    prev = (
        SyncRun.query
        .filter(SyncRun.id != sync_run.id,
                SyncRun.status == "success",
                SyncRun.sync_type.in_([sync_type, "full", "resync_total"]))
        .order_by(SyncRun.started_at.desc())
        .first()
    )
    prev_users_found = prev.users_found if prev else None
    prev_projects_found = prev.projects_found if prev else None

    try:
        adapter.connect()
        with adapter.get_db() as mongo_db:
            extractor = OverleafExtractor(mongo_db)
            loader = OverleafLoader()

            # ── USUARIOS ─────────────────────────────────────────────────────
            if sync_type in ("full", "users", "resync_total", "scheduled"):
                raw_users = extractor.extract_users()
                u_found, u_synced, u_created, u_updated = loader.upsert_users(raw_users)
                sync_run.users_found    = u_found
                sync_run.users_synced   = u_synced
                sync_run.users_created  = u_created
                sync_run.users_updated  = u_updated
                db.session.flush()
            else:
                # Para sync_type='projects' no tocamos usuarios — pero sí necesitamos
                # el mapeo (overleaf_id → internal id) que ya tengamos en DB.
                pass

            user_map = loader.build_user_map()

            # ── PROYECTOS ────────────────────────────────────────────────────
            if sync_type in ("full", "projects", "resync_total", "scheduled"):
                raw_projects = extractor.extract_projects()

                # Construir membresías mientras tengamos los raw_projects en mano
                memberships_data = []
                for raw_proj in raw_projects:
                    members = []
                    for oid in raw_proj.get("collaborator_overleaf_ids", []):
                        if oid in user_map:
                            members.append({"overleaf_user_id": oid, "role": "collaborator"})
                    for oid in raw_proj.get("readonly_overleaf_ids", []):
                        if oid in user_map:
                            members.append({"overleaf_user_id": oid, "role": "read_only"})
                    memberships_data.append((raw_proj["overleaf_id"], members))

                p_found, p_synced, p_created, p_updated, m_synced = loader.upsert_projects(
                    raw_projects, memberships_data, user_map,
                    sync_run_id=sync_run.id,
                )
                sync_run.projects_found    = p_found
                sync_run.projects_synced   = p_synced
                sync_run.projects_created  = p_created
                sync_run.projects_updated  = p_updated
                sync_run.members_synced    = m_synced
                db.session.commit()

        adapter.disconnect()

        # Deltas vs. sync anterior
        if prev_users_found is not None and (sync_type in ("full", "users", "resync_total", "scheduled")):
            sync_run.users_delta = sync_run.users_found - prev_users_found
        if prev_projects_found is not None and (sync_type in ("full", "projects", "resync_total", "scheduled")):
            sync_run.projects_delta = sync_run.projects_found - prev_projects_found

        # Mensaje final compuesto según el alcance
        parts = []
        if sync_type in ("full", "users", "resync_total", "scheduled"):
            parts.append(
                f"{sync_run.users_synced}/{sync_run.users_found} usuarios "
                f"({_fmt_delta(sync_run.users_delta)})"
            )
        if sync_type in ("full", "projects", "resync_total", "scheduled"):
            parts.append(
                f"{sync_run.projects_synced}/{sync_run.projects_found} proyectos "
                f"({_fmt_delta(sync_run.projects_delta)})"
            )
        message = f"Sincronización completada: {', '.join(parts)}."

        sync_run.mark_finished(status="success", message=message)
        db.session.commit()

        audit_service.log_action(
            action="sync_ok",
            actor=triggered_by_user or "system",
            detail=sync_run.message,
            level="info",
        )
        logger.info("SyncRun #%d finished successfully (type=%s).",
                    sync_run.id, sync_type)

        try:
            from app.model.services import alerts_service
            alerts_service.check_last_sync()
            if sync_type in ("full", "users", "resync_total", "scheduled"):
                alerts_service.check_all_quotas()
            if sync_type in ("full", "projects", "resync_total", "scheduled"):
                alerts_service.check_all_project_limits()
            alerts_service.check_repeated_errors()
        except Exception as alert_exc:
            logger.warning("Alert checks after sync failed: %s", alert_exc)

    except Exception as exc:
        db.session.rollback()
        error_msg = f"Error de sincronización: {exc}"
        logger.error("SyncRun #%d failed: %s", sync_run.id, exc, exc_info=True)

        try:
            sync_run.mark_finished(
                status="error",
                message=error_msg,
                errors_count=(sync_run.errors_count or 0) + 1,
                error_detail=repr(exc),
            )
            db.session.commit()
        except Exception:
            db.session.rollback()

        audit_service.log_action(
            action="sync_error",
            actor=triggered_by_user or "system",
            detail=error_msg,
            level="error",
        )

        try:
            from app.model.services import alerts_service
            alerts_service.check_last_sync()
            alerts_service.check_repeated_errors()
        except Exception as alert_exc:
            logger.warning("Alert checks after sync error failed: %s", alert_exc)

    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass

    return sync_run
