"""
ProjectService — business logic for OverleafProject queries.
"""
from app.models.overleaf_project import OverleafProject


def get_projects_page(page: int, per_page: int, search: str | None = None):
    """Return paginated OverleafProject queryset, optionally filtered."""
    query = OverleafProject.query
    if search:
        term = f"%{search}%"
        query = query.filter(OverleafProject.name.ilike(term))
    return query.order_by(OverleafProject.name).paginate(
        page=page, per_page=per_page, error_out=False
    )


def get_project_by_id(project_id: int) -> OverleafProject | None:
    return OverleafProject.query.get(project_id)
