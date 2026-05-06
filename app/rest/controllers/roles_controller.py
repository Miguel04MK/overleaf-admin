"""Roles controller — manage administrative roles and audit log."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user

from app.model.services import roles_service

roles_bp = Blueprint("roles", __name__, url_prefix="/roles")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_int_or_none(value: str) -> int | None:
    try:
        v = int(value)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_bytes(value: str, unit: str) -> int | None:
    """Parse a (value, unit) pair into bytes. Returns None for empty/zero."""
    try:
        v = float(value)
        if v <= 0:
            return None
    except (ValueError, TypeError):
        return None
    multipliers = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}
    return int(v * multipliers.get(unit, 1024 ** 2))


# ── Views ─────────────────────────────────────────────────────────────────────

@roles_bp.route("/")
@login_required
def list_roles():
    roles        = roles_service.get_all_roles()
    stats        = roles_service.get_role_stats()   # {role_id: count}
    default      = roles_service.get_default_role()
    recent_logs  = roles_service.get_role_change_logs(per_page=8).items
    quota_alerts = roles_service.get_quota_alerts_per_role()  # {role_id: {near_limit, exceeded}}
    return render_template(
        "roles/list.html",
        active_page="roles",
        roles=roles,
        stats=stats,
        default_role=default,
        recent_logs=recent_logs,
        quota_alerts=quota_alerts,
    )


@roles_bp.route("/<int:role_id>")
@login_required
def role_detail(role_id: int):
    role = roles_service.get_role_by_id(role_id)
    if not role:
        abort(404)
    recent_logs = roles_service.get_role_change_logs(role_id=role_id, per_page=10)
    users_stats = roles_service.get_users_stats_for_role(role_id)   # all users, for JS
    return render_template(
        "roles/detail.html",
        active_page="roles",
        role=role,
        users_stats=users_stats,
        recent_logs=recent_logs,
    )


@roles_bp.route("/<int:role_id>/editar", methods=["POST"])
@login_required
def update_role(role_id: int):
    role = roles_service.get_role_by_id(role_id)
    if not role:
        abort(404)

    description   = request.form.get("description", "").strip()
    quota_value   = request.form.get("quota_value", "").strip()
    quota_unit    = request.form.get("quota_unit", "MB")
    max_proj_raw  = request.form.get("max_projects", "").strip()

    quota_bytes = _parse_bytes(quota_value, quota_unit)
    max_projects = _parse_int_or_none(max_proj_raw)

    ok, msg = roles_service.update_role_config(
        role_id=role_id,
        description=description or None,
        storage_quota_bytes=quota_bytes,
        max_projects=max_projects,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("roles.role_detail", role_id=role_id))


@roles_bp.route("/auditoria")
@login_required
def audit_log():
    page      = request.args.get("page", 1, type=int)
    user_id   = request.args.get("user_id",  None, type=int)
    role_id   = request.args.get("role_id",  None, type=int)
    action    = request.args.get("action",   None)
    all_roles = roles_service.get_all_roles()

    _VALID_ACTIONS = {"assigned", "changed", "removed"}
    if action not in _VALID_ACTIONS:
        action = None

    pagination = roles_service.get_role_change_logs(
        user_id=user_id, role_id=role_id, action=action, page=page,
    )
    return render_template(
        "roles/audit.html",
        active_page="roles",
        pagination=pagination,
        all_roles=all_roles,
        filter_user_id=user_id,
        filter_role_id=role_id,
        filter_action=action,
    )


@roles_bp.route("/<int:role_id>/buscar-usuarios")
@login_required
def search_users_for_role(role_id: int):
    """API endpoint: search all users, marking whether they already have this role."""
    role = roles_service.get_role_by_id(role_id)
    if not role:
        return jsonify([]), 404

    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])

    results = roles_service.search_users_for_role(role_id, q, limit=15)
    return jsonify(results)


@roles_bp.route("/<int:role_id>/gestionar-usuario", methods=["POST"])
@login_required
def manage_user_role(role_id: int):
    """Assign or remove a user's role from the role detail page."""
    role = roles_service.get_role_by_id(role_id)
    if not role:
        abort(404)

    user_id = request.form.get("user_id", type=int)
    action  = request.form.get("action", "assign")   # "assign" | "remove"

    if not user_id:
        flash("No se ha seleccionado ningún usuario.", "danger")
        return redirect(url_for("roles.role_detail", role_id=role_id))

    if action == "remove":
        ok, msg = roles_service.remove_role(
            user_id=user_id,
            actor=current_user.username,
        )
    else:
        ok, msg = roles_service.assign_role(
            user_id=user_id,
            role_id=role_id,
            actor=current_user.username,
        )

    flash(msg, "success" if ok else "danger")
    return redirect(url_for("roles.role_detail", role_id=role_id))


@roles_bp.route("/asignar/<int:user_id>", methods=["POST"])
@login_required
def assign_role(user_id: int):
    """Assign or change the role of a user. Called from user detail page."""
    role_id = request.form.get("role_id", type=int)
    reason  = request.form.get("reason", "").strip() or None
    action  = request.form.get("action", "assign")  # 'assign' | 'remove'

    # Empty role_id means "remove / reset to default"
    if action == "remove" or not role_id:
        ok, msg = roles_service.remove_role(
            user_id=user_id,
            actor=current_user.username,
            reason=reason,
        )
    else:
        ok, msg = roles_service.assign_role(
            user_id=user_id,
            role_id=role_id,
            actor=current_user.username,
            reason=reason,
        )

    flash(msg, "success" if ok else "danger")
    return redirect(url_for("users.user_detail", user_id=user_id))
