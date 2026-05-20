"""
DashboardService — lightweight summary data for the main dashboard.

The dashboard is now a high-level overview.  Heavy analytics (charts,
rankings, growth trends, sync history) live in metrics_service.py and
are rendered on the dedicated /metricas page.
"""
import logging

from sqlalchemy import func, cast, Numeric

from app.config.extensions import db
from app.model.entities.overleaf_user import OverleafUser, QUOTA_WARNING_PCT
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.sync_run import SyncRun
from app.model.entities.audit_log import AuditLog
from app.model.entities.system_alert import SystemAlert
from app.model.entities.role import Role
from app.model.services._helpers import fmt_bytes as _fmt_bytes

logger = logging.getLogger(__name__)


def get_users_near_quota_page(page: int = 1, per_page: int = 5) -> dict:
    """Return a page of users near quota with total count, for AJAX pagination."""
    try:
        usage_sq = (
            db.session.query(
                OverleafProject.owner_id.label("uid"),
                func.coalesce(func.sum(OverleafProject.size_bytes), 0).label("used"),
            )
            .filter(OverleafProject.owner_id.isnot(None))
            .group_by(OverleafProject.owner_id)
            .subquery()
        )
        pct_expr = func.round(
            cast(
                usage_sq.c.used * 100.0 / OverleafUser.max_quota_bytes,
                Numeric,
            ),
            1,
        )
        base_q = (
            db.session.query(
                OverleafUser.id,
                OverleafUser.email,
                OverleafUser.first_name,
                pct_expr.label("pct"),
            )
            .join(usage_sq, usage_sq.c.uid == OverleafUser.id)
            .filter(OverleafUser.max_quota_bytes.isnot(None))
            .filter(OverleafUser.max_quota_bytes > 0)
            .filter(pct_expr >= QUOTA_WARNING_PCT)
            .order_by(pct_expr.desc())
        )
        total = base_q.count()
        rows = base_q.offset((page - 1) * per_page).limit(per_page).all()
        items = [
            {
                "id": int(r.id),
                "label": r.email or r.first_name or "—",
                "pct": float(r.pct) if r.pct else 0,
            }
            for r in rows
        ]
        return {"items": items, "total": total, "page": page, "per_page": per_page}
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error paging near-quota users: %s", exc)
        return {"items": [], "total": 0, "page": page, "per_page": per_page}


def get_dashboard_data() -> dict:
    """Return summary-level data the dashboard overview needs."""
    try:
        db.session.rollback()
    except Exception:
        pass

    data = {
        # KPI numbers
        "total_users": 0,
        "total_projects": 0,
        "avg_projects_per_user": 0.0,
        "total_storage_bytes": 0,
        "total_storage_fmt": "0 B",
        "total_quota_bytes": 0,
        "total_quota_fmt": "Sin límite",
        "storage_percent": None,
        # Roles
        "role_stats": {},
        # Quota warnings
        "users_near_quota": [],
        "users_near_quota_total": 0,
        # Alerts
        "alerts_active": 0,
        "alerts_by_level": {},
        # Sync
        "last_sync": None,
        "recent_syncs": [],
        # Tables
        "recent_alerts": [],
        "recent_audit": [],
        # System
        "services": [],
        "db_ok": False,
    }

    # ── 1. KPI totals ────────────────────────────────────────────────────
    try:
        data["total_users"] = OverleafUser.query.count()
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error counting users: %s", exc)

    try:
        data["total_projects"] = OverleafProject.query.count()
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error counting projects: %s", exc)

    try:
        tu = data["total_users"]
        tp = data["total_projects"]
        data["avg_projects_per_user"] = round(tp / tu, 1) if tu > 0 else 0.0
    except Exception:
        pass

    try:
        raw_storage = db.session.query(
            func.coalesce(func.sum(OverleafProject.size_bytes), 0)
        ).scalar()
        total_storage = int(raw_storage) if raw_storage else 0
        data["total_storage_bytes"] = total_storage
        data["total_storage_fmt"] = _fmt_bytes(total_storage)
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error calculating storage: %s", exc)

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
            if total_quota and total_quota > 0 else None
        )
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error calculating quota: %s", exc)

    # ── 2. Role stats ────────────────────────────────────────────────────
    try:
        from app.model.services.roles_service import get_role_stats
        data["role_stats"] = get_role_stats()
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error fetching role stats: %s", exc)

    # ── 3. Users near quota ──────────────────────────────────────────────
    try:
        usage_sq = (
            db.session.query(
                OverleafProject.owner_id.label("uid"),
                func.coalesce(func.sum(OverleafProject.size_bytes), 0).label("used"),
            )
            .filter(OverleafProject.owner_id.isnot(None))
            .group_by(OverleafProject.owner_id)
            .subquery()
        )
        pct_expr = func.round(
            cast(
                usage_sq.c.used * 100.0 / OverleafUser.max_quota_bytes,
                Numeric,
            ),
            1,
        )
        near_q = (
            db.session.query(OverleafUser, pct_expr.label("pct"))
            .join(usage_sq, usage_sq.c.uid == OverleafUser.id)
            .filter(OverleafUser.max_quota_bytes.isnot(None))
            .filter(OverleafUser.max_quota_bytes > 0)
            .filter(pct_expr >= QUOTA_WARNING_PCT)
            .order_by(pct_expr.desc())
            .all()
        )
        for u, pct in near_q:
            u._cached_quota_percent = float(pct)
        data["users_near_quota"] = [u for u, _ in near_q[:7]]
        data["users_near_quota_total"] = len(near_q)
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error fetching near-quota users: %s", exc)

    # ── 4. Alerts ────────────────────────────────────────────────────────
    try:
        from app.model.services import alerts_service
        alert_counts = dict(
            db.session.query(SystemAlert.level, func.count())
            .filter(SystemAlert.is_resolved == False)  # noqa: E712
            .group_by(SystemAlert.level)
            .all()
        )
        data["alerts_by_level"] = alert_counts
        data["alerts_active"] = alerts_service.get_active_count()
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error counting alerts: %s", exc)

    # ── 5. Last sync ─────────────────────────────────────────────────────
    try:
        data["last_sync"] = SyncRun.query.order_by(
            SyncRun.started_at.desc()
        ).first()
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error fetching last sync: %s", exc)

    # ── 5b. Recent syncs (last 5 for mini-table) ────────────────────────
    try:
        data["recent_syncs"] = (
            SyncRun.query
            .order_by(SyncRun.started_at.desc())
            .limit(5)
            .all()
        )
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error fetching recent syncs: %s", exc)

    # ── 6. Recent alerts ─────────────────────────────────────────────────
    try:
        from app.model.services import alerts_service
        data["recent_alerts"] = alerts_service.get_recent_alerts(limit=5)
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error fetching recent alerts: %s", exc)

    # ── 7. Recent audit logs ─────────────────────────────────────────────
    try:
        data["recent_audit"] = (
            AuditLog.query
            .order_by(AuditLog.created_at.desc())
            .limit(5)
            .all()
        )
    except Exception as exc:
        db.session.rollback()
        logger.error("Dashboard: error fetching audit logs: %s", exc)

    # ── 8. System status ─────────────────────────────────────────────────
    try:
        import concurrent.futures
        from app.model.services.admin.admin_service import get_service_statuses
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(get_service_statuses)
            data["services"] = future.result(timeout=3)
    except Exception:
        pass

    # ── 9. DB check ──────────────────────────────────────────────────────
    try:
        db.session.execute(db.text("SELECT 1"))
        data["db_ok"] = True
    except Exception:
        data["db_ok"] = False

    return data
