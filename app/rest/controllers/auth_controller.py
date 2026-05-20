"""Auth controller — login and logout."""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required

from app.model.services import auth_service
from app.rest.dtos.forms import LoginForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        form = LoginForm(request.form)
        if form.validate():
            user = auth_service.authenticate(
                form.username.data.strip(), form.password.data
            )
            if user:
                auth_service.perform_login(user)
                next_page = request.args.get("next") or url_for("dashboard.index")
                return redirect(next_page)
        flash("Credenciales incorrectas. Inténtalo de nuevo.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    username = current_user.username
    auth_service.perform_logout(username)
    flash("Has cerrado sesión correctamente.", "success")
    return redirect(url_for("auth.login"))
