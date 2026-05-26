"""
AuthService — login/logout logic for the admin platform.
"""
import logging
from flask import request
from flask_login import login_user, logout_user

from app.model.entities.admin_user import AdminUser
from app.config.extensions import db
from app.model.services.admin import admin_service as audit_service

logger = logging.getLogger(__name__)


def authenticate(login_identifier: str, password: str) -> AdminUser | None:
    """Authenticate an admin by either username or email.

    Acepta indistintamente `username` o `email` como identificador. Normaliza
    espacios y compara el email en minúsculas (los emails se guardan así
    también desde admins_service.create_admin).

    Devuelve el AdminUser sólo si:
      - existe (por username exacto o por email lower)
      - la contraseña es correcta
      - is_active es True
    """
    if not login_identifier or not password:
        return None
    ident = (login_identifier or "").strip()
    if not ident:
        return None

    # Buscar por username exacto o por email (case-insensitive).
    user = (
        AdminUser.query
        .filter(
            db.or_(
                AdminUser.username == ident,
                AdminUser.email    == ident.lower(),
            )
        )
        .filter(AdminUser.is_active.is_(True))
        .first()
    )
    if user and user.check_password(password):
        return user
    return None


def perform_login(user: AdminUser) -> None:
    user.update_last_login()
    db.session.commit()
    login_user(user)
    audit_service.log_action(
        action="login",
        actor=user.username,
        detail="Inicio de sesión exitoso",
        level="info",
        ip_address=request.remote_addr,
    )
    logger.info("Admin '%s' logged in from %s", user.username, request.remote_addr)


def perform_logout(username: str) -> None:
    logout_user()
    audit_service.log_action(
        action="logout",
        actor=username,
        detail="Cierre de sesión",
        level="info",
        ip_address=request.remote_addr,
    )
    logger.info("Admin '%s' logged out", username)
