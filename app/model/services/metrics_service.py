"""
MetricsService — full analytics data for the dedicated Metrics page.

Gathers user/project/storage stats, growth trends, rankings, sync history,
and system health into a single ``get_metrics_data()`` dict.

Every section is wrapped in try/except so a failure in one area cannot
bring down the rest of the page.
"""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, desc, asc, case, cast, Numeric, nulls_last

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.sync_run import SyncRun
from app.model.entities.audit_log import AuditLog
from app.model.entities.system_alert import SystemAlert
from app.model.entities.role import Role
from app.model.services._helpers import fmt_bytes as _fmt_bytes, label_user as _label

logger = logging.getLogger(__name__)

MES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
       "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _storage_by_owner_sq():
    """Subquery: sum of size_bytes per owner_id. Returns (uid, used_bytes)."""
    return (
        db.session.query(
            OverleafProject.owner_id.label("uid"),
            func.coalesce(func.sum(OverleafProject.size_bytes), 0).label("used_bytes"),
        )
        .filter(OverleafProject.owner_id.isnot(None))
        .group_by(OverleafProject.owner_id)
        .subquery()
    )


def _month_series(n_months: int = 12):
    """Return a contiguous list of datetimes (1st of each month) for the
    last *n_months* months, most recent last."""
    now = datetime.now(timezone.utc)
    months = []
    cur = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(n_months):
        months.append(cur)
        cur = (cur - timedelta(days=1)).replace(day=1)
    months.reverse()
    return months


def _bucket_by_month(query, date_col, start):
    """GROUP BY (year, month) and return {(y, m): count}."""
    rows = (
        query
        .filter(date_col.isnot(None))
        .filter(date_col >= start)
        .with_entities(
            func.extract("year", date_col).label("y"),
            func.extract("month", date_col).label("m"),
            func.count(),
        )
        .group_by("y", "m").all()
    )
    return {(int(y), int(m)): int(c) for y, m, c in rows}


# ── Main entry point ────────────────────────────────────────────────────────

