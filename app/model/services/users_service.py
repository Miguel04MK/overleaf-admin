"""
UsersService — business logic for OverleafUser queries.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

from sqlalchemy import func, case, cast, Numeric, asc as sa_asc, desc as sa_desc

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.project_member import ProjectMember
from app.model.entities.role import Role


# ── Subqueries used for sorting / filtering without N+1 ──────────────────────

def _projects_count_subq():
    """Correlated subquery: number of owned projects per user."""
    return (
        db.session.query(func.count(OverleafProject.id))
        .filter(OverleafProject.owner_id == OverleafUser.id)
        .correlate(OverleafUser)
        .scalar_subquery()
        .label("projects_count")
    )


def _quota_used_subq():
    """Correlated subquery: total size_bytes of owned projects per user."""
    return (
        db.session.query(func.coalesce(func.sum(OverleafProject.size_bytes), 0))
        .filter(OverleafProject.owner_id == OverleafUser.id)
        .correlate(OverleafUser)
        .scalar_subquery()
        .label("quota_used")
    )


def _quota_pct_expr(quota_used):
    """SQL expression: quota percentage (NULL when no limit)."""
    return case(
        (OverleafUser.max_quota_bytes.is_(None), None),
        (OverleafUser.max_quota_bytes == 0, None),
        else_=func.round(cast(quota_used * 100.0 / OverleafUser.max_quota_bytes, Numeric), 1),
    ).label("quota_pct")


# ── Server-side paginated search ──────────────────────────────────────────────

def search_users_paginated(
    *,
    q: str | None = None,
    sort: str = "email",
    order: str = "asc",
    page: int = 1,
    per_page: int = 20,
    filters: list[dict] | None = None,
):
    """
    Return a dict with {total, pages, page, has_next, has_prev, users: [serialized]}.
    All filtering, sorting and pagination happens in SQL.
    """
    projects_count = _projects_count_subq()
    quota_used = _quota_used_subq()
    quota_pct = _quota_pct_expr(quota_used)

    query = (
        db.session.query(
            OverleafUser,
            projects_count,
            quota_used,
            quota_pct,
        )
    )

    # ── Text search ───────────────────────────────────────────────────────────
    if q:
        term = f"%{q}%"
        query = query.filter(
            OverleafUser.email.ilike(term)
            | OverleafUser.first_name.ilike(term)
            | OverleafUser.last_name.ilike(term)
        )

    # ── Filters ───────────────────────────────────────────────────────────────
    if filters:
        now = datetime.now(timezone.utc)
        for f in filters:
            ftype = f.get("type")
            fop = f.get("op")
            fval = f.get("val")

            if ftype == "projects":
                v = int(fval) if fval is not None else 0
                if fop == "gte":
                    query = query.having(projects_count >= v)
                elif fop == "eq":
                    query = query.having(projects_count == v)
                elif fop == "lte":
                    query = query.having(projects_count <= v)

            elif ftype == "quota":
                if fop == "exceeded":
                    query = query.filter(
                        OverleafUser.max_quota_bytes.isnot(None),
                        OverleafUser.max_quota_bytes > 0,
                    ).having(quota_pct >= 100)
                elif fop == "unlimited":
                    query = query.filter(OverleafUser.max_quota_bytes.is_(None))
                else:
                    v = float(fval) if fval is not None else 0
                    query = query.filter(
                        OverleafUser.max_quota_bytes.isnot(None),
                        OverleafUser.max_quota_bytes > 0,
                    )
                    if fop == "gte":
                        query = query.having(quota_pct >= v)
                    elif fop == "lte":
                        query = query.having(quota_pct <= v)

            elif ftype == "role":
                if fval == "none":
                    query = query.filter(OverleafUser.role_id.is_(None))
                else:
                    try:
                        rid = int(fval)
                        query = query.filter(OverleafUser.role_id == rid)
                    except (TypeError, ValueError):
                        pass

            elif ftype == "access":
                if fval == "never":
                    query = query.filter(OverleafUser.last_login_at.is_(None))
                elif fval == "inactive":
                    cutoff = now - timedelta(days=90)
                    query = query.filter(
                        (OverleafUser.last_login_at.is_(None))
                        | (OverleafUser.last_login_at < cutoff)
                    )
                else:
                    days_map = {"1d": 1, "7d": 7, "30d": 30}
                    days = days_map.get(fval)
                    if days:
                        cutoff = now - timedelta(days=days)
                        query = query.filter(OverleafUser.last_login_at >= cutoff)

    # ── Group by (needed for HAVING clauses) ──────────────────────────────────
    query = query.group_by(OverleafUser.id)

    # ── Sorting ───────────────────────────────────────────────────────────────
    # Subquery escalar para que el ORDER BY de "roles" use el NOMBRE del rol
    # (alfabético) en lugar de `is_admin` (booleano), que es el orden que el
    # usuario espera al pulsar la cabecera de la columna.
    from sqlalchemy import select as sa_select
    role_name_for_user = (
        sa_select(Role.name)
        .where(Role.id == OverleafUser.role_id)
        .correlate(OverleafUser)
        .scalar_subquery()
    )
    sort_map = {
        "email":     OverleafUser.email,
        "nombre":    func.concat(
                         func.coalesce(OverleafUser.first_name, ''),
                         ' ',
                         func.coalesce(OverleafUser.last_name, ''),
                     ),
        "roles":     role_name_for_user,
        "proyectos": projects_count,
        "cuota":     quota_pct,
        "registro":  OverleafUser.signup_date,
    }
    sort_col = sort_map.get(sort, OverleafUser.email)
    if order == "desc":
        query = query.order_by(sa_desc(sort_col).nullslast())
    else:
        query = query.order_by(sa_asc(sort_col).nullslast())

    # ── Count + paginate ──────────────────────────────────────────────────────
    # .count() wraps the grouped query in a subquery and counts rows — correct.
    total = query.order_by(None).count()
    pages = max(1, -(-total // per_page))  # ceil div
    page = max(1, min(page, pages))

    rows = query.offset((page - 1) * per_page).limit(per_page).all()

    # Batch-load roles para evitar N+1
    role_ids = {u.role_id for u, *_ in rows if u.role_id}
    roles_map: dict[int, Role] = (
        {r.id: r for r in Role.query.filter(Role.id.in_(role_ids)).all()}
        if role_ids else {}
    )

    users = []
    for user, proj_count, q_used, q_pct in rows:
        users.append(_serialize_row(user, proj_count, q_used, q_pct,
                                    roles_map.get(user.role_id)))

    return {
        "total": total,
        "pages": pages,
        "page": page,
        "has_next": page < pages,
        "has_prev": page > 1,
        "users": users,
    }


def _fmt_bytes(n) -> str:
    if n is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _serialize_row(u, projects_count, quota_used, quota_pct, role: "Role | None" = None) -> dict:
    """Serialize a user row without N+1 queries — all aggregates pre-computed."""
    from flask import url_for

    # PostgreSQL aggregates return Decimal — convert to native Python types
    projects_count = int(projects_count) if projects_count is not None else 0
    quota_used = int(quota_used) if quota_used is not None else 0

    max_q = u.max_quota_bytes
    pct = float(quota_pct) if quota_pct is not None else None

    if pct is None:
        q_status = "secondary"
    elif pct >= 95:
        q_status = "danger"
    elif pct >= 80:
        q_status = "warning"
    else:
        q_status = "success"

    return {
        "id": u.id,
        "email": u.email or "",
        "display_name": u.display_name if u.display_name != u.email else "",
        "is_admin": u.is_admin,
        "role_id":    role.id    if role else None,
        "role_name":  role.name  if role else None,
        "role_color": role.color if role else None,
        "projects_count": projects_count,
        "quota_percent": pct,
        "quota_status": q_status,
        "quota_used_fmt": _fmt_bytes(quota_used),
        "quota_max_fmt": _fmt_bytes(max_q) if max_q else "Sin limite",
        "quota_exceeded": pct is not None and pct >= 100,
        "signup_date": u.signup_date.strftime("%d/%m/%Y") if u.signup_date else "",
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "detail_url": url_for("users.user_detail", user_id=u.id),
    }


# ── Legacy functions (kept for other callers) ────────────────────────────────

def search_users(
    q: str | None = None,
    sort: str = "email",
    order: str = "asc",
    limit: int = 500,
) -> list[OverleafUser]:
    """Legacy: returns ORM objects. Prefer search_users_paginated for list views."""
    _SORT_KEYS = {
        "email":     lambda u: (u.email or "").lower(),
        "nombre":    lambda u: (u.display_name or "").lower(),
        "roles":     lambda u: not u.is_admin,
        "proyectos": lambda u: u.projects_owned.count(),
        "cuota":     lambda u: u.quota_used_bytes,
        "registro":  lambda u: u.signup_date or datetime.min.replace(tzinfo=timezone.utc),
    }
    query = OverleafUser.query
    if q:
        term = f"%{q}%"
        query = query.filter(
            OverleafUser.email.ilike(term)
            | OverleafUser.first_name.ilike(term)
            | OverleafUser.last_name.ilike(term)
        )
    users = query.all()
    key_fn = _SORT_KEYS.get(sort, _SORT_KEYS["email"])
    users.sort(key=key_fn, reverse=(order == "desc"))
    return users[:limit]


def get_users_page(page: int, per_page: int, search: str | None = None):
    query = OverleafUser.query
    if search:
        term = f"%{search}%"
        query = query.filter(
            OverleafUser.email.ilike(term)
            | OverleafUser.first_name.ilike(term)
            | OverleafUser.last_name.ilike(term)
        )
    return query.order_by(OverleafUser.email).paginate(
        page=page, per_page=per_page, error_out=False
    )


def get_user_by_id(user_id: int):
    return OverleafUser.query.get(user_id)


def get_user_detail_data(user_id: int, projects_page: int = 1, per_page: int = 10) -> dict | None:
    user = get_user_by_id(user_id)
    if not user:
        return None

    now = datetime.now(timezone.utc)

    def _aware(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # All owned projects for charts/KPIs
    all_projects = user.projects_owned.order_by(OverleafProject.size_bytes.desc()).all()

    # Paginated projects for table
    projects_pagination = (
        user.projects_owned
        .order_by(OverleafProject.name)
        .paginate(page=projects_page, per_page=per_page, error_out=False)
    )

    # Collaborator names per project (current page only)
    members_map: dict[int, list[str]] = {}
    for proj in projects_pagination.items:
        names = [m.user.display_name for m in proj.members.all() if m.user]
        if names:
            members_map[proj.id] = names

    # Collaborations: projects where this user is a member (not owner)
    collab_memberships = user.memberships.filter(
        ProjectMember.role.in_(["collaborator", "read_only"])
    ).all()
    collab_projects = [m.project for m in collab_memberships if m.project]

    # KPI: active if last login within 90 days
    is_active = bool(
        user.last_login_at
        and (now - _aware(user.last_login_at)).days <= 90
    )

    # KPI: projects updated in last 30 days
    recent_activity = sum(
        1 for p in all_projects
        if p.last_updated_at and (now - _aware(p.last_updated_at)).days <= 30
    )

    # Chart 1 — storage by project (top 10)
    top_by_size = sorted(all_projects, key=lambda p: p.size_bytes or 0, reverse=True)[:10]
    chart_storage = {
        "labels": [(p.name or "Sin nombre")[:30] for p in top_by_size],
        "values": [round((p.size_bytes or 0) / 1_048_576, 2) for p in top_by_size],
    }

    # Chart 2 — projects created per month (last 12 months)
    monthly: dict[str, int] = defaultdict(int)
    for p in all_projects:
        if p.created_at:
            monthly[_aware(p.created_at).strftime("%b %y")] += 1
    month_labels, month_values = [], []
    for i in range(11, -1, -1):
        key = (now - timedelta(days=30 * i)).strftime("%b %y")
        month_labels.append(key)
        month_values.append(monthly.get(key, 0))
    chart_projects = {"labels": month_labels, "values": month_values}

    # Chart 3 — collaborations by size (top 10)
    collab_sorted = sorted(collab_projects, key=lambda p: p.size_bytes or 0, reverse=True)[:10]
    chart_collabs = {
        "labels": [(p.name or "Sin nombre")[:30] for p in collab_sorted],
        "values": [round((p.size_bytes or 0) / 1_048_576, 2) for p in collab_sorted],
    }

    collab_memberships_filtered = [m for m in collab_memberships if m.project]

    return {
        "user": user,
        "projects_pagination": projects_pagination,
        "collab_memberships": collab_memberships_filtered,
        "collab_count": len(collab_memberships_filtered),
        "members_map": members_map,
        "is_active": is_active,
        "recent_activity": recent_activity,
        "chart_storage": chart_storage,
        "chart_projects": chart_projects,
        "chart_collabs": chart_collabs,
    }


def set_user_quota(
    user_id: int,
    max_bytes,
    *,
    actor: str = "system",
) -> tuple:
    user = OverleafUser.query.get(user_id)
    if not user:
        return False, "Usuario no encontrado."

    if max_bytes is not None and max_bytes < 0:
        return False, "La cuota no puede ser negativa."

    old_bytes = user.max_quota_bytes
    user.max_quota_bytes = max_bytes
    db.session.commit()

    # AuditLog para que aparezca en /auditoria/ bajo la categoría "Cuotas".
    try:
        from app.model.services.admin import admin_service as audit_service
        def _fmt(b):
            if b is None:
                return "Ilimitada"
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if abs(b) < 1024:
                    return f"{b:.0f} {unit}"
                b /= 1024
            return f"{b:.1f} PB"
        detail = (
            f"Cuota del usuario «{user.email or user.id}» "
            f"actualizada: {_fmt(old_bytes)} → {_fmt(max_bytes)}"
        )
        audit_service.log_action(
            action="quota_change",
            actor=actor,
            detail=detail,
            level="info",
        )
    except Exception as exc:
        logger.warning("AuditLog of quota_change failed for user %s: %s", user_id, exc)

    try:
        from app.model.services import alerts_service
        alerts_service.check_user_quota(user_id)
    except Exception as exc:
        logger.warning("Quota updated for user %s but alert recheck failed: %s", user_id, exc)

    return True, "Cuota actualizada correctamente."
