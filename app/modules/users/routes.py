"""Users blueprint — list and detail views for synchronized Overleaf users."""
from flask import Blueprint, render_template, request, abort, redirect, url_for, flash
from flask_login import login_required
from flask import current_app

from app.modules.users import service as user_service

users_bp = Blueprint("users", __name__, url_prefix="/usuarios", template_folder="templates")


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
    projects_owned = user.projects_owned.all()
    return render_template(
        "users/detail.html",
        user=user,
        projects_owned=projects_owned,
        active_page="users",
    )


@users_bp.route("/<int:user_id>/cuota", methods=["POST"])
@login_required
def set_quota(user_id: int):
    """Update the storage quota for a user."""
    raw_value = request.form.get("quota_value", "").strip()
    raw_unit  = request.form.get("quota_unit", "MB")

    # Empty or zero => remove quota (unlimited)
    if not raw_value or raw_value == "0":
        max_bytes = None
    else:
        try:
            value = float(raw_value)
            if value < 0:
                raise ValueError("negative")
        except ValueError:
            flash("Valor de cuota no valido.", "danger")
            return redirect(url_for("users.user_detail", user_id=user_id))

        multipliers = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}
        mult = multipliers.get(raw_unit, 1024 ** 2)
        max_bytes = int(value * mult)

    ok, msg = user_service.set_user_quota(user_id, max_bytes)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("users.user_detail", user_id=user_id))
