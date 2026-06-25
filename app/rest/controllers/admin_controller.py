"""Admin controller — audit log."""
from flask import Blueprint, render_template, request
from flask_login import login_required

from app.model.services.admin import admin_service

audit_bp = Blueprint("audit", __name__, url_prefix="/auditoria")


@audit_bp.route("/")
@login_required
def logs():
    # Filtros de la URL — todos opcionales
    page      = request.args.get("page", 1, type=int)
    search    = request.args.get("q", "", type=str).strip() or None
    level     = request.args.get("level", "", type=str).strip() or None
    category  = request.args.get("category", "", type=str).strip() or None
    actor     = request.args.get("actor", "", type=str).strip() or None
    date_from = request.args.get("date_from", "", type=str).strip() or None
    date_to   = request.args.get("date_to", "", type=str).strip() or None
    last_24h  = request.args.get("last_24h", "", type=str) in ("1", "true", "yes", "y")

    pagination = admin_service.get_filtered_logs(
        page=page, per_page=30,
        search=search, level=level, category=category, actor=actor,
        date_from=date_from, date_to=date_to, last_24h=last_24h,
    )
    summary = admin_service.get_audit_summary()
    actors  = admin_service.get_distinct_actors()

    return render_template(
        "audit/logs.html",
        active_page="audit",
        pagination=pagination,
        summary=summary,
        actors=actors,
        categories=admin_service.CATEGORIES,
        label_for_action=admin_service.label_for_action,
        category_for_action=admin_service.category_for_action,
        # Estado actual de los filtros (para volver a pintarlos en el form)
        f_search=search or "",
        f_level=level or "",
        f_category=category or "",
        f_actor=actor or "",
        f_date_from=date_from or "",
        f_date_to=date_to or "",
        f_last_24h=last_24h,
    )


