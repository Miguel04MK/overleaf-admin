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

    # Importante: usar el rol EFECTIVO (con fallback al rol por defecto), no
    # `user.role` directo. Un usuario con role_id=NULL aparece en la UI como
    # el rol por defecto (alumno) gracias a get_effective_role(); si miráramos
    # sólo user.role, los logs registrarían "Sin rol → X" cuando en realidad
    # el usuario tenía el rol por defecto. Esto pasa cuando:
    #   - El usuario se sincroniza desde Mongo (sync no asigna rol explícito).
    #   - Un rol anterior fue borrado (ondelete=SET NULL) — aunque
    #     delete_role intenta reasignar, usuarios huérfanos previos pueden
    #     tener NULL.
    explicit_old = user.role  # rol explícitamente asignado (puede ser None)
    effective_old = explicit_old or get_default_role()  # lo que la UI muestra

    # Mismo rol efectivo → rechazar
    if effective_old and effective_old.id == new_role.id:
        return False, f"El usuario ya tiene el rol «{new_role.name}»."

    # Safety: prevent removing the last admin (comprueba sobre el efectivo)
    if effective_old and effective_old.name == "admin" and new_role.name != "admin":
        admin_count = OverleafUser.query.join(Role).filter(Role.name == "admin").count()
        if admin_count <= 1:
            return False, (
                "No es posible cambiar el rol: este es el último administrador activo."
            )

    # "assigned" sólo si NO había rol efectivo (caso muy raro: no hay default).
    # En la práctica, casi siempre será "changed".
    action = "assigned" if effective_old is None else "changed"

    try:
        # Log usa el rol EFECTIVO en role_from para reflejar lo que el usuario
        # tenía visiblemente, no el campo crudo de DB.
        log = RoleChangeLog(
            user_id=user_id,
            role_from_id=effective_old.id   if effective_old else None,
            role_from_name=effective_old.name if effective_old else None,
            role_to_id=new_role.id,
            role_to_name=new_role.name,
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

        old_name = effective_old.name if effective_old else "sin rol"
        logger.info(
            "Role change: user=%s %s→%s by %s", user.email, old_name, new_role.name, actor
        )

        # AuditLog (categoría "Cambios de rol" en /auditoria/).
        try:
            from app.model.services.admin import admin_service as audit_service
            audit_service.log_action(
                action=("role_assigned" if action == "assigned" else "role_changed"),
                actor=actor,
                detail=(
                    f"Usuario «{user.email or user.id}»: "
                    f"{old_name} → {new_role.name}"
                ),
                level="info",
            )
        except Exception as exc:
            logger.warning("AuditLog of role change failed for user %s: %s", user_id, exc)

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
            role_from_name=old_role.name,
            role_to_id=default.id,
            role_to_name=default.name,
            action="removed",
            changed_by=actor,
            changed_at=datetime.now(timezone.utc),
            reason=reason or None,
        )
        db.session.add(log)

        user.role_id = default.id
        user.max_quota_bytes = default.storage_quota_bytes

        db.session.commit()

        # AuditLog (categoría "Cambios de rol" en /auditoria/).
        try:
            from app.model.services.admin import admin_service as audit_service
            audit_service.log_action(
                action="role_removed",
                actor=actor,
                detail=(
                    f"Usuario «{user.email or user.id}»: "
                    f"{old_role.name} → {default.name} (retirado)"
                ),
                level="info",
            )
        except Exception as exc:
            logger.warning("AuditLog of role remove failed for user %s: %s", user_id, exc)

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
    is_default: bool | None = None,
) -> tuple[bool, str]:
    """Update role description, quota defaults and (opcional) "rol por defecto".

    Propagation: users in this role whose ``max_quota_bytes`` equals the OLD
    role quota are migrated to the new value (custom overrides are preserved).
    Returns a Spanish message that mentions the number of users updated so the
    caller can flash it to the user.

    Regla del rol por defecto:
      - Si is_default es True y este rol NO era default → desmarca el anterior.
      - Si is_default es False y este rol ERA el default → rechaza
        (siempre debe haber un rol por defecto).
      - Si is_default es None → no se toca este campo.
    """
    role = db.session.get(Role, role_id)
    if not role:
        return False, "Rol no encontrado."

    # Validación de "rol por defecto" antes de tocar nada en DB.
    if is_default is not None:
        if not is_default and role.is_default:
            return False, (
                "No puedes quitarle el rol por defecto a «" + role.name + "». "
                "Marca otro rol como por defecto para cambiar esta configuración."
            )

    try:
        old_quota = role.storage_quota_bytes
        old_max_projects = role.max_projects

        # Cambio de "rol por defecto": desmarcar el anterior si procede.
        if is_default is True and not role.is_default:
            db.session.query(Role).filter(Role.is_default.is_(True)).update(
                {"is_default": False}, synchronize_session=False,
            )
            role.is_default = True

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


