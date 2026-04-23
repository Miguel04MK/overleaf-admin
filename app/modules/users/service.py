"""
UserService — business logic for OverleafUser queries.
"""
from app.extensions import db
from app.models.overleaf_user import OverleafUser


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
