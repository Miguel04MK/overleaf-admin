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
        # System
        "services": [],
        "db_ok": False,
        "alerts_summary": {},
        "recent_errors": [],
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

    # ── 8. Alerts summary ────────────────────────────────────────────────
    try:
        from app.model.services import alerts_service
        alert_counts = dict(
            db.session.query(SystemAlert.level, func.count())
            .filter(SystemAlert.is_resolved == False)  # noqa: E712
            .group_by(SystemAlert.level)
            .all()
        )
        data["alerts_summary"] = {
            "active": alerts_service.get_active_count(),
            "by_level": alert_counts,
            "resolved": alerts_service.get_resolved_count(),
        }
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching alerts summary: %s", exc)

    # ── 9. Recent error audit logs ───────────────────────────────────────
    try:
        data["recent_errors"] = (
            AuditLog.query
            .filter(AuditLog.level.in_(["error", "warning"]))
            .order_by(AuditLog.created_at.desc())
            .limit(10)
            .all()
        )
    except Exception as exc:
        db.session.rollback()
        logger.error("Metrics: error fetching recent errors: %s", exc)

    # ── 10. System status ────────────────────────────────────────────────
    try:
        import concurrent.futures
        from app.model.services.admin.admin_service import get_service_statuses
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(get_service_statuses)
            data["services"] = future.result(timeout=3)
    except Exception:
        pass

    try:
        db.session.execute(db.text("SELECT 1"))
        data["db_ok"] = True
    except Exception:
        data["db_ok"] = False

    return data
