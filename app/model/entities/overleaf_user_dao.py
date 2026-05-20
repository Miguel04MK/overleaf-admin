"""
OverleafUserDao — low-level DB access for OverleafUser.
"""
from app.model.entities.overleaf_user import OverleafUser
from app.config.extensions import db


def find_by_overleaf_id(overleaf_id: str) -> OverleafUser | None:
    return OverleafUser.query.filter_by(overleaf_id=overleaf_id).first()


def find_by_email(email: str) -> OverleafUser | None:
    return OverleafUser.query.filter_by(email=email).first()


def count_all() -> int:
    return OverleafUser.query.count()


def count_admins() -> int:
    return OverleafUser.query.filter_by(is_admin=True).count()
