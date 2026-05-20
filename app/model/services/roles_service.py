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


def _role_counts() -> list[tuple]:
    """Return [(role_id, role_name, user_count), …] including null-role users
    counted under the default role."""
    from sqlalchemy import func
    rows = (
        db.session.query(OverleafUser.role_id, Role.name, func.count(OverleafUser.id))
        .join(Role, Role.id == OverleafUser.role_id)
        .filter(OverleafUser.role_id.isnot(None))
        .group_by(OverleafUser.role_id, Role.name)
        .all()
    )
    counts = {rid: (name, cnt) for rid, name, cnt in rows}
    default = get_default_role()
    if default:
        null_count = OverleafUser.query.filter(OverleafUser.role_id.is_(None)).count()
        if null_count:
            name, prev = counts.get(default.id, (default.name, 0))
            counts[default.id] = (name, prev + null_count)
    return [(rid, name, cnt) for rid, (name, cnt) in counts.items()]


def get_role_stats() -> dict[str, int]:
    """Return {role_name: user_count} for all roles (keyed by name for charts)."""
    return {name: cnt for _, name, cnt in _role_counts()}


def get_role_stats_by_id() -> dict[int, int]:
    """Return {role_id: user_count} for all roles (keyed by ID for lookups)."""
    return {rid: cnt for rid, _, cnt in _role_counts()}


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


def get_quota_alerts_per_role() -> dict[int, dict]:
    """
    Returns {role_id: {near_limit, exceeded, avg_used_bytes}} for all roles.
    near_limit:     users using 80–99 % of their individual quota.
    exceeded:       users using ≥ 100 % of their individual quota.
    avg_used_bytes: average storage used across ALL users in the role.
    NULL role_id rows (default-role users) are merged into the default role.
    """
    from sqlalchemy import func
    from app.model.entities.overleaf_project import OverleafProject

    proj_sq = (
        db.session.query(
            OverleafProject.owner_id.label("uid"),
            func.coalesce(func.sum(OverleafProject.size_bytes), 0).label("used_bytes"),
        )
        .group_by(OverleafProject.owner_id)
        .subquery()
    )

    # Fetch ALL users (with or without quota) to compute avg_used_bytes
    rows = (
        db.session.query(
            OverleafUser.role_id,
            func.coalesce(proj_sq.c.used_bytes, 0).label("used_bytes"),
            OverleafUser.max_quota_bytes,
        )
        .outerjoin(proj_sq, proj_sq.c.uid == OverleafUser.id)
        .all()
    )

    buckets: dict = {}
    for role_id, used_bytes, max_quota in rows:
        b = buckets.setdefault(role_id, {
            "total_used": 0, "count": 0, "near_limit": 0, "exceeded": 0
        })
        b["count"]      += 1
        b["total_used"] += (used_bytes or 0)
        if max_quota and max_quota > 0:
            pct = (used_bytes or 0) / max_quota * 100
            if pct >= 100:
                b["exceeded"] += 1
            elif pct >= 80:
                b["near_limit"] += 1

    raw = {
        rid: {
            "near_limit":     b["near_limit"],
            "exceeded":       b["exceeded"],
            "avg_used_bytes": b["total_used"] // b["count"] if b["count"] else 0,
        }
        for rid, b in buckets.items()
    }

    # Merge NULL role_id (default-role users) into the default role bucket
    default = get_default_role()
    if default and None in raw:
        null_d = raw.pop(None)
        def_d  = raw.setdefault(default.id, {
            "near_limit": 0, "exceeded": 0, "avg_used_bytes": 0
        })
        def_d["near_limit"] += null_d["near_limit"]
        def_d["exceeded"]   += null_d["exceeded"]
        if def_d["avg_used_bytes"] == 0:
            def_d["avg_used_bytes"] = null_d["avg_used_bytes"]

    return raw


def search_users_for_role(role_id: int, q: str, limit: int = 15) -> list[dict]:
    """Search all users matching name/email, marking whether they have role_id.

    Returns a list of dicts with keys:
        id, name, email, current_role, has_role (bool)
    """
    from sqlalchemy import or_

    default_role = get_default_role()
    is_default   = default_role is not None and default_role.id == role_id

    term   = f"%{q}%"
    users  = (
        OverleafUser.query
        .filter(
            or_(
                OverleafUser.email.ilike(term),
                OverleafUser.first_name.ilike(term),
                OverleafUser.last_name.ilike(term),
            )
        )
        .order_by(OverleafUser.email)
        .limit(limit)
        .all()
    )

    results = []
    for u in users:
        effective_role = u.role or default_role
        # "has this role" means the user's effective role IS role_id
        if is_default:
            has_role = u.role_id is None or u.role_id == role_id
        else:
            has_role = u.role_id == role_id
        results.append({
            "id":           u.id,
            "name":         u.display_name,
            "email":        u.email or "",
            "current_role": effective_role.name if effective_role else "sin rol",
            "has_role":     has_role,
        })
    return results


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

        try:
            from app.model.services import alerts_service
            alerts_service.check_user_quota(user_id)
            alerts_service.check_user_project_limit(user_id)
        except Exception as exc:
            logger.warning(
                "Role assigned to user %s but alert recheck failed: %s", user_id, exc
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

        try:
            from app.model.services import alerts_service
            alerts_service.check_user_quota(user_id)
            alerts_service.check_user_project_limit(user_id)
        except Exception as exc:
            logger.warning(
                "Role removed from user %s but alert recheck failed: %s", user_id, exc
            )

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
    """Update role description and quota defaults.

    Propagation: users in this role whose ``max_quota_bytes`` equals the OLD
    role quota are migrated to the new value (custom overrides are preserved).
    Returns a Spanish message that mentions the number of users updated so the
    caller can flash it to the user.
    """
    role = db.session.get(Role, role_id)
    if not role:
        return False, "Rol no encontrado."
    try:
        old_quota = role.storage_quota_bytes
        old_max_projects = role.max_projects

        if description is not None:
            role.description = description.strip() or None
        role.storage_quota_bytes = storage_quota_bytes
        role.max_projects        = max_projects
        role.updated_at = datetime.now(timezone.utc)

        # Propagate the new defaults to users who were inheriting the old ones.
        # Done in a single bulk UPDATE — no N+1.
        users_updated = 0
        if old_quota != storage_quota_bytes:
            from app.model.entities.overleaf_user import OverleafUser
            q = OverleafUser.query.filter(OverleafUser.role_id == role.id)
            if old_quota is None:
                q = q.filter(OverleafUser.max_quota_bytes.is_(None))
            else:
                q = q.filter(OverleafUser.max_quota_bytes == old_quota)
            users_updated = q.update(
                {"max_quota_bytes": storage_quota_bytes},
                synchronize_session=False,
            )

        db.session.commit()

        # Re-evaluate quota / project-limit alerts for everyone in this role,
        # since both thresholds may have shifted. This is event-driven (single
        # explicit call), NOT something the dashboard does on every render.
        try:
            from app.model.services import alerts_service
            alerts_service.check_role_users(role.id)
        except Exception as exc:
            logger.warning(
                "Role %s updated but alert recheck failed: %s", role.id, exc
            )

        if users_updated:
            return True, (
                f"Configuración de «{role.name}» actualizada. "
                f"{users_updated} usuario(s) migrados a la nueva cuota."
            )
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
