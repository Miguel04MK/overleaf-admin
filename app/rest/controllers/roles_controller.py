"""Roles controller — manage administrative roles and audit log."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user

from app.model.services import roles_service
from app.rest.dtos.forms import (
    UpdateRoleForm, ManageUserRoleForm, AssignRoleForm, CreateRoleForm,
)

roles_bp = Blueprint("roles", __name__, url_prefix="/roles")


# ── Views ─────────────────────────────────────────────────────────────────────

@roles_bp.route("/")
@login_required
def list_roles():
    roles        = roles_service.get_all_roles()
    stats        = roles_service.get_role_stats_by_id()   # {role_id: count}
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
    recent_logs  = roles_service.get_role_change_logs(role_id=role_id, per_page=10)
    users_stats  = roles_service.get_users_stats_for_role(role_id)   # all users, for JS
    default_role = roles_service.get_default_role()                  # para el modal de borrado
    return render_template(
        "roles/detail.html",
        active_page="roles",
        role=role,
        users_stats=users_stats,
        recent_logs=recent_logs,
        default_role=default_role,
    )


@roles_bp.route("/crear", methods=["POST"])
@login_required
def create_role():
    """Crea un nuevo rol desde el modal de /roles/."""
    form = CreateRoleForm(request.form)
    if not form.validate():
        first_error = next(
            (errs[0] for errs in form.errors.values() if errs),
            "Datos del rol no válidos.",
        )
        flash(first_error, "danger")
        return redirect(url_for("roles.list_roles"))

    ok, msg, _role = roles_service.create_role(
        name=form.name.data,
        description=form.description.data,
        storage_quota_bytes=form.to_quota_bytes(),
        max_projects=form.to_max_projects(),
        is_default=bool(form.is_default.data),
        color=form.color.data,
        actor=current_user.username,
        ip_address=request.remote_addr,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("roles.list_roles"))


@roles_bp.route("/<int:role_id>/eliminar", methods=["POST"])
@login_required
def delete_role(role_id: int):
    """Elimina un rol. Si falla un guard de seguridad, redirige al detalle
    con flash; si tiene éxito, vuelve al listado."""
    ok, msg = roles_service.delete_role(
        role_id,
        actor=current_user.username,
        ip_address=request.remote_addr,
    )
    flash(msg, "success" if ok else "danger")
    if ok:
        return redirect(url_for("roles.list_roles"))
    return redirect(url_for("roles.role_detail", role_id=role_id))


@roles_bp.route("/<int:role_id>/editar", methods=["POST"])
@login_required
def update_role(role_id: int):
    role = roles_service.get_role_by_id(role_id)
    if not role:
        abort(404)

    form = UpdateRoleForm(request.form)
    if not form.validate():
        flash("Datos del rol no válidos.", "danger")
        return redirect(url_for("roles.role_detail", role_id=role_id))

    ok, msg = roles_service.update_role_config(
        role_id=role_id,
        description=form.description.data.strip() or None,
        storage_quota_bytes=form.to_quota_bytes(),
        max_projects=form.to_max_projects(),
        is_default=bool(form.is_default.data),
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
    """Assign or remove a user's role from the role detail page.

    Si la peticion viene de un fetch (header `X-Requested-With: XMLHttpRequest`)
    se devuelve JSON sin redirect ni flash, para que el cliente pueda batchear
    multiples cambios sin acumular N flash messages.
    """
    role = roles_service.get_role_by_id(role_id)
    if not role:
        abort(404)

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    form = ManageUserRoleForm(request.form)
    if not form.validate():
        if is_ajax:
            return jsonify({"ok": False, "msg": "No se ha seleccionado ningún usuario."}), 400
        flash("No se ha seleccionado ningún usuario.", "danger")
        return redirect(url_for("roles.role_detail", role_id=role_id))

    user_id = form.user_id.data
    action  = form.action.data

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

    if is_ajax:
        return jsonify({"ok": ok, "msg": msg}), (200 if ok else 400)

    flash(msg, "success" if ok else "danger")
    return redirect(url_for("roles.role_detail", role_id=role_id))


@roles_bp.route("/asignar/<int:user_id>", methods=["POST"])
@login_required
def assign_role(user_id: int):
    """Assign or change the role of a user. Called from user detail page."""
    form    = AssignRoleForm(request.form)
    form.validate()  # campos opcionales; sólo normaliza tipos
    role_id = form.role_id.data
    reason  = (form.reason.data or "").strip() or None
    action  = form.action.data or "assign"

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
