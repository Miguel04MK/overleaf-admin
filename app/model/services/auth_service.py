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


def authenticate(username: str, password: str) -> AdminUser | None:
    user = AdminUser.query.filter_by(username=username, is_active=True).first()
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
