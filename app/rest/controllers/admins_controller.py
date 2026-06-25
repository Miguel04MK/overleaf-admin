"""Admins controller — gestión de administradores de la plataforma.

Pantalla única en /administradores/ con:
  - Listado de admins (stats, búsqueda)
  - Crear admin (modal)
  - Activar / desactivar
  - Resetear contraseña (modal)

NO es para que el admin edite su propia cuenta — eso pertenece a /mi-cuenta/.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.model.services import admins_service
from app.rest.dtos.forms import CreateAdminForm, ResetAdminPasswordForm

admins_bp = Blueprint("admins", __name__, url_prefix="/administradores")


# ── Vista principal ─────────────────────────────────────────────────────────

@admins_bp.route("/")
@login_required
def index():
    admins   = admins_service.get_all_admins()
    stats    = admins_service.get_stats()
    activity = admins_service.get_recent_admin_activity(limit=10)
    return render_template(
        "admins/index.html",
        active_page="admins",
        admins=admins,
        stats=stats,
        activity=activity,
    )


# ── Crear admin ─────────────────────────────────────────────────────────────

@admins_bp.route("/nuevo", methods=["POST"])
@login_required
def create():
    form = CreateAdminForm(request.form)
    if not form.validate():
        first_error = next(
            (errs[0] for errs in form.errors.values() if errs),
            "Datos del formulario no válidos.",
        )
        flash(first_error, "danger")
        return redirect(url_for("admins.index"))

    ok, msg = admins_service.create_admin(
        username=form.username.data,
        email=form.email.data,
        password=form.password.data,
        confirm_password=form.confirm_password.data,
        is_active=bool(form.is_active.data),
        actor=current_user.username,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("admins.index"))


# ── Activar / desactivar ────────────────────────────────────────────────────

@admins_bp.route("/<int:admin_id>/activar", methods=["POST"])
@login_required
def activate(admin_id: int):
    ok, msg = admins_service.set_admin_active(
        admin_id, True,
        actor=current_user.username,
        actor_id=current_user.id,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("admins.index"))


@admins_bp.route("/<int:admin_id>/desactivar", methods=["POST"])
@login_required
def deactivate(admin_id: int):
    ok, msg = admins_service.set_admin_active(
        admin_id, False,
        actor=current_user.username,
        actor_id=current_user.id,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("admins.index"))


# ── Reset password ──────────────────────────────────────────────────────────

@admins_bp.route("/<int:admin_id>/reset-password", methods=["POST"])
@login_required
def reset_password(admin_id: int):
    form = ResetAdminPasswordForm(request.form)
    if not form.validate():
        first_error = next(
            (errs[0] for errs in form.errors.values() if errs),
            "Datos del formulario no válidos.",
        )
        flash(first_error, "danger")
        return redirect(url_for("admins.index"))

    ok, msg = admins_service.reset_admin_password(
        admin_id,
        new_password=form.new_password.data,
        confirm_password=form.confirm_password.data,
        actor=current_user.username,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("admins.index"))
