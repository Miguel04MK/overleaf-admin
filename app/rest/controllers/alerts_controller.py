"""Alerts controller — list, filter and manage SystemAlerts."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app.model.services import alerts_service

alerts_bp = Blueprint("alerts", __name__, url_prefix="/alertas")


def _filter_args() -> dict:
    return {
        "status":    request.args.get("status", "all"),
        "level":     request.args.get("level")     or None,
        "type_":     request.args.get("type")      or None,
        "unread":    request.args.get("unread")    or None,
        "q":         request.args.get("q", "").strip() or None,
        "date_from": request.args.get("date_from") or None,
        "date_to":   request.args.get("date_to")   or None,
    }


def _serialize(a) -> dict:
    """Serialize a SystemAlert to JSON for AJAX endpoints."""
    entity_url = None
    if a.entity_type == "user" and a.entity_id:
        try:
            entity_url = url_for("users.user_detail", user_id=int(a.entity_id))
        except Exception:
            pass
    elif a.entity_type == "sync_run":
        try:
            entity_url = url_for("sync.status")
        except Exception:
            pass

    return {
        "id":                 a.id,
        "type":               a.type,
        "type_label":         a.type_label,
        "level":              a.level,
        "level_label":        a.level_label,
        "level_badge":        a.level_badge_class,
        "level_icon":         a.level_icon,
        "title":              a.title,
        "message":            a.message,
        "entity_type":        a.entity_type,
        "entity_id":          a.entity_id,
        "entity_url":         entity_url,
        "is_read":            a.is_read,
        "is_resolved":        a.is_resolved,
        "resolved_by":        a.resolved_by,
        "resolved_at":        a.resolved_at.strftime("%d/%m/%Y %H:%M") if a.resolved_at else None,
        "resolution_comment": a.resolution_comment,
        "extra_data":         a.extra_data,
        "created_at":         a.created_at.strftime("%d/%m/%Y %H:%M") if a.created_at else "",
        "read_url":           url_for("alerts.mark_read",    alert_id=a.id),
        "resolve_url":        url_for("alerts.resolve_alert", alert_id=a.id),
        "reopen_url":         url_for("alerts.reopen_alert",  alert_id=a.id),
        "detail_url":         url_for("alerts.alert_detail",  alert_id=a.id),
    }


# ── Main views ────────────────────────────────────────────────────────────────

@alerts_bp.route("/")
@login_required
def list_alerts():
    summary = {
        "active":   alerts_service.get_active_count(),
        "unread":   alerts_service.get_unread_count(),
        "critical": alerts_service.get_critical_count(),
    }
    last_recalc = alerts_service.get_last_recalc_time()

    return render_template(
        "alerts/list.html",
        active_page="alerts",
        summary=summary,
        last_recalc=last_recalc,
        search_url=url_for("alerts.search"),
        recalc_url=url_for("alerts.recalculate"),
    )


# ── Search / pagination ───────────────────────────────────────────────────────

@alerts_bp.route("/buscar")
@login_required
def search():
    """JSON endpoint — returns a page of filtered alerts (true server-side pagination)."""
    filters  = _filter_args()
    page     = max(1, request.args.get("page",     1,  type=int))
    per_page = max(1, request.args.get("per_page", 10, type=int))

    pagination = alerts_service.get_alerts_page(page=page, per_page=per_page, **filters)

    last_recalc = alerts_service.get_last_recalc_time()
    return jsonify({
        "total":          pagination.total,
        "pages":          pagination.pages,
        "page":           page,
        "per_page":       per_page,
        "has_next":       pagination.has_next,
        "has_prev":       pagination.has_prev,
        "alerts":         [_serialize(a) for a in pagination.items],
        "active_count":   alerts_service.get_active_count(),
        "unread_count":   alerts_service.get_unread_count(),
        "critical_count": alerts_service.get_critical_count(),
        "last_recalc":    last_recalc.strftime("%d/%m/%Y %H:%M") if last_recalc else None,
    })


@alerts_bp.route("/<int:alert_id>")
@login_required
def alert_detail(alert_id: int):
    """JSON endpoint — returns full detail of a single alert for the detail modal."""
    alert = alerts_service.get_alert_by_id(alert_id)
    if not alert:
        return jsonify({"error": "Alerta no encontrada."}), 404
    return jsonify(_serialize(alert))


# ── Individual action endpoints ───────────────────────────────────────────────

@alerts_bp.route("/<int:alert_id>/leer", methods=["POST"])
@login_required
def mark_read(alert_id: int):
    ok, msg = alerts_service.mark_as_read(alert_id, actor=current_user.username)
    if request.accept_mimetypes.accept_json:
        return jsonify({"ok": ok, "msg": msg})
    flash(msg, "success" if ok else "danger")
    return redirect(request.referrer or url_for("alerts.list_alerts"))


@alerts_bp.route("/<int:alert_id>/resolver", methods=["POST"])
@login_required
def resolve_alert(alert_id: int):
    if request.is_json:
        comment = (request.get_json(silent=True) or {}).get("comment", "").strip() or None
    else:
        comment = request.form.get("comment", "").strip() or None

    ok, msg = alerts_service.mark_as_resolved(
        alert_id, actor=current_user.username, comment=comment
    )
    if request.accept_mimetypes.accept_json:
        return jsonify({"ok": ok, "msg": msg})
    flash(msg, "success" if ok else "danger")
    return redirect(request.referrer or url_for("alerts.list_alerts"))


@alerts_bp.route("/<int:alert_id>/reabrir", methods=["POST"])
@login_required
def reopen_alert(alert_id: int):
    ok, msg = alerts_service.reopen_alert(alert_id, actor=current_user.username)
    if request.accept_mimetypes.accept_json:
        return jsonify({"ok": ok, "msg": msg})
    flash(msg, "success" if ok else "danger")
    return redirect(request.referrer or url_for("alerts.list_alerts"))


# ── Bulk action endpoints ─────────────────────────────────────────────────────

def _bulk_ids() -> list[int]:
    """Extract alert IDs from JSON body {'ids': [1, 2, 3]}."""
    body = request.get_json(silent=True) or {}
    raw  = body.get("ids", [])
    return [int(x) for x in raw if str(x).isdigit()]


@alerts_bp.route("/bulk/leer", methods=["POST"])
@login_required
def bulk_mark_read():
    ids   = _bulk_ids()
    count = alerts_service.mark_many_read(ids, actor=current_user.username)
    return jsonify({"ok": True, "updated": count,
                    "msg": f"{count} alerta(s) marcada(s) como leídas."})


@alerts_bp.route("/bulk/resolver", methods=["POST"])
@login_required
def bulk_resolve():
    body    = request.get_json(silent=True) or {}
    ids     = [int(x) for x in body.get("ids", []) if str(x).isdigit()]
    comment = (body.get("comment") or "").strip() or None
    count   = alerts_service.resolve_many(ids, actor=current_user.username, comment=comment)
    return jsonify({"ok": True, "updated": count,
                    "msg": f"{count} alerta(s) resuelta(s)."})


@alerts_bp.route("/bulk/reabrir", methods=["POST"])
@login_required
def bulk_reopen():
    ids   = _bulk_ids()
    count = alerts_service.reopen_many(ids, actor=current_user.username)
    return jsonify({"ok": True, "updated": count,
                    "msg": f"{count} alerta(s) reabierta(s)."})


# ── Threshold configuration endpoints ────────────────────────────────────────

@alerts_bp.route("/configuracion", methods=["GET"])
@login_required
def get_config():
    """Return current alert thresholds as JSON."""
    return jsonify({"ok": True, "thresholds": alerts_service.get_thresholds()})


@alerts_bp.route("/configuracion", methods=["POST"])
@login_required
def update_config():
    """Update alert thresholds from JSON body {key: value, ...}."""
    body = request.get_json(silent=True) or {}
    try:
        alerts_service.update_thresholds(body, actor=current_user.username)
        return jsonify({"ok": True, "msg": "Configuración guardada."})
    except Exception as exc:
        return jsonify({"ok": False, "msg": str(exc)}), 400


# ── Per-admin notification preference endpoints ───────────────────────────────

@alerts_bp.route("/configuracion/notificaciones", methods=["GET"])
@login_required
def get_notif_prefs():
    """Return current user's notification preferences (creates defaults if absent)."""
    pref = alerts_service.get_or_create_notif_prefs(current_user.id)
    return jsonify({"ok": True, "prefs": pref.to_dict()})


