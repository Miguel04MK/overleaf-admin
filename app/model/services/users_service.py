"""
UsersService — business logic for OverleafUser queries.
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.project_member import ProjectMember

_SORT_KEYS = {
    "email":     lambda u: (u.email or "").lower(),
    "nombre":    lambda u: (u.display_name or "").lower(),
    "roles":     lambda u: not u.is_admin,
    "proyectos": lambda u: u.projects_owned.count(),
    "cuota":     lambda u: u.quota_used_bytes,
    "registro":  lambda u: u.signup_date or datetime.min.replace(tzinfo=timezone.utc),
}


def search_users(
    q: str | None = None,
    sort: str = "email",
    order: str = "asc",
    limit: int = 500,
) -> list[OverleafUser]:
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


def set_user_quota(user_id: int, max_bytes) -> tuple:
    user = OverleafUser.query.get(user_id)
    if not user:
        return False, "Usuario no encontrado."

    if max_bytes is not None and max_bytes < 0:
        return False, "La cuota no puede ser negativa."

    user.max_quota_bytes = max_bytes
    db.session.commit()
    return True, "Cuota actualizada correctamente."
