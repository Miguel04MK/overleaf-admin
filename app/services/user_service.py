"""
UserService — business logic for OverleafUser queries.
"""
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


def get_user_by_id(user_id: int) -> OverleafUser | None:
    return OverleafUser.query.get(user_id)