def get_metrics_data() -> dict:
    """All data the metrics template needs, in a single call."""
    try:
        db.session.rollback()
    except Exception:
        pass

    data = {
        # Totals
        "total_users": 0,
        "total_projects": 0,
        "avg_projects_per_user": 0.0,
        "total_storage_bytes": 0,
        "total_storage_fmt": "0 B",
        "total_quota_bytes": 0,
        "total_quota_fmt": "Sin límite",
        "storage_percent": None,
        # Growth
        "growth_users": [],
        "growth_projects": [],
        # Rankings
        "top_owners": [],
        "top_storage": [],
        # Distribution
        "size_buckets": [],
        "storage_per_user": [],
        "role_distribution": [],
        # Activity
        "activity_monthly": [],
        # Sync history
        "sync_history": [],
        "sync_stats": {},
        # ── Analítica avanzada de usuarios y proyectos ───────────────────
        "top_quota": [],            # ranking por % de cuota usado
        "quota_status": [],         # dentro / cerca / superada / sin cuota
        "users_by_proj_count": [],  # buckets 0, 1-2, 3-5, 6-10, >10
        "storage_by_role": [],      # almacenamiento por rol del propietario
        "projects_by_role": [],     # nº de proyectos por rol del propietario
        "activity_status": [],      # activos / inactivos 30d / 90d / nunca
        "top_projects_size": [],    # ranking de proyectos por tamaño
        "scatter_users": [],        # {x: proyectos, y: MB} por usuario
    }

    # ── 1. Totals ────────────────────────────────────────────────────────
    try:
        data["total_users"] = OverleafUser.query.count()
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error counting users: %s", exc)

    try:
        data["total_projects"] = OverleafProject.query.count()
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error counting projects: %s", exc)

    try:
        tu = data["total_users"]
        tp = data["total_projects"]
        data["avg_projects_per_user"] = round(tp / tu, 1) if tu > 0 else 0.0
    except Exception:
        pass

    try:
        raw = db.session.query(
            func.coalesce(func.sum(OverleafProject.size_bytes), 0)
        ).scalar()
        total_storage = int(raw) if raw else 0
        data["total_storage_bytes"] = total_storage
        data["total_storage_fmt"] = _fmt_bytes(total_storage)
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error calculating storage: %s", exc)

    try:
        raw_quota = db.session.query(
            func.coalesce(func.sum(OverleafUser.max_quota_bytes), 0)
        ).filter(OverleafUser.max_quota_bytes.isnot(None)).scalar()
        total_quota = int(raw_quota) if raw_quota else 0
        data["total_quota_bytes"] = total_quota
        data["total_quota_fmt"] = _fmt_bytes(total_quota) if total_quota else "Sin límite"
        ts = data["total_storage_bytes"]
        data["storage_percent"] = (
            round((ts / total_quota) * 100, 1)
            if total_quota > 0 else None
        )
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error calculating quota: %s", exc)

    # ── 2. Growth over 12 months ─────────────────────────────────────────
    try:
        months = _month_series(12)
        start = months[0] - timedelta(days=1)

        signups = _bucket_by_month(OverleafUser.query, OverleafUser.signup_date, start)
        proj_created = _bucket_by_month(OverleafProject.query, OverleafProject.created_at, start)

        # Count users/projects that existed BEFORE the 12-month window
        users_before = (
            OverleafUser.query
            .filter(OverleafUser.signup_date.isnot(None))
            .filter(OverleafUser.signup_date < months[0])
            .count()
        )
        projects_before = (
            OverleafProject.query
            .filter(OverleafProject.created_at.isnot(None))
            .filter(OverleafProject.created_at < months[0])
            .count()
        )

        # Build growth series with cumulative totals
        u_running = users_before
        p_running = projects_before
        gu_list, gp_list, am_list = [], [], []
        for m in months:
            u_new = signups.get((m.year, m.month), 0)
            p_new = proj_created.get((m.year, m.month), 0)
            u_running += u_new
            p_running += p_new
            lbl = f"{MES[m.month]} {str(m.year)[-2:]}"
            gu_list.append({"label": lbl, "count": u_new, "total": u_running})
            gp_list.append({"label": lbl, "count": p_new, "total": p_running})
            am_list.append({"label": lbl, "signups": u_new, "projects": p_new})

        data["growth_users"] = gu_list
        data["growth_projects"] = gp_list
        data["activity_monthly"] = am_list
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching growth data: %s", exc)

    # ── 3. Rankings ──────────────────────────────────────────────────────
    try:
        proj_count_sq = (
            db.session.query(
                OverleafProject.owner_id.label("uid"),
                func.count(OverleafProject.id).label("proj_count"),
            )
            .filter(OverleafProject.owner_id.isnot(None))
            .group_by(OverleafProject.owner_id)
            .subquery()
        )
        top_owners = (
            db.session.query(
                OverleafUser.id,
                OverleafUser.email,
                OverleafUser.first_name,
                OverleafUser.last_name,
                proj_count_sq.c.proj_count,
            )
            .join(proj_count_sq, proj_count_sq.c.uid == OverleafUser.id)
            .order_by(proj_count_sq.c.proj_count.desc())
            .limit(10)
            .all()
        )
        data["top_owners"] = [
            {
                "label": _label(r.email, r.first_name, r.last_name),
                "count": int(r.proj_count or 0),
                "user_id": int(r.id),
            }
            for r in top_owners
        ]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching top owners: %s", exc)

    try:
        storage_sq = _storage_by_owner_sq()
        top_storage = (
            db.session.query(
                OverleafUser.id,
                OverleafUser.email,
                OverleafUser.first_name,
                OverleafUser.last_name,
                storage_sq.c.used_bytes,
            )
            .join(storage_sq, storage_sq.c.uid == OverleafUser.id)
            .order_by(storage_sq.c.used_bytes.desc())
            .limit(10)
            .all()
        )
        data["top_storage"] = [
            {
                "label": _label(r.email, r.first_name, r.last_name),
                "bytes": int(r.used_bytes or 0),
                "fmt": _fmt_bytes(int(r.used_bytes or 0)),
                "user_id": int(r.id),
            }
            for r in top_storage
        ]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching top storage: %s", exc)

    # ── 4. Storage per user (top 10 for chart) ───────────────────────────
    try:
        storage_sq = _storage_by_owner_sq()
        rows = (
            db.session.query(
                OverleafUser.id,
                OverleafUser.email,
                OverleafUser.first_name,
                OverleafUser.last_name,
                OverleafUser.max_quota_bytes,
                func.coalesce(storage_sq.c.used_bytes, 0).label("used"),
            )
            .outerjoin(storage_sq, storage_sq.c.uid == OverleafUser.id)
            .filter(OverleafUser.max_quota_bytes.isnot(None))
            .filter(OverleafUser.max_quota_bytes > 0)
            .order_by(desc("used"))
            .limit(10)
            .all()
        )
        data["storage_per_user"] = [
            {
                "label": _label(r.email, r.first_name, r.last_name),
                "used": int(r.used or 0),
                "used_fmt": _fmt_bytes(int(r.used or 0)),
                "quota": int(r.max_quota_bytes),
                "quota_fmt": _fmt_bytes(int(r.max_quota_bytes)),
                "pct": round(int(r.used or 0) / int(r.max_quota_bytes) * 100, 1) if r.max_quota_bytes else 0,
                "user_id": int(r.id),
            }
            for r in rows
        ]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching storage per user: %s", exc)

    # ── 5. Role distribution ─────────────────────────────────────────────
    try:
        rows = (
            db.session.query(Role.name, func.count(OverleafUser.id))
            .outerjoin(OverleafUser, OverleafUser.role_id == Role.id)
            .group_by(Role.id, Role.name)
            .order_by(Role.name)
            .all()
        )
        data["role_distribution"] = [
            {"name": name, "count": int(cnt)} for name, cnt in rows
        ]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching role distribution: %s", exc)

    # ── 6. Size buckets ──────────────────────────────────────────────────
    try:
        bucket_sq = (
            db.session.query(
                case(
                    (OverleafProject.size_bytes < 200_000, "tiny"),
                    (OverleafProject.size_bytes < 2_500_000, "small"),
                    (OverleafProject.size_bytes < 15_000_000, "medium"),
                    (OverleafProject.size_bytes < 50_000_000, "large"),
                    else_="huge",
                ).label("bucket")
            )
            .filter(OverleafProject.size_bytes.isnot(None))
            .subquery()
        )
        rows = (
            db.session.query(bucket_sq.c.bucket, func.count())
            .group_by(bucket_sq.c.bucket)
            .all()
        )
        order = ["tiny", "small", "medium", "large", "huge"]
        nice = {"tiny": "< 200 KB", "small": "200 KB – 2 MB",
                "medium": "2 – 15 MB", "large": "15 – 50 MB", "huge": "> 50 MB"}
        counts = {b: 0 for b in order}
        for b, n in rows:
            counts[b] = int(n)
        data["size_buckets"] = [{"label": nice[b], "count": counts[b]} for b in order]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching size buckets: %s", exc)

    # ── 7. Sync history (last 20 runs) ───────────────────────────────────
    try:
        runs = (
            SyncRun.query
            .order_by(SyncRun.started_at.desc())
            .limit(20)
            .all()
        )
        data["sync_history"] = runs

        # Aggregate sync stats
        total_runs = len(runs)
        success_runs = sum(1 for r in runs if r.status == "success")
        error_runs = sum(1 for r in runs if r.status == "error")
        avg_duration = None
        durations = [r.duration_seconds for r in runs if r.duration_seconds is not None]
        if durations:
            avg_duration = round(sum(durations) / len(durations), 1)
        data["sync_stats"] = {
            "total_runs": total_runs,
            "success_runs": success_runs,
            "error_runs": error_runs,
            "success_rate": round(success_runs / total_runs * 100, 1) if total_runs else 0,
            "avg_duration_s": avg_duration,
        }
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching sync history: %s", exc)

    # ── 8. Ranking por % de cuota usado (3er modo del ranking) ───────────
    try:
        storage_sq = _storage_by_owner_sq()
        rows = (
            db.session.query(
                OverleafUser.id, OverleafUser.email,
                OverleafUser.first_name, OverleafUser.last_name,
                OverleafUser.max_quota_bytes,
                func.coalesce(storage_sq.c.used_bytes, 0).label("used"),
            )
            .outerjoin(storage_sq, storage_sq.c.uid == OverleafUser.id)
            .filter(OverleafUser.max_quota_bytes.isnot(None))
            .filter(OverleafUser.max_quota_bytes > 0)
            .all()
        )
        ranked = []
        for r in rows:
            used = int(r.used or 0)
            quota = int(r.max_quota_bytes)
            pct = round(used / quota * 100, 1) if quota else 0
            ranked.append({
                "label": _label(r.email, r.first_name, r.last_name),
                "pct": pct,
                "used_fmt": _fmt_bytes(used),
                "quota_fmt": _fmt_bytes(quota),
                "user_id": int(r.id),
            })
        ranked.sort(key=lambda x: x["pct"], reverse=True)
        data["top_quota"] = ranked[:10]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching quota ranking: %s", exc)

    # ── 9. Estado de cuota (dentro / cerca / superada / sin cuota) ────────
    try:
        storage_sq = _storage_by_owner_sq()
        rows = (
            db.session.query(
                OverleafUser.max_quota_bytes,
                func.coalesce(storage_sq.c.used_bytes, 0).label("used"),
            )
            .outerjoin(storage_sq, storage_sq.c.uid == OverleafUser.id)
            .all()
        )
        within = near = exceeded = no_quota = 0
        for r in rows:
            q = r.max_quota_bytes
            if not q or q <= 0:
                no_quota += 1
                continue
            pct = (int(r.used or 0) / int(q)) * 100
            if pct >= 100:
                exceeded += 1
            elif pct >= 80:
                near += 1
            else:
                within += 1
        data["quota_status"] = [
            {"label": "Dentro de cuota",   "count": within,    "key": "within"},
            {"label": "Cerca del límite",  "count": near,      "key": "near"},
            {"label": "Cuota superada",    "count": exceeded,  "key": "exceeded"},
            {"label": "Sin cuota asignada","count": no_quota,  "key": "none"},
        ]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching quota status: %s", exc)

    # ── 10. Distribución de usuarios por nº de proyectos ─────────────────
    try:
        proj_count_sq = (
            db.session.query(
                OverleafProject.owner_id.label("uid"),
                func.count(OverleafProject.id).label("pc"),
            )
            .filter(OverleafProject.owner_id.isnot(None))
            .group_by(OverleafProject.owner_id)
            .subquery()
        )
        rows = (
            db.session.query(func.coalesce(proj_count_sq.c.pc, 0))
            .select_from(OverleafUser)
            .outerjoin(proj_count_sq, proj_count_sq.c.uid == OverleafUser.id)
            .all()
        )
        b0 = b12 = b35 = b610 = b10p = 0
        for (pc,) in rows:
            pc = int(pc or 0)
            if pc == 0:        b0 += 1
            elif pc <= 2:      b12 += 1
            elif pc <= 5:      b35 += 1
            elif pc <= 10:     b610 += 1
            else:              b10p += 1
        data["users_by_proj_count"] = [
            {"label": "0",        "count": b0},
            {"label": "1–2",      "count": b12},
            {"label": "3–5",      "count": b35},
            {"label": "6–10",     "count": b610},
            {"label": "Más de 10","count": b10p},
        ]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching users by project count: %s", exc)

    # ── 11. Estado de actividad (último acceso) ──────────────────────────
    try:
        now = datetime.now(timezone.utc)
        c30 = now - timedelta(days=30)
        c90 = now - timedelta(days=90)
        active = (
            OverleafUser.query.filter(OverleafUser.last_login_at >= c30).count()
        )
        inactive30 = (
            OverleafUser.query
            .filter(OverleafUser.last_login_at < c30)
            .filter(OverleafUser.last_login_at >= c90)
            .count()
        )
        inactive90 = (
            OverleafUser.query.filter(OverleafUser.last_login_at < c90).count()
        )
        never = (
            OverleafUser.query.filter(OverleafUser.last_login_at.is_(None)).count()
        )
        data["activity_status"] = [
            {"label": "Activos (< 30 d)",    "count": active,     "key": "active"},
            {"label": "Inactivos 30 d",      "count": inactive30, "key": "inact30"},
            {"label": "Inactivos 90 d",      "count": inactive90, "key": "inact90"},
            {"label": "Sin actividad",       "count": never,      "key": "never"},
        ]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching activity status: %s", exc)

    # ── 12. Almacenamiento y proyectos por rol del propietario ───────────
    try:
        rows = (
            db.session.query(
                Role.name,
                func.count(OverleafProject.id),
                func.coalesce(func.sum(OverleafProject.size_bytes), 0),
            )
            .select_from(OverleafProject)
            .join(OverleafUser, OverleafUser.id == OverleafProject.owner_id)
            .outerjoin(Role, Role.id == OverleafUser.role_id)
            .group_by(Role.name)
            .all()
        )
        storage_by_role, projects_by_role = [], []
        for name, pcount, sbytes in rows:
            rname = name or "Sin rol"
            storage_by_role.append({
                "name": rname,
                "bytes": int(sbytes or 0),
                "fmt": _fmt_bytes(int(sbytes or 0)),
            })
            projects_by_role.append({"name": rname, "count": int(pcount or 0)})
        storage_by_role.sort(key=lambda x: x["bytes"], reverse=True)
        projects_by_role.sort(key=lambda x: x["count"], reverse=True)
        data["storage_by_role"] = storage_by_role
        data["projects_by_role"] = projects_by_role
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching per-role aggregates: %s", exc)

    # ── 13. Ranking de proyectos por tamaño ──────────────────────────────
    try:
        rows = (
            db.session.query(
                OverleafProject.id,
                OverleafProject.name,
                OverleafProject.size_bytes,
                OverleafUser.email,
                OverleafUser.first_name,
                OverleafUser.last_name,
            )
            .outerjoin(OverleafUser, OverleafUser.id == OverleafProject.owner_id)
            .filter(OverleafProject.size_bytes.isnot(None))
            .filter(OverleafProject.size_bytes > 0)
            .order_by(OverleafProject.size_bytes.desc())
            .limit(10)
            .all()
        )
        data["top_projects_size"] = [
            {
                "label": r.name or "(sin nombre)",
                "bytes": int(r.size_bytes or 0),
                "fmt": _fmt_bytes(int(r.size_bytes or 0)),
                "owner": _label(r.email, r.first_name, r.last_name) if r.email else "—",
                "project_id": int(r.id),
            }
            for r in rows
        ]
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching top projects by size: %s", exc)

    # ── 14. Scatter: proyectos (X) vs almacenamiento MB (Y) por usuario ──
    try:
        storage_sq = _storage_by_owner_sq()
        proj_count_sq = (
            db.session.query(
                OverleafProject.owner_id.label("uid"),
                func.count(OverleafProject.id).label("pc"),
            )
            .filter(OverleafProject.owner_id.isnot(None))
            .group_by(OverleafProject.owner_id)
            .subquery()
        )
        rows = (
            db.session.query(
                OverleafUser.id, OverleafUser.email,
                OverleafUser.first_name, OverleafUser.last_name,
                func.coalesce(proj_count_sq.c.pc, 0).label("pc"),
                func.coalesce(storage_sq.c.used_bytes, 0).label("used"),
            )
            .outerjoin(proj_count_sq, proj_count_sq.c.uid == OverleafUser.id)
            .outerjoin(storage_sq, storage_sq.c.uid == OverleafUser.id)
            .all()
        )
        scatter = []
        for r in rows:
            pc = int(r.pc or 0)
            used = int(r.used or 0)
            # Solo incluir usuarios con algo de actividad (proyectos o storage)
            if pc == 0 and used == 0:
                continue
            scatter.append({
                "x": pc,
                "y": round(used / (1024 * 1024), 2),
                "label": _label(r.email, r.first_name, r.last_name),
                "used_fmt": _fmt_bytes(used),
                "user_id": int(r.id),
            })
        data["scatter_users"] = scatter
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error building scatter data: %s", exc)

    return data
