"""
UserService — business logic for OverleafUser queries.
"""
from datetime import datetime, timezone

from app.extensions import db
from app.models.overleaf_user import OverleafUser

_SORT_KEYS = {
    "email":     lambda u: (u.email or "").lower(),
    "nombre":    lambda u: (u.display_name or "").lower(),
    "roles":     lambda u: not u.is_admin,   # admins first on asc
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
    """Return a filtered and sorted list of users for the live-search endpoint."""
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
    """Return paginated OverleafUser queryset, optionally filtered by search term."""
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


def set_user_quota(user_id: int, max_bytes) -> tuple:
    """
    Assign a storage quota to a user.

    max_bytes: integer bytes, or None to remove the quota limit.
    Returns (success: bool, message: str).
    """
    user = OverleafUser.query.get(user_id)
    if not user:
        return False, "Usuario no encontrado."

    if max_bytes is not None and max_bytes < 0:
        return False, "La cuota no puede ser negativa."

    user.max_quota_bytes = max_bytes
    db.session.commit()
    return True, "Cuota actualizada correctamente."
