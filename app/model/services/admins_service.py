"""
AdminsService — gestión de cuentas de administrador de la plataforma.

Pertenece al módulo /administradores/. Permite:
  - Listar admins con sus estadísticas (último acceso, nº de acciones)
  - Crear admins nuevos
  - Activar / desactivar admins
  - Resetear / cambiar la contraseña de un admin

Reglas de seguridad clave:
  - Username y email son únicos (constraints en DB).
  - SIEMPRE debe quedar al menos un admin activo.
  - Un admin no puede desactivarse a sí mismo si es el único activo.
  - Las contraseñas nunca aparecen en logs.
  - Cada mutación deja rastro en AuditLog (admin_create, admin_disable,
    admin_enable, admin_password_reset).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.config.extensions import db
from app.model.entities.admin_user import AdminUser
from app.model.entities.audit_log import AuditLog
from app.model.services.admin import admin_service as audit_service

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8


# ── Lecturas ─────────────────────────────────────────────────────────────────

def get_all_admins() -> list[dict]:
    """Devuelve todos los admins con sus stats (última actividad, nº acciones,
    último cambio de contraseña).

    Hace 2 queries agrupadas para evitar N+1: una con la lista de admins
    más el conteo total de AuditLogs por actor, y otra con la fecha del último
    `password_change` por actor.
    """
    counts_sq = (
        db.session.query(
            AuditLog.actor.label("actor"),
            func.count(AuditLog.id).label("n"),
        )
        .group_by(AuditLog.actor)
        .subquery()
    )

    rows = (
        db.session.query(AdminUser, func.coalesce(counts_sq.c.n, 0).label("audit_count"))
        .outerjoin(counts_sq, counts_sq.c.actor == AdminUser.username)
        .order_by(AdminUser.is_active.desc(), AdminUser.username.asc())
        .all()
    )

    last_pw_by_actor: dict[str, object] = dict(
        db.session.query(AuditLog.actor, func.max(AuditLog.created_at))
        .filter(AuditLog.action == "password_change")
        .group_by(AuditLog.actor)
        .all()
    )

    active_total = count_active_admins()

    return [
        {
            "id":                      a.id,
            "username":                a.username,
            "email":                   a.email,
            "is_active":               a.is_active,
            "created_at":              a.created_at,
            "last_login_at":           a.last_login_at,
            "last_password_change_at": last_pw_by_actor.get(a.username),
            "audit_count":             int(n),
            # True si desactivarlo dejaría 0 admins activos: lo bloqueamos.
            "is_protected":            bool(a.is_active and active_total <= 1),
        }
        for a, n in rows
    ]


def get_admin_by_id(admin_id: int) -> AdminUser | None:
    return db.session.get(AdminUser, admin_id)


def get_stats() -> dict:
    """KPI rápidos para las cards de cabecera."""
    total  = db.session.query(func.count(AdminUser.id)).scalar() or 0
    active = (
        db.session.query(func.count(AdminUser.id))
        .filter(AdminUser.is_active.is_(True))
        .scalar()
    ) or 0
    return {
        "total":    int(total),
        "active":   int(active),
        "inactive": int(total - active),
    }


def count_active_admins() -> int:
    return (
        db.session.query(func.count(AdminUser.id))
        .filter(AdminUser.is_active.is_(True))
        .scalar()
    ) or 0


def get_recent_admin_activity(limit: int = 10) -> list[dict]:
    """Últimos AuditLogs cuyo `actor` es un AdminUser conocido.

    Reusa el mapeo de etiquetas legibles de account_service para no duplicar
    la lista de acciones traducidas. Devuelve dicts (sin exponer el ORM).
    """
    from app.model.services.account_service import label_for_action

    rows = (
        db.session.query(AuditLog)
        .join(AdminUser, AdminUser.username == AuditLog.actor)
        .order_by(AuditLog.created_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    return [
        {
            "created_at":   r.created_at,
            "action":       r.action,
            "action_label": label_for_action(r.action),
            "actor":        r.actor,
            "level":        r.level,
            "detail":       r.detail,
        }
        for r in rows
    ]


# ── Mutaciones ───────────────────────────────────────────────────────────────

def create_admin(
    *,
    username: str,
    email: str,
    password: str,
    confirm_password: str,
    is_active: bool = True,
    actor: str = "system",
    ip_address: str | None = None,
) -> tuple[bool, str]:
    """Crea un AdminUser nuevo. Devuelve (ok, mensaje).

    Validaciones:
    - username y email obligatorios y no vacíos
    - email con formato razonable (incluye '@' y '.')
    - password >= 8 chars
    - password == confirm_password
    - unicidad de username y email (constraint DB)
    """
    u = (username or "").strip()
    e = (email or "").strip().lower()

    if not u or not e:
        return False, "Usuario y email son obligatorios."

    if len(u) > 64:
        return False, "El usuario no puede tener más de 64 caracteres."

    if "@" not in e or "." not in e or len(e) > 255:
        return False, "Email con formato no válido."

    if not password or not confirm_password:
        return False, "La contraseña y su confirmación son obligatorias."

    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."

    if password != confirm_password:
        return False, "Las contraseñas no coinciden."

    # Comprobación previa (mensaje más claro que IntegrityError)
    if AdminUser.query.filter_by(username=u).first():
        return False, f"Ya existe un administrador con el usuario '{u}'."
    if AdminUser.query.filter_by(email=e).first():
        return False, f"Ya existe un administrador con el email '{e}'."

    new_admin = AdminUser(username=u, email=e, is_active=bool(is_active))
    new_admin.set_password(password)

    try:
        db.session.add(new_admin)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        logger.warning("IntegrityError creando admin %s: %s", u, exc)
        return False, "No se pudo crear: usuario o email duplicados."
    except Exception as exc:
        db.session.rollback()
        logger.error("Error inesperado creando admin %s: %s", u, exc)
        return False, "Error inesperado al crear el administrador."

    audit_service.log_action(
        action="admin_create",
        actor=actor,
        detail=f"Administrador '{u}' creado (activo={is_active})",
        level="info",
        ip_address=ip_address,
    )
    logger.info("Admin '%s' creó al nuevo admin '%s'", actor, u)
    return True, f"Administrador '{u}' creado correctamente."


def set_admin_active(
    admin_id: int,
    active: bool,
    *,
    actor: str,
    actor_id: int | None = None,
    ip_address: str | None = None,
) -> tuple[bool, str]:
    """Activa o desactiva un admin con guarda del último admin activo."""
    target = db.session.get(AdminUser, admin_id)
    if not target:
        return False, "Administrador no encontrado."

    # Mismo estado → no-op
    if target.is_active == bool(active):
        return False, "El administrador ya está en ese estado."

    # No permitir que un admin se desactive a sí mismo — NUNCA (no sólo cuando
    # es el último activo). El cambio de su propia cuenta se hace desde /mi-cuenta/.
    if not active and actor_id is not None and actor_id == admin_id:
        return False, "No puedes desactivar tu propia cuenta."

    # Guarda del último admin activo
    if not active and target.is_active and count_active_admins() <= 1:
        return False, "No se puede desactivar al último administrador activo de la plataforma."

    target.is_active = bool(active)
    db.session.commit()

    action = "admin_enable" if active else "admin_disable"
    detail = f"Administrador '{target.username}' { 'activado' if active else 'desactivado' }"
    audit_service.log_action(
        action=action, actor=actor, detail=detail,
        level="info", ip_address=ip_address,
    )
    return True, detail + "."


def reset_admin_password(
    admin_id: int,
    new_password: str,
    confirm_password: str,
    *,
    actor: str,
    ip_address: str | None = None,
) -> tuple[bool, str]:
    """Resetea la contraseña de OTRO admin (no la propia)."""
    target = db.session.get(AdminUser, admin_id)
    if not target:
        return False, "Administrador no encontrado."

    if not new_password or not confirm_password:
        return False, "Nueva contraseña y confirmación son obligatorias."

    if len(new_password) < MIN_PASSWORD_LENGTH:
        return False, f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."

    if new_password != confirm_password:
        return False, "Las contraseñas no coinciden."

    target.set_password(new_password)
    db.session.commit()

    audit_service.log_action(
        action="admin_password_reset",
        actor=actor,
        detail=f"Contraseña reseteada para administrador '{target.username}'",
        level="info",
        ip_address=ip_address,
    )
    logger.info("Admin '%s' reseteó la contraseña de '%s'", actor, target.username)
    return True, f"Contraseña de '{target.username}' actualizada correctamente."