@alerts_bp.route("/configuracion/notificaciones", methods=["POST"])
@login_required
def update_notif_prefs():
    """Update current user's notification preferences from JSON body."""
    body = request.get_json(silent=True) or {}
    alerts_service.update_notif_prefs(current_user.id, body)
    return jsonify({"ok": True, "msg": "Preferencias de notificación guardadas."})


# ── Recalculate ───────────────────────────────────────────────────────────────

@alerts_bp.route("/recalcular", methods=["POST"])
@login_required
def recalculate():
    alerts_service.recalculate_alerts(actor=current_user.username)
    if request.accept_mimetypes.accept_json:
        return jsonify({"ok": True})
    flash("Recálculo de alertas completado.", "success")
    return redirect(url_for("alerts.list_alerts"))


# ── Email endpoints ──────────────────────────────────────────────────────────

@alerts_bp.route("/email/diagnostico", methods=["GET"])
@login_required
def email_diagnostics():
    """Return SMTP configuration diagnostics."""
    from app.model.services import notification_service
    diag = notification_service.diagnose_smtp()
    pending = notification_service.get_pending_alerts()
    diag["pending_alerts"] = len(pending)
    return jsonify({"ok": True, **diag})


@alerts_bp.route("/email/prueba", methods=["POST"])
@login_required
def send_test_email():
    """Send a test email to the current admin (or to a specified address)."""
    from app.model.services import notification_service
    body = request.get_json(silent=True) or {}
    to_email = body.get("email", current_user.email)
    if not to_email:
        return jsonify({"ok": False, "msg": "No hay email configurado para este admin."}), 400

    ok, msg = notification_service.send_test_email(to_email)
    return jsonify({"ok": ok, "msg": msg})


@alerts_bp.route("/email/resumen", methods=["POST"])
@login_required
def send_email_summary():
    """Send batch summary emails to all admins with pending alerts."""
    from app.model.services import notification_service
    results = notification_service.send_summary_emails(actor=current_user.username)
    return jsonify({"ok": True, **results})
