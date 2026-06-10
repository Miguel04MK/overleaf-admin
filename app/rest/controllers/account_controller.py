"""Account controller — área "Mi cuenta" del administrador autenticado.

Pantalla principal con 4 cards: perfil, seguridad, notificaciones (inline)
y actividad reciente.

NO maneja creación/desactivación de otros admins — eso pertenece al módulo
/administradores/ (a implementar en una segunda iteración).
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.model.services import account_service
from app.rest.dtos.forms import ChangePasswordForm, NotifPrefsForm

account_bp = Blueprint("account", __name__, url_prefix="/mi-cuenta")


@account_bp.route("/")
@login_required
def index():
    overview            = account_service.get_account_overview(current_user.id)
    prefs               = account_service.get_notification_preferences(current_user.id)
    last_pw_change      = account_service.get_last_password_change(current_user.username)
    recent_activity     = account_service.get_recent_activity(current_user.username, limit=7)
    return render_template(
        "account/index.html",
        active_page="account",
        overview=overview,
        prefs=prefs,
        last_pw_change=last_pw_change,
        recent_activity=recent_activity,
    )


@account_bp.route("/cambiar-password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm(request.form)
    if not form.validate():
        first_error = next(
            (errs[0] for errs in form.errors.values() if errs),
            "Datos del formulario no válidos.",
        )
        flash(first_error, "danger")
        return redirect(url_for("account.index"))

    ok, msg = account_service.change_password(
        admin_id=current_user.id,
        current_password=form.current_password.data,
        new_password=form.new_password.data,
        confirm_password=form.confirm_password.data,
        ip_address=request.remote_addr,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("account.index"))


@account_bp.route("/notificaciones", methods=["POST"])
@login_required
def update_notifications():
    form = NotifPrefsForm(request.form)
    if not form.validate():
        flash("Datos de preferencias no válidos.", "danger")
        return redirect(url_for("account.index"))

    ok, msg = account_service.update_notification_preferences(
        admin_id=current_user.id,
        data=form.to_dict(),
        ip_address=request.remote_addr,
    )
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("account.index"))
