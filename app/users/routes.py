"""Users blueprint — list and detail views for synchronized Overleaf users."""
from flask import Blueprint, render_template, request, abort
from flask_login import login_required
from flask import current_app

from app.services import user_service

users_bp = Blueprint("users", __name__, url_prefix="/usuarios")


@users_bp.route("/")
@login_required
def list_users():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip() or None
    per_page = current_app.config.get("ITEMS_PER_PAGE", 20)

    pagination = user_service.get_users_page(page=page, per_page=per_page, search=search)
    return render_template(
        "users/list.html",
        pagination=pagination,
        search=search or "",
        active_page="users",
    )


@users_bp.route("/<int:user_id>")
@login_required
def user_detail(user_id: int):
    user = user_service.get_user_by_id(user_id)
    if not user:
        abort(404)
    # Projects owned by this user
    projects_owned = user.projects_owned.all()
    return render_template(
        "users/detail.html",
        user=user,
        projects_owned=projects_owned,
        active_page="users",
    )
