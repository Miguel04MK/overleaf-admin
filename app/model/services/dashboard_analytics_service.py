"""
DashboardAnalyticsService — datasets for the rotating analytics cards.

Every dataset is computed with ONE SQL query (joins / subqueries / aggregates)
— no Python iteration over users or projects, no N+1, and no alert
recalculation. The endpoint that calls these functions returns the data once
to the browser, which then rotates between datasets in JS without further
network traffic.

Datasets returned by ``get_rotation_datasets()``:
  - users_near_quota          (users >= 80% of quota, completed up to 10)
  - users_quota_exceeded      (users >= 100% of quota)
  - users_near_project_limit  (users >= 80% of role.max_projects)
  - users_project_limit_over  (users with projects > role.max_projects)
  - inactive_users            (oldest last_login_at first, NULLs last)
  - inactive_projects         (oldest last_updated_at first)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, desc, asc, case, nulls_last, cast, Numeric

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.role import Role
from app.model.services._helpers import label_user as _label

logger = logging.getLogger(__name__)

WARN_PCT = 80
LIMIT = 10


# ── Quota datasets ───────────────────────────────────────────────────────────

def _quota_rows():
    """Return [(email, first, last, overleaf_id, used, max, pct), ...]
    for every user with a non-zero quota — sorted by pct desc."""
    usage_sq = (
        db.session.query(
            OverleafProject.owner_id.label("uid"),
            func.coalesce(func.sum(OverleafProject.size_bytes), 0).label("used"),
        )
        .filter(OverleafProject.owner_id.isnot(None))
        .group_by(OverleafProject.owner_id)
        .subquery()
    )
    # Postgres `round(double precision, int)` does not exist — cast to numeric.
    pct_expr = func.round(
        cast(
            func.coalesce(usage_sq.c.used, 0) * 100.0 / OverleafUser.max_quota_bytes,
            Numeric,
        ),
        1,
    )
    rows = (
        db.session.query(
            OverleafUser.id,
            OverleafUser.email,
            OverleafUser.first_name,
            OverleafUser.last_name,
            OverleafUser.overleaf_id,
            func.coalesce(usage_sq.c.used, 0).label("used"),
            OverleafUser.max_quota_bytes.label("max"),
            pct_expr.label("pct"),
        )
        .outerjoin(usage_sq, usage_sq.c.uid == OverleafUser.id)
        .filter(OverleafUser.max_quota_bytes.isnot(None))
        .filter(OverleafUser.max_quota_bytes > 0)
        .order_by(desc("pct"))
        .limit(LIMIT * 2)  # small buffer so >=80% selection still fits
        .all()
    )
    return rows


def users_near_quota_dataset() -> dict:
    rows = _quota_rows()
    # >=80% first; if fewer than LIMIT, fill with the next highest.
    above = [r for r in rows if r.pct is not None and r.pct >= WARN_PCT]
    if len(above) < LIMIT:
        rest = [r for r in rows if r not in above]
        rows = above + rest[: LIMIT - len(above)]
    else:
        rows = above[:LIMIT]
    return {
        "id": "users_near_quota",
        "title": "Usuarios cerca de superar cuota",
        "subtitle": "Top por % de cuota utilizada",
        "type": "bar",
        "unit": "%",
        "icon": "speedometer2",
        "labels": [_label(r.email, r.first_name, r.last_name, r.overleaf_id) for r in rows],
        "values": [float(r.pct or 0) for r in rows],
        "user_ids": [int(r.id) for r in rows],
    }


def users_quota_exceeded_dataset() -> dict:
    rows = [r for r in _quota_rows() if r.pct is not None and r.pct >= 100][:LIMIT]
    return {
        "id": "users_quota_exceeded",
        "title": "Usuarios con cuota excedida",
        "subtitle": "Uso por encima del 100% de la cuota",
        "type": "polarArea",
        "unit": "%",
        "labels": [_label(r.email, r.first_name, r.last_name, r.overleaf_id) for r in rows],
        "values": [float(r.pct or 0) for r in rows],
    }


# ── Project-limit datasets ───────────────────────────────────────────────────

def _project_limit_rows():
    """Return rows for users whose role has a finite max_projects, with their
    current project count and percentage of the limit used."""
    proj_count_sq = (
        db.session.query(
            OverleafProject.owner_id.label("uid"),
            func.count(OverleafProject.id).label("cnt"),
        )
        .filter(OverleafProject.owner_id.isnot(None))
        .group_by(OverleafProject.owner_id)
        .subquery()
    )
    pct_expr = func.round(
        cast(
            func.coalesce(proj_count_sq.c.cnt, 0) * 100.0 / Role.max_projects,
            Numeric,
        ),
        1,
    )
    rows = (
        db.session.query(
            OverleafUser.id,
            OverleafUser.email,
            OverleafUser.first_name,
            OverleafUser.last_name,
            OverleafUser.overleaf_id,
            func.coalesce(proj_count_sq.c.cnt, 0).label("cnt"),
            Role.max_projects.label("max"),
            pct_expr.label("pct"),
        )
        .join(Role, Role.id == OverleafUser.role_id)
        .outerjoin(proj_count_sq, proj_count_sq.c.uid == OverleafUser.id)
        .filter(Role.max_projects.isnot(None))
        .filter(Role.max_projects > 0)
        .order_by(desc("pct"))
        .limit(LIMIT * 2)
        .all()
    )
    return rows


def users_near_project_limit_dataset() -> dict:
    rows = _project_limit_rows()
    above = [r for r in rows if r.pct is not None and r.pct >= WARN_PCT]
    if len(above) < LIMIT:
        rest = [r for r in rows if r not in above]
        rows = above + rest[: LIMIT - len(above)]
    else:
        rows = above[:LIMIT]
    return {
        "id": "users_near_project_limit",
        "title": "Usuarios cerca del límite de proyectos",
        "subtitle": "% del límite del rol consumido",
        "type": "bar",
        "unit": "%",
        "icon": "kanban-fill",
        "labels": [_label(r.email, r.first_name, r.last_name, r.overleaf_id) for r in rows],
        "values": [float(r.pct or 0) for r in rows],
        "user_ids": [int(r.id) for r in rows],
    }


def users_project_limit_exceeded_dataset() -> dict:
    rows = [r for r in _project_limit_rows() if r.pct is not None and r.pct > 100][:LIMIT]
    return {
        "id": "users_project_limit_over",
        "title": "Usuarios con límite de proyectos superado",
        "subtitle": "Proyectos en propiedad por encima del máximo del rol",
        "type": "doughnut",
        "unit": "%",
        "labels": [_label(r.email, r.first_name, r.last_name, r.overleaf_id) for r in rows],
        "values": [float(r.pct or 0) for r in rows],
        "user_ids": [int(r.id) for r in rows],
    }


# ── Inactivity datasets ──────────────────────────────────────────────────────

def inactive_users_dataset() -> dict:
    """Top users by oldest last_login_at. NULLs (never logged in) are shown
    last with a 'Sin registro' label and a max-out day count."""
    rows = (
        db.session.query(
            OverleafUser.id,
            OverleafUser.email,
            OverleafUser.first_name,
            OverleafUser.last_name,
            OverleafUser.overleaf_id,
            OverleafUser.last_login_at,
        )
        .order_by(nulls_last(asc(OverleafUser.last_login_at)))
        .limit(LIMIT)
        .all()
    )
    now = datetime.now(timezone.utc)
    labels, values, user_ids = [], [], []
    for r in rows:
        labels.append(_label(r.email, r.first_name, r.last_name, r.overleaf_id))
        user_ids.append(int(r.id))
        if r.last_login_at is None:
            values.append(None)
        else:
            ts = r.last_login_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            values.append((now - ts).days)
    return {
        "id": "inactive_users",
        "title": "Usuarios más inactivos",
        "subtitle": "Días desde el último inicio de sesión",
        "type": "bar",
        "unit": "días",
        "labels": labels,
        "values": values,
        "user_ids": user_ids,
    }


def inactive_projects_dataset() -> dict:
    rows = (
        db.session.query(
            OverleafProject.name,
            OverleafProject.last_updated_at,
        )
        .filter(OverleafProject.last_updated_at.isnot(None))
        .order_by(asc(OverleafProject.last_updated_at))
        .limit(LIMIT)
        .all()
    )
    now = datetime.now(timezone.utc)
    labels, values = [], []
    for r in rows:
        labels.append((r.name or "—")[:40])
        ts = r.last_updated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        values.append((now - ts).days)
    return {
        "id": "inactive_projects",
        "title": "Proyectos más inactivos",
        "subtitle": "Días desde la última actualización",
        "type": "bar",
        "unit": "días",
        "labels": labels,
        "values": values,
    }


# ── Orchestrator ─────────────────────────────────────────────────────────────

def users_by_role_dataset() -> dict:
    """Distribution of users across roles. Doughnut, fixed-by-name palette."""
    rows = (
        db.session.query(Role.name, func.count(OverleafUser.id))
        .outerjoin(OverleafUser, OverleafUser.role_id == Role.id)
        .group_by(Role.id, Role.name)
        .order_by(Role.name)
        .all()
    )
    return {
        "id": "users_by_role",
        "title": "Usuarios por rol",
        "subtitle": "Distribución de usuarios entre roles",
        "type": "doughnut",
        "unit": "",
        "icon": "pie-chart-fill",
        "labels": [r[0] for r in rows if r[1] > 0],
        "values": [int(r[1]) for r in rows if r[1] > 0],
    }


def get_rotation_datasets() -> list[dict]:
    """All rotation datasets. Each is wrapped so a failure in one doesn't kill
    the rest — empty datasets are filtered out before returning."""
    builders = [
        users_by_role_dataset,
        users_near_quota_dataset,
        users_near_project_limit_dataset,
        users_project_limit_exceeded_dataset,
        inactive_users_dataset,
        inactive_projects_dataset,
    ]
    datasets = []
    for build in builders:
        try:
            ds = build()
        except Exception as exc:
            # Roll back the failed query so the next builder gets a clean session
            # (Postgres aborts the entire transaction on any error).
            db.session.rollback()
            logger.exception("Analytics: %s failed: %s", build.__name__, exc)
            continue
        n = len(ds.get("labels") or [])
        logger.info("Analytics dataset %s: %d rows", build.__name__, n)
        if n:
            datasets.append(ds)
    logger.info("Analytics: returning %d non-empty datasets", len(datasets))
    return datasets

# touch 1778789801.7202463
