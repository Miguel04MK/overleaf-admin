"""Users blueprint — list and detail views for synchronized Overleaf users."""
from flask import Blueprint, render_template, request, abort, redirect, url_for, flash, jsonify
from flask_login import login_required
from flask import current_app

from app.modules.users import service as user_service

users_bp = Blueprint("users", __name__, url_prefix="/usuarios", template_folder="templates")


def _serialize_user(u) -> dict:
    return {
        "id": u.id,
        "email": u.email or "",
        "display_name": u.display_name if u.display_name != u.email else "",
        "is_admin": u.is_admin,
        "projects_count": u.projects_owned.count(),
        "quota_percent": u.quota_percent,
        "quota_status": u.quota_status,
        "quota_used_fmt": u.quota_used_fmt,
        "quota_max_fmt": u.quota_max_fmt,
        "quota_exceeded": u.quota_exceeded,
        "signup_date": u.signup_date.strftime("%d/%m/%Y") if u.signup_date else "",
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "detail_url": url_for("users.user_detail", user_id=u.id),
    }


@users_bp.route("/buscar")
@login_required
def search():
    """JSON endpoint for live search + sorting."""
    q = request.args.get("q", "").strip() or None
    sort = request.args.get("sort", "email")
    order = request.args.get("order", "asc")
    users = user_service.search_users(q=q, sort=sort, order=order)
    return jsonify({"total": len(users), "users": [_serialize_user(u) for u in users]})


@users_bp.route("/")
@login_required
def list_users():
    return render_template("users/list.html", active_page="users")


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
