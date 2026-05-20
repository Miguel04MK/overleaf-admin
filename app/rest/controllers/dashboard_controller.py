"""Dashboard controller — high-level overview page."""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required

from app.model.services import dashboard_service

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/")


@dashboard_bp.route("/")
@login_required
def index():
    data = dashboard_service.get_dashboard_data()
    return render_template(
        "dashboard/index.html",
        d=data,
        active_page="dashboard",
    )


@dashboard_bp.route("/api/dashboard/quota-users")
@login_required
def quota_users_page():
    """Paginated users near quota — called by the dashboard rotation widget."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 7, type=int)
    per_page = min(per_page, 20)  # cap
    result = dashboard_service.get_users_near_quota_page(page=page, per_page=per_page)
    return jsonify(result)
