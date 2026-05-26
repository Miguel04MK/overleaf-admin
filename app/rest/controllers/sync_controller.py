"""Sync controller — /sincronizacion/.

Endpoints:
  - GET  /                          : pantalla principal (estado + acciones + historial)
  - POST /ejecutar                  : sync completa manual
  - POST /usuarios                  : sync parcial — usuarios
  - POST /proyectos                 : sync parcial — proyectos
  - POST /resync-total              : resincronización total
  - POST /configurar                : guardar configuración periódica
  - GET  /buscar                    : historial paginado (JSON)
  - GET  /<id>                      : detalle de una sync (JSON)
  - GET  /estado                    : estado actual (JSON, para polling)
"""
import logging
import threading

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    current_app, jsonify, abort,
)
from flask_login import login_required, current_user

from app.model.services import sync_service
from app.model.services.admin import admin_service as audit_service

logger = logging.getLogger(__name__)
sync_bp = Blueprint("sync", __name__, url_prefix="/sincronizacion")


# ── Helpers ──────────────────────────────────────────────────────────────────

# Mapa: tipo de sync (URL) → action del AuditLog para sincronizaciones manuales
_AUDIT_ACTION_BY_TYPE = {
    "full":         "sync_manual_full",
    "users":        "sync_manual_users",
    "projects":     "sync_manual_projects",
    "resync_total": "sync_manual_resync_total",
}


def _launch_background(sync_type: str) -> tuple[bool, str]:
    """Arranca una sync en background. Devuelve (ok, mensaje)."""
    if sync_service.is_sync_running():
        return False, "Ya hay una sincronización en curso."

    app   = current_app._get_current_object()
    actor = current_user.username

    audit_service.log_action(
        action=_AUDIT_ACTION_BY_TYPE.get(sync_type, "sync_trigger"),
        actor=actor,
        detail=f"Sincronización manual iniciada (tipo: {sync_type}).",
        level="info",
    )

    def _run():
        from app.etl.runners.runner import run_sync
        try:
            run_sync(app, sync_type=sync_type, triggered_by="manual", triggered_by_user=actor)
        except Exception as exc:
            logger.error("Error inesperado en hilo de sync: %s", exc, exc_info=True)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return True, (
        f"Sincronización «{sync_type}» iniciada en segundo plano. "
        "Esta pantalla se actualiza automáticamente."
    )


def _serialize_run(run) -> dict:
    """Serializa un SyncRun para los endpoints JSON."""
    return {
        "id":                  run.id,
        "started_at":          run.started_at.strftime("%d/%m/%Y %H:%M:%S") if run.started_at else None,
        "finished_at":         run.finished_at.strftime("%d/%m/%Y %H:%M:%S") if run.finished_at else None,
        "duration_seconds":    round(run.duration_seconds, 1) if run.duration_seconds is not None else None,
        "status":              run.status,
        "sync_type":           run.sync_type,
        "sync_type_label":     run.sync_type_label,
        "triggered_by":        run.triggered_by,
        "triggered_by_user":   run.triggered_by_user,
        "users_found":         run.users_found,
        "users_synced":        run.users_synced,
        "users_created":       run.users_created,
        "users_updated":       run.users_updated,
        "users_delta":         run.users_delta,
        "projects_found":      run.projects_found,
        "projects_synced":     run.projects_synced,
        "projects_created":    run.projects_created,
        "projects_updated":    run.projects_updated,
        "projects_delta":      run.projects_delta,
        "members_synced":      run.members_synced,
        "errors_count":        run.errors_count,
        "message":             run.message,
        "error_detail":        run.error_detail,
        "detail_url":          url_for("sync.sync_detail", sync_id=run.id),
    }


# ── Views ────────────────────────────────────────────────────────────────────

@sync_bp.route("/")
@login_required
def status():
    sync_status = sync_service.get_sync_status()
    schedules   = sync_service.list_schedules()
    pagination  = sync_service.get_syncs_paginated(page=1, per_page=15)
    actors      = sync_service.get_distinct_actors()
    from app.model.entities.sync_schedule import INTERVAL_PRESETS, SYNC_TYPE_CHOICES
    return render_template(
        "sync/status.html",
        active_page="sync",
        sync_status=sync_status,
        schedules=schedules,
        interval_presets=INTERVAL_PRESETS,
        sync_type_choices=SYNC_TYPE_CHOICES,
        pagination=pagination,
        actors=actors,
    )


