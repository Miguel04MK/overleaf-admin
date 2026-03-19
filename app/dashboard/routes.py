"""Dashboard blueprint — main overview page."""
from flask import Blueprint, render_template
from flask_login import login_required

from app.services import dashboard_service, status_service

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/")


@dashboard_bp.route("/")
@login_required
def index():
    stats = dashboard_service.get_stats()
    service_statuses = status_service.get_service_statuses()
    return render_template(
        "dashboard/index.html",
        stats=stats,
        service_statuses=service_statuses,
        active_page="dashboard",
    )