# ── Create ────────────────────────────────────────────────────────────────────

# Paleta de colores aceptados al crear un rol nuevo (clases de Bootstrap)
ROLE_COLOR_CHOICES: list[str] = [
    "primary", "info", "success", "warning", "danger", "secondary", "dark",
]


def role_name_exists(name: str) -> bool:
    """True si ya existe un rol con ese nombre (comparación case-insensitive)."""
    n = (name or "").strip().lower()
    if not n:
        return False
    return Role.query.filter(Role.name == n).first() is not None


def create_role(
    *,
    name: str,
    description: str | None,
    storage_quota_bytes: int | None,
    max_projects: int | None,
    is_default: bool = False,
    color: str = "secondary",
    actor: str = "system",
) -> tuple[bool, str, Role | None]:
    """Crea un Role nuevo. Devuelve (ok, mensaje, role|None).

    Validaciones:
      - name obligatorio, único (case-insensitive)
      - storage_quota_bytes >= 0 o None (ilimitado)
      - max_projects >= 1 o None (ilimitado)
      - color en ROLE_COLOR_CHOICES
      - is_default=True desmarca el anterior automáticamente
    Registra AuditLog `role_create` y devuelve el Role para que el caller
    pueda redirigir a su detalle si quiere.
    """
    n = (name or "").strip().lower()

    if not n:
        return False, "El nombre del rol es obligatorio.", None
    if len(n) > 64:
        return False, "El nombre no puede tener más de 64 caracteres.", None

    if role_name_exists(n):
        return False, f"Ya existe un rol con el nombre «{n}».", None

    if storage_quota_bytes is not None and storage_quota_bytes < 0:
        return False, "La cuota no puede ser negativa.", None

    if max_projects is not None and max_projects < 1:
        return False, "El límite de proyectos debe ser >= 1 (o ilimitado).", None

    if color not in ROLE_COLOR_CHOICES:
        color = "secondary"

    try:
        # Si marcamos como default, desmarcar el anterior (constraint lógico).
        if is_default:
            db.session.query(Role).filter(Role.is_default.is_(True)).update(
                {"is_default": False}, synchronize_session=False,
            )

        role = Role(
            name=n,
            description=(description or "").strip() or None,
            storage_quota_bytes=storage_quota_bytes,
            max_projects=max_projects,
            is_default=bool(is_default),
            color=color,
        )
        db.session.add(role)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Error creando rol '%s': %s", n, exc)
        return False, "Error al crear el rol.", None

    # Auditoría — sólo AuditLog global; RoleChangeLog está reservado para
    # cambios de rol de usuarios (assigned/changed/removed).
    try:
        from app.model.services.admin import admin_service as audit_service
        audit_service.log_action(
            action="role_create",
            actor=actor,
            detail=f"Creado nuevo rol: {n}",
            level="info",
        )
    except Exception as exc:
        logger.warning("Rol '%s' creado pero AuditLog falló: %s", n, exc)

    logger.info("Admin '%s' creó el rol '%s'", actor, n)
    return True, f"Rol «{n}» creado correctamente.", role


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_role(
    role_id: int,
    *,
    actor: str = "system",
) -> tuple[bool, str]:
    """Elimina un rol.

    Reglas:
      - El rol debe existir.
      - No se puede eliminar el rol por defecto (la plataforma necesita uno).
      - Si el rol tiene usuarios asignados, se REASIGNAN automáticamente al
        rol por defecto antes de borrar. Por cada usuario afectado se crea
        un `RoleChangeLog` (action='changed') con la razón explícita.
        Si la cuota del usuario coincidía con la del rol borrado, también
        se migra a la del nuevo rol por defecto.
      - Si el usuario no tiene rol por defecto configurado y hay usuarios
        que reasignar, se aborta (no hay donde mandarlos).
    Devuelve (ok, mensaje) y registra `AuditLog` con action='role_delete'.
    """
    role = db.session.get(Role, role_id)
    if not role:
        return False, "Rol no encontrado."

    if role.is_default:
        return False, (
            f"No puedes eliminar «{role.name}» porque es el rol por defecto. "
            "Marca otro rol como por defecto antes de eliminarlo."
        )

    default = get_default_role()
    n_users = role.users.count()
    if n_users > 0 and default is None:
        return False, (
            "No hay un rol por defecto configurado al que reasignar los usuarios. "
            "Configura uno antes de eliminar este rol."
        )

    try:
        role_name = role.name
        old_quota = role.storage_quota_bytes

        # Reasignar usuarios al rol por defecto antes de borrar.
        if n_users > 0:
            users_to_reassign = OverleafUser.query.filter_by(role_id=role.id).all()
            for user in users_to_reassign:
                # Log primero (todavía existe la FK al rol antiguo).
                log = RoleChangeLog(
                    user_id=user.id,
                    role_from_id=role.id,
                    role_from_name=role_name,
                    role_to_id=default.id,
                    role_to_name=default.name,
                    action="changed",
                    changed_by=actor,
                    changed_at=datetime.now(timezone.utc),
                    reason=f"Reasignado automáticamente al borrar el rol «{role_name}»",
                )
                db.session.add(log)
                user.role_id = default.id
                # Si la cuota del usuario heredaba la del rol viejo, migrarla
                # también a la del nuevo rol por defecto (overrides personalizados
                # se respetan).
                if user.max_quota_bytes == old_quota:
                    user.max_quota_bytes = default.storage_quota_bytes
            # Flush para que los RoleChangeLog se persistan ANTES del DELETE.
            db.session.flush()

        db.session.delete(role)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Error eliminando rol %s: %s", role_id, exc)
        return False, "Error al eliminar el rol."

    # ── Auditoría global ───────────────────────────────────────────
    detail = f"Rol eliminado: {role_name}"
    if n_users > 0:
        detail += (
            f" ({n_users} usuario{'s' if n_users != 1 else ''} reasignado"
            f"{'s' if n_users != 1 else ''} al rol por defecto «{default.name}»)"
        )
    try:
        from app.model.services.admin import admin_service as audit_service
        audit_service.log_action(
            action="role_delete",
            actor=actor,
            detail=detail,
            level="info",
        )
    except Exception as exc:
        logger.warning("Rol '%s' eliminado pero AuditLog falló: %s", role_name, exc)

    # ── Recalcular alertas para los usuarios reasignados ───────────
    if n_users > 0:
        try:
            from app.model.services import alerts_service
            alerts_service.check_role_users(default.id)
        except Exception as exc:
            logger.warning(
                "Rol '%s' eliminado pero recalculación de alertas falló: %s",
                role_name, exc,
            )

    logger.info(
        "Admin '%s' eliminó el rol '%s' (reasignó %d usuario(s))",
        actor, role_name, n_users,
    )

    msg = f"Rol «{role_name}» eliminado correctamente."
    if n_users > 0:
        msg += (
            f" {n_users} usuario{'s' if n_users != 1 else ''} "
            f"reasignado{'s' if n_users != 1 else ''} a «{default.name}»."
        )
    return True, msg


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
