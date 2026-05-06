"""Dashboard controller — main overview page."""
from flask import Blueprint, render_template
from flask_login import login_required

from app.model.services import dashboard_service

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/")


@dashboard_bp.route("/")
@login_required
def index():
    stats = dashboard_service.get_stats()
    return render_template(
        "dashboard/index.html",
        stats=stats,
        active_page="dashboard",
    )