@sync_bp.route("/ejecutar", methods=["POST"])
@login_required
def trigger():
    """Sincronización completa manual (compatibilidad con el endpoint antiguo)."""
    ok, msg = _launch_background("full")
    flash(msg, "info" if ok else "warning")
    return redirect(url_for("sync.status"))


@sync_bp.route("/usuarios", methods=["POST"])
@login_required
def trigger_users():
    ok, msg = _launch_background("users")
    flash(msg, "info" if ok else "warning")
    return redirect(url_for("sync.status"))


@sync_bp.route("/proyectos", methods=["POST"])
@login_required
def trigger_projects():
    ok, msg = _launch_background("projects")
    flash(msg, "info" if ok else "warning")
    return redirect(url_for("sync.status"))


@sync_bp.route("/resync-total", methods=["POST"])
@login_required
def trigger_resync_total():
    ok, msg = _launch_background("resync_total")
    flash(msg, "info" if ok else "warning")
    return redirect(url_for("sync.status"))


@sync_bp.route("/programadas/nueva", methods=["POST"])
@login_required
def create_schedule():
    """Añade una nueva programación de sync periódica."""
    raw_hour = request.form.get("scheduled_hour", "").strip()
    scheduled_hour = int(raw_hour) if raw_hour.isdigit() else None

    ok, msg, _ = sync_service.create_schedule(
        name=request.form.get("name", "").strip(),
        sync_type=request.form.get("sync_type", "full"),
        interval_minutes=request.form.get("interval_minutes", "1440"),
        scheduled_hour=scheduled_hour,
        enabled=request.form.get("enabled") in ("on", "true", "1", "y", "yes"),
        actor=current_user.username,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("sync.status"))


@sync_bp.route("/programadas/<int:schedule_id>/eliminar", methods=["POST"])
@login_required
def delete_schedule(schedule_id: int):
    ok, msg = sync_service.delete_schedule(schedule_id, actor=current_user.username)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("sync.status"))


@sync_bp.route("/programadas/<int:schedule_id>/toggle", methods=["POST"])
@login_required
def toggle_schedule(schedule_id: int):
    ok, msg = sync_service.toggle_schedule(schedule_id, actor=current_user.username)
    flash(msg, "success" if ok else "warning")
    return redirect(url_for("sync.status"))


# ── JSON endpoints ───────────────────────────────────────────────────────────

@sync_bp.route("/buscar")
@login_required
def search():
    """Historial paginado con filtros para refresco AJAX."""
    page     = max(1, request.args.get("page",     1,  type=int))
    per_page = max(1, request.args.get("per_page", 15, type=int))
    pagination = sync_service.get_syncs_paginated(
        page=page, per_page=per_page,
        status=request.args.get("status") or None,
        sync_type=request.args.get("sync_type") or None,
        triggered_by=request.args.get("triggered_by") or None,
        triggered_by_user=request.args.get("triggered_by_user") or None,
        date_from=request.args.get("date_from") or None,
        date_to=request.args.get("date_to") or None,
    )
    return jsonify({
        "total":    pagination.total,
        "page":     pagination.page,
        "pages":    pagination.pages,
        "per_page": pagination.per_page,
        "has_prev": pagination.has_prev,
        "has_next": pagination.has_next,
        "prev_num": pagination.prev_num,
        "next_num": pagination.next_num,
        "items":    [_serialize_run(r) for r in pagination.items],
    })


@sync_bp.route("/estado")
@login_required
def state_json():
    """Estado actual ligero — para polling desde la pantalla."""
    return jsonify(sync_service.get_sync_status())


@sync_bp.route("/<int:sync_id>")
@login_required
def sync_detail(sync_id: int):
    """Detalle JSON de una sync concreta + sus ProjectSyncLog."""
    run = sync_service.get_sync_by_id(sync_id)
    if not run:
        abort(404)
    logs = sync_service.get_project_logs_for_sync(sync_id, limit=50)

    return jsonify({
        "run":  _serialize_run(run),
        "project_logs": [
            {
                "synced_at":    l.synced_at.strftime("%d/%m/%Y %H:%M:%S") if l.synced_at else None,
                "event":        l.event,
                "size_bytes":   l.size_bytes,
                "member_count": l.member_count,
                "project_id":   l.project_id,
                "project_name": l.project.name if l.project else None,
            }
            for l in logs
        ],
    })
