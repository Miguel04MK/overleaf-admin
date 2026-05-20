"""
ProjectsService — business logic for OverleafProject queries.

All list queries batch-load member data to avoid N+1 problems.
"""
from datetime import datetime, timezone

from sqlalchemy import func

from app.config.extensions import db
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.project_member import ProjectMember
from app.model.entities.project_sync_log import ProjectSyncLog

# ── Visual indicator thresholds ───────────────────────────────────────────────
SIZE_LARGE_BYTES = 10 * 1024 * 1024   # ≥ 10 MB  → badge "Grande"
INACTIVE_DAYS    = 90                  # ≥ 90 días → badge "Inactivo"
COLLAB_MANY      = 3                   # ≥ 3 miembros → badge "Colaborativo"


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_projects_list_data(
    page: int,
    per_page: int,
    search: str | None = None,
    owner_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    indicators: list[str] | None = None,
    sort: str = "last_updated_at",
    order: str = "desc",
) -> dict:
    """
    Returns paginated projects + pre-computed member counts, member names
    (for tooltips) and visual indicator flags — O(1) extra queries.
    """
    query = (
        OverleafProject.query
        .options(db.joinedload(OverleafProject.owner))
    )

    if search:
        term = f"%{search}%"
        query = query.filter(
            OverleafProject.name.ilike(term)
            | OverleafProject.overleaf_id.ilike(term)
        )
    if owner_id:
        query = query.filter(OverleafProject.owner_id == owner_id)
    if date_from:
        query = query.filter(OverleafProject.last_updated_at >= date_from)
    if date_to:
        query = query.filter(OverleafProject.last_updated_at <= date_to)

    from sqlalchemy import select as sa_select, func as sa_func

    if indicators:
        from datetime import timedelta
        _now = datetime.now(timezone.utc)
        for ind in indicators:
            if ind == "large":
                query = query.filter(OverleafProject.size_bytes >= SIZE_LARGE_BYTES)
            elif ind == "inactive":
                cutoff = _now - timedelta(days=INACTIVE_DAYS)
                query = query.filter(OverleafProject.last_updated_at <= cutoff)
            elif ind == "collaborative":
                collab_sq = (
                    sa_select(sa_func.count(ProjectMember.id))
                    .where(ProjectMember.project_id == OverleafProject.id)
                    .correlate(OverleafProject)
                    .scalar_subquery()
                )
                query = query.filter(collab_sq >= COLLAB_MANY)

    # ── Ordenación ────────────────────────────────────────────────────────────
    _SORT_COLS = {
        "name":       OverleafProject.name,
        "size":       OverleafProject.size_bytes,
        "updated":    OverleafProject.last_updated_at,
        "created":    OverleafProject.created_at,
    }
    sort_col = _SORT_COLS.get(sort, OverleafProject.last_updated_at)
    if sort == "members":
        member_sort_sq = (
            sa_select(sa_func.count(ProjectMember.id))
            .where(ProjectMember.project_id == OverleafProject.id)
            .correlate(OverleafProject)
            .scalar_subquery()
        )
        order_expr = member_sort_sq.desc() if order == "desc" else member_sort_sq.asc()
    elif order == "desc":
        order_expr = sort_col.desc().nullslast()
    else:
        order_expr = sort_col.asc().nullsfirst()

    pagination = query.order_by(order_expr).paginate(
        page=page, per_page=per_page, error_out=False
    )

    project_ids = [p.id for p in pagination.items]

    member_counts: dict[int, int] = {}
    member_names: dict[int, list[str]] = {}

    if project_ids:
        # Single query for counts
        count_rows = (
            db.session.query(
                ProjectMember.project_id,
                func.count(ProjectMember.id).label("cnt"),
            )
            .filter(ProjectMember.project_id.in_(project_ids))
            .group_by(ProjectMember.project_id)
            .all()
        )
        member_counts = {r.project_id: r.cnt for r in count_rows}

        # Single query for names (tooltip content)
        pm_rows = (
            ProjectMember.query
            .options(db.joinedload(ProjectMember.user))
            .filter(ProjectMember.project_id.in_(project_ids))
            .all()
        )
        for pm in pm_rows:
            if pm.user:
                label = "Editor" if pm.role == "collaborator" else "Solo lectura"
                member_names.setdefault(pm.project_id, []).append(
                    f"{pm.user.display_name} ({label})"
                )

    # Visual indicator flags per project
    now = datetime.now(timezone.utc)
    indicators: dict[int, list[str]] = {}
    for proj in pagination.items:
        flags: list[str] = []
        if proj.size_bytes and proj.size_bytes >= SIZE_LARGE_BYTES:
            flags.append("large")
        lu = _aware(proj.last_updated_at)
        if lu and (now - lu).days >= INACTIVE_DAYS:
            flags.append("inactive")
        if member_counts.get(proj.id, 0) >= COLLAB_MANY:
            flags.append("collaborative")
        indicators[proj.id] = flags

    return {
        "pagination": pagination,
        "member_counts": member_counts,
        "member_names": member_names,
        "indicators": indicators,
    }


def get_project_by_id(project_id: int) -> OverleafProject | None:
    return OverleafProject.query.get(project_id)


def get_project_detail_data(project_id: int) -> dict | None:
    """Returns all data needed for the project detail page."""
    project = (
        OverleafProject.query
        .options(db.joinedload(OverleafProject.owner))
        .get(project_id)
    )
    if not project:
        return None

    members = (
        ProjectMember.query
        .options(db.joinedload(ProjectMember.user))
        .filter_by(project_id=project_id)
        .order_by(ProjectMember.role)
        .all()
    )

    sync_logs = (
        ProjectSyncLog.query
        .options(db.joinedload(ProjectSyncLog.sync_run))
        .filter_by(project_id=project_id)
        .order_by(ProjectSyncLog.synced_at.desc())
        .limit(25)
        .all()
    )

    return {
        "project": project,
        "members": members,
        "sync_logs": sync_logs,
    }


def get_owners_for_filter() -> list[OverleafUser]:
    """Users that own at least one project, for the filter dropdown."""
    owner_ids = (
        db.session.query(OverleafProject.owner_id)
        .filter(OverleafProject.owner_id.isnot(None))
        .distinct()
        .subquery()
    )
    return (
        OverleafUser.query
        .filter(OverleafUser.id.in_(owner_ids))
        .order_by(OverleafUser.email)
        .all()
    )
