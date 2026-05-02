"""
RolesService — business logic for platform role management.

Roles are administrative (not synced from Overleaf).
Changing a user's role also updates their storage quota automatically.
"""
import logging
from datetime import datetime, timezone

from app.config.extensions import db
from app.model.entities.role import Role, ROLE_PRESETS
from app.model.entities.role_change_log import RoleChangeLog
from app.model.entities.overleaf_user import OverleafUser

logger = logging.getLogger(__name__)


# ── Queries ───────────────────────────────────────────────────────────────────

def get_all_roles() -> list[Role]:
    return Role.query.order_by(Role.is_default.desc(), Role.name).all()


def get_role_by_id(role_id: int) -> Role | None:
    return db.session.get(Role, role_id)


def get_role_by_name(name: str) -> Role | None:
    return Role.query.filter_by(name=name.lower()).first()


def get_default_role() -> Role | None:
    return Role.query.filter_by(is_default=True).first()


def get_effective_role(user: OverleafUser) -> Role | None:
    """Return the user's assigned role, or the default role if none assigned."""
    return user.role or get_default_role()


def get_role_stats() -> dict[int, int]:
    """Return {role_id: user_count} for all roles.
    Users with NULL role_id are counted under the default role."""
    from sqlalchemy import func
    rows = (
        db.session.query(OverleafUser.role_id, func.count(OverleafUser.id))
        .filter(OverleafUser.role_id.isnot(None))
        .group_by(OverleafUser.role_id)
        .all()
    )
    stats = {role_id: cnt for role_id, cnt in rows}
    default = get_default_role()
    if default:
        null_count = OverleafUser.query.filter(OverleafUser.role_id.is_(None)).count()
        if null_count:
            stats[default.id] = stats.get(default.id, 0) + null_count
    return stats


def get_users_stats_for_role(role_id: int) -> list[dict]:
    """
    Return all users with this role, with storage usage and project count
    resolved in a single SQL query (no N+1).
    For the default role, also includes users with NULL role_id.
    Used for client-side simulation.
    """
    from sqlalchemy import func, or_
    from app.model.entities.overleaf_project import OverleafProject

    default_role = get_default_role()
    is_default = default_role is not None and default_role.id == role_id

    proj_sq = (
        db.session.query(
            OverleafProject.owner_id.label("uid"),
            func.coalesce(func.sum(OverleafProject.size_bytes), 0).label("used_bytes"),
            func.count(OverleafProject.id).label("proj_count"),
        )
        .group_by(OverleafProject.owner_id)
        .subquery()
    )

    base_q = (
        db.session.query(
            OverleafUser.id,
            OverleafUser.first_name,
            OverleafUser.last_name,
            OverleafUser.email,
            func.coalesce(proj_sq.c.used_bytes, 0).label("used_bytes"),
            func.coalesce(proj_sq.c.proj_count, 0).label("proj_count"),
        )
        .outerjoin(proj_sq, proj_sq.c.uid == OverleafUser.id)
    )

    if is_default:
        base_q = base_q.filter(
            or_(OverleafUser.role_id == role_id, OverleafUser.role_id.is_(None))
        )
    else:
        base_q = base_q.filter(OverleafUser.role_id == role_id)

    rows = base_q.order_by(OverleafUser.email).all()
    result = []
    for r in rows:
        parts = [r.first_name, r.last_name]
        name  = " ".join(p for p in parts if p) or r.email or str(r.id)
        result.append({
            "id":             r.id,
            "name":           name,
            "email":          r.email or "",
            "used_bytes":     int(r.used_bytes or 0),
            "projects_count": int(r.proj_count  or 0),
        })
    return result


def get_users_for_role(role_id: int, page: int = 1, per_page: int = 20):
    """Paginated list of users with a specific role."""
    return (
        OverleafUser.query
        .filter_by(role_id=role_id)
        .order_by(OverleafUser.email)
        .paginate(page=page, per_page=per_page, error_out=False)
    )


def get_role_change_logs(
    user_id: int | None = None,
    role_id: int | None = None,
    action: str | None = None,
    page: int = 1,
    per_page: int = 30,
):
    """Paginated audit log, optionally filtered."""
    q = RoleChangeLog.query.options(
        db.joinedload(RoleChangeLog.user),
        db.joinedload(RoleChangeLog.role_from),
        db.joinedload(RoleChangeLog.role_to),
    )
    if user_id:
        q = q.filter(RoleChangeLog.user_id == user_id)
    if role_id:
        q = q.filter(
            (RoleChangeLog.role_from_id == role_id) |
            (RoleChangeLog.role_to_id   == role_id)
        )
    if action:
        q = q.filter(RoleChangeLog.action == action)
    return q.order_by(RoleChangeLog.changed_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )


