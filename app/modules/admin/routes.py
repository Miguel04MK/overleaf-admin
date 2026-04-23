"""Admin blueprints — audit log and developer utilities."""
from flask import Blueprint, render_template, request
from flask_login import login_required

from app.modules.admin import service as admin_service

audit_bp = Blueprint("audit", __name__, url_prefix="/auditoria", template_folder="templates")
dev_bp = Blueprint("dev", __name__, url_prefix="/dev", template_folder="templates")


@audit_bp.route("/")
@login_required
def logs():
    page = request.args.get("page", 1, type=int)
    pagination = admin_service.get_paginated_logs(page=page, per_page=30)
    return render_template(
        "audit/logs.html",
        pagination=pagination,
        active_page="audit",
    )


@dev_bp.route("/")
@login_required
def index():
    service_statuses = admin_service.get_service_statuses()
    return render_template(
        "dev/index.html",
        service_statuses=service_statuses,
        active_page="dev",
    )
