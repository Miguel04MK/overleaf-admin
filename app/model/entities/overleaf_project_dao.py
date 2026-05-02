"""
OverleafProjectDao — low-level DB access for OverleafProject.
"""
from app.model.entities.overleaf_project import OverleafProject
from app.config.extensions import db


def find_by_overleaf_id(overleaf_id: str) -> OverleafProject | None:
    return OverleafProject.query.filter_by(overleaf_id=overleaf_id).first()


def count_all() -> int:
    return OverleafProject.query.count()


def count_by_owner(owner_id: int) -> int:
    return OverleafProject.query.filter_by(owner_id=owner_id).count()