# ── Mutations ─────────────────────────────────────────────────────────────────

def assign_role(
    user_id: int,
    role_id: int,
    actor: str,
    reason: str | None = None,
) -> tuple[bool, str]:
    """
    Assign or change a user's role.
    Also applies the new role's storage quota.
    Returns (success, message).
    """
    user = db.session.get(OverleafUser, user_id)
    if not user:
        return False, "Usuario no encontrado."

    new_role = db.session.get(Role, role_id)
    if not new_role:
        return False, "Rol no encontrado."

    old_role = user.role  # may be None
    if old_role and old_role.id == new_role.id:
        return False, f"El usuario ya tiene el rol «{new_role.name}»."

    # Safety: prevent removing the last admin
    if old_role and old_role.name == "admin" and new_role.name != "admin":
        admin_count = OverleafUser.query.join(Role).filter(Role.name == "admin").count()
        if admin_count <= 1:
            return False, (
                "No es posible cambiar el rol: este es el último administrador activo."
            )

    action = "assigned" if old_role is None else "changed"

    try:
        # Log the change
        log = RoleChangeLog(
            user_id=user_id,
            role_from_id=old_role.id if old_role else None,
            role_to_id=new_role.id,
            action=action,
            changed_by=actor,
            changed_at=datetime.now(timezone.utc),
            reason=reason or None,
        )
        db.session.add(log)

        # Update user role
        user.role_id = new_role.id

        # Apply role quota
        user.max_quota_bytes = new_role.storage_quota_bytes

        db.session.commit()

        old_name = old_role.name if old_role else "sin rol"
        logger.info(
            "Role change: user=%s %s→%s by %s", user.email, old_name, new_role.name, actor
        )
        return True, f"Rol cambiado de «{old_name}» a «{new_role.name}»."

    except Exception as exc:
        db.session.rollback()
        logger.error("Error assigning role to user %s: %s", user_id, exc)
        return False, "Error al cambiar el rol. Inténtalo de nuevo."


def remove_role(
    user_id: int,
    actor: str,
    reason: str | None = None,
) -> tuple[bool, str]:
    """
    Remove explicit role from user — resets to default role.
    Cannot leave a user without a role (default is always applied).
    """
    user = db.session.get(OverleafUser, user_id)
    if not user:
        return False, "Usuario no encontrado."

    default = get_default_role()
    if not default:
        return False, "No hay un rol por defecto configurado."

    old_role = user.role
    if old_role is None or old_role.id == default.id:
        return False, f"El usuario ya tiene el rol por defecto («{default.name}»)."

    # Safety: prevent removing the last admin
    if old_role.name == "admin":
        admin_count = OverleafUser.query.join(Role).filter(Role.name == "admin").count()
        if admin_count <= 1:
            return False, (
                "No es posible retirar el rol: este es el último administrador activo."
            )

    try:
        log = RoleChangeLog(
            user_id=user_id,
            role_from_id=old_role.id,
            role_to_id=default.id,
            action="removed",
            changed_by=actor,
            changed_at=datetime.now(timezone.utc),
            reason=reason or None,
        )
        db.session.add(log)

        user.role_id = default.id
        user.max_quota_bytes = default.storage_quota_bytes

        db.session.commit()
        return True, f"Rol retirado. Usuario resetado a «{default.name}»."

    except Exception as exc:
        db.session.rollback()
        logger.error("Error removing role from user %s: %s", user_id, exc)
        return False, "Error al retirar el rol."


def update_role_config(
    role_id: int,
    description: str | None,
    storage_quota_bytes: int | None,
    max_projects: int | None,
) -> tuple[bool, str]:
    """Update role description and quota defaults (does NOT retroactively change users)."""
    role = db.session.get(Role, role_id)
    if not role:
        return False, "Rol no encontrado."
    try:
        if description is not None:
            role.description = description.strip() or None
        role.storage_quota_bytes = storage_quota_bytes
        role.max_projects        = max_projects
        role.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return True, f"Configuración de «{role.name}» actualizada."
    except Exception as exc:
        db.session.rollback()
        logger.error("Error updating role %s: %s", role_id, exc)
        return False, "Error al guardar los cambios."


# ── Seeding ───────────────────────────────────────────────────────────────────

def seed_default_roles() -> None:
    """
    Ensure the three default roles exist in the DB.
    Safe to call multiple times (idempotent).
    """
    for name, preset in ROLE_PRESETS.items():
        if not Role.query.filter_by(name=name).first():
            role = Role(name=name, **preset)
            db.session.add(role)
            logger.info("Seeded role: %s", name)
    db.session.commit()
