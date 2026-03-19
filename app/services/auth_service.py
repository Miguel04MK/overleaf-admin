"""
AuthService — login/logout logic for the admin platform.
"""
import logging
from flask import request
from flask_login import login_user, logout_user

from app.models.admin_user import AdminUser
from app.extensions import db
from app.services import audit_service

logger = logging.getLogger(__name__)


def authenticate(username: str, password: str) -> AdminUser | None:
    """Validate credentials. Returns the AdminUser on success, None on failure."""
    user = AdminUser.query.filter_by(username=username, is_active=True).first()
    if user and user.check_password(password):
        return user
    return None


def perform_login(user: AdminUser) -> None:
    """Log the user into the Flask session and record the audit event."""
    user.update_last_login()
    db.session.commit()
    login_user(user)
    audit_service.log_action(
        action="login",
        actor=user.username,
        detail=f"Inicio de sesión exitoso",
        level="info",
        ip_address=request.remote_addr,
    )
    logger.info("Admin '%s' logged in from %s", user.username, request.remote_addr)


def perform_logout(username: str) -> None:
    """Log the user out and record the audit event."""
    logout_user()
    audit_service.log_action(
        action="logout",
        actor=username,
        detail="Cierre de sesión",
        level="info",
        ip_address=request.remote_addr,
    )
    logger.info("Admin '%s' logged out", username)
