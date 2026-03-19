"""Audit blueprint — view audit log entries."""
from flask import Blueprint, render_template, request
from flask_login import login_required

from app.services import audit_service

audit_bp = Blueprint("audit", __name__, url_prefix="/auditoria")


@audit_bp.route("/")
@login_required
def logs():
    page = request.args.get("page", 1, type=int)
    pagination = audit_service.get_paginated_logs(page=page, per_page=30)
    return render_template(
        "audit/logs.html",
        pagination=pagination,
        active_page="audit",
    )
