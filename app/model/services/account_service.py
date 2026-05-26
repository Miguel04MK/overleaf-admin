"""
AccountService — lógica del área "Mi cuenta" del administrador autenticado.

Gestiona:
  - Lectura de los datos básicos del admin (overview)
  - Cambio de contraseña (con validación de password actual y auditoría)
  - Lectura y actualización de preferencias de notificación
  - Consulta de actividad reciente (últimos AuditLog del admin)
"""
import logging

from app.config.extensions import db
from app.model.entities.admin_user import AdminUser
from app.model.entities.audit_log import AuditLog
from app.model.entities.admin_notification_pref import AdminNotificationPref
from app.model.services.admin import admin_service as audit_service

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8


# Etiquetas legibles para el AuditLog en la card "Actividad reciente"
ACTION_LABELS: dict[str, str] = {
    "login":                          "Inicio de sesión",
    "logout":                         "Cierre de sesión",
    "password_change":                "Cambio de contraseña",
    "notification_preferences_update":"Preferencias de notificación actualizadas",
    "alert_resolve":                  "Alerta resuelta",
    "alert_reopen":                   "Alerta reabierta",
    "alert_mark_read":                "Alerta marcada como leída",
    "admin_create":                   "Administrador creado",
    "admin_disable":                  "Administrador desactivado",
    "admin_enable":                   "Administrador activado",
    "admin_password_reset":           "Contraseña de admin reseteada",
    "role_assign":                    "Rol asignado",
    "role_remove":                    "Rol eliminado",
    "sync_start":                     "Sincronización iniciada",
    "sync_ok":                        "Sincronización OK",
    "sync_error":                     "Sincronización con error",
}


def label_for_action(action: str) -> str:
    """Traduce un AuditLog.action a una etiqueta legible."""
    return ACTION_LABELS.get(action, action.replace("_", " ").capitalize())


# ── Datos de cuenta ──────────────────────────────────────────────────────────

def get_account_overview(admin_id: int) -> dict | None:
    """Devuelve los datos visibles en la card "Perfil del administrador"."""
    admin = db.session.get(AdminUser, admin_id)
    if not admin:
        return None
    # Inicial para el avatar circular
    initial = (admin.username or "?")[:1].upper()
    return {
        "id":            admin.id,
        "username":      admin.username,
        "email":         admin.email,
        "is_active":     admin.is_active,
        "created_at":    admin.created_at,
        "last_login_at": admin.last_login_at,
        "initial":       initial,
    }


def get_last_password_change(actor: str):
    """Devuelve el AuditLog más reciente de tipo password_change del actor, o None."""
    return (
        AuditLog.query
        .filter_by(actor=actor, action="password_change")
        .order_by(AuditLog.created_at.desc())
        .first()
    )


def get_recent_activity(actor: str, limit: int = 5) -> list[dict]:
    """Devuelve los últimos *limit* AuditLogs del actor, ya con etiqueta legible.

    Mapea cada entrada a un dict con {created_at, action, action_label, level, detail}
    para no exponer el ORM al template.
    """
    rows = (
        AuditLog.query
        .filter_by(actor=actor)
        .order_by(AuditLog.created_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    return [
        {
            "created_at":   r.created_at,
            "action":       r.action,
            "action_label": label_for_action(r.action),
            "level":        r.level,
            "detail":       r.detail,
        }
        for r in rows
    ]


# ── Cambio de contraseña ─────────────────────────────────────────────────────

def change_password(
    admin_id: int,
    current_password: str,
    new_password: str,
    confirm_password: str,
    ip_address: str | None = None,
) -> tuple[bool, str]:
    """Cambia la contraseña del admin actual.

    Devuelve (ok, mensaje). Nunca incluye contraseñas en logs.
    Registra un AuditLog `password_change` si tiene éxito.
    """
    admin = db.session.get(AdminUser, admin_id)
    if not admin:
        return False, "Cuenta de administrador no encontrada."

    if not current_password or not new_password or not confirm_password:
        return False, "Todos los campos de contraseña son obligatorios."

    if not admin.check_password(current_password):
        logger.warning("Cambio de contraseña fallido para %s: password actual incorrecta", admin.username)
        return False, "La contraseña actual es incorrecta."

    if len(new_password) < MIN_PASSWORD_LENGTH:
        return False, f"La nueva contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."

    if new_password != confirm_password:
        return False, "La confirmación de la nueva contraseña no coincide."

    if new_password == current_password:
        return False, "La nueva contraseña debe ser distinta de la actual."

    admin.set_password(new_password)
    db.session.commit()

    audit_service.log_action(
        action="password_change",
        actor=admin.username,
        detail="Cambio de contraseña del administrador",
        level="info",
        ip_address=ip_address,
    )
    logger.info("Admin '%s' cambió su contraseña", admin.username)

    return True, "Contraseña actualizada correctamente."


# ── Preferencias de notificación ─────────────────────────────────────────────

def get_notification_preferences(admin_id: int) -> AdminNotificationPref:
    """Devuelve las preferencias del admin; las crea con defaults si no existen."""
    pref = AdminNotificationPref.query.filter_by(admin_id=admin_id).first()
    if pref is None:
        pref = AdminNotificationPref(admin_id=admin_id)
        db.session.add(pref)
        db.session.commit()
    return pref


def update_notification_preferences(
    admin_id: int,
    data: dict,
    ip_address: str | None = None,
) -> tuple[bool, str]:
    """Actualiza las preferencias de notificación del admin (crea fila si no existe).

    Devuelve (ok, mensaje) y registra un AuditLog `notification_preferences_update`.
    """
    admin = db.session.get(AdminUser, admin_id)
    if not admin:
        return False, "Cuenta de administrador no encontrada."

    pref = AdminNotificationPref.query.filter_by(admin_id=admin_id).first()
    if pref is None:
        pref = AdminNotificationPref(admin_id=admin_id)
        db.session.add(pref)

    pref.update_from_dict(data)
    db.session.commit()

    audit_service.log_action(
        action="notification_preferences_update",
        actor=admin.username,
        detail="Actualización de preferencias de notificación",
        level="info",
        ip_address=ip_address,
    )

    return True, "Preferencias guardadas correctamente."
