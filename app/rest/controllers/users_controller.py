"""Users controller — list and detail views for synchronized Overleaf users."""
import json

from flask import Blueprint, render_template, request, abort, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app.model.services import users_service
from app.model.services import roles_service
from app.rest.dtos.forms import SetQuotaForm

users_bp = Blueprint("users", __name__, url_prefix="/usuarios")


@users_bp.route("/buscar")
@login_required
def search():
    """JSON endpoint: server-side search, filter, sort & paginate."""
    q        = request.args.get("q", "").strip() or None
    sort     = request.args.get("sort", "email")
    order    = request.args.get("order", "asc")
    page     = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = max(1, min(per_page, 100))  # clamp

    # Parse filters JSON: [{"type":"projects","op":"gte","val":5}, ...]
    filters_raw = request.args.get("filters", "")
    filters = None
    if filters_raw:
        try:
            filters = json.loads(filters_raw)
        except (ValueError, TypeError):
            filters = None

    result = users_service.search_users_paginated(
        q=q, sort=sort, order=order,
        page=page, per_page=per_page,
        filters=filters,
    )
    return jsonify(result)


@users_bp.route("/")
@login_required
def list_users():
    all_roles = roles_service.get_all_roles()
    return render_template("users/list.html", active_page="users", all_roles=all_roles)


@users_bp.route("/<int:user_id>")
@login_required
def user_detail(user_id: int):
    page = request.args.get("page", 1, type=int)
    data = users_service.get_user_detail_data(user_id, projects_page=page)
    if data is None:
        abort(404)
    all_roles = roles_service.get_all_roles()
    return render_template("users/detail.html", active_page="users",
                           all_roles=all_roles, **data)


@users_bp.route("/<int:user_id>/cuota", methods=["POST"])
@login_required
def set_quota(user_id: int):
    form = SetQuotaForm(request.form)
    if not form.validate():
        flash("Valor de cuota no válido.", "danger")
        return redirect(url_for("users.user_detail", user_id=user_id))

    max_bytes = form.to_bytes()
    ok, msg = users_service.set_user_quota(
        user_id, max_bytes,
        actor=current_user.username,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("users.user_detail", user_id=user_id))
