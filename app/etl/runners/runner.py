"""
SyncRunner — orchestrates the full ETL pipeline.

Flow:
    1. Create SyncRun record (status=running)
    2. Connect to MongoDB via OverleafMongoAdapter
    3. Extract users and projects (OverleafExtractor)
    4. Upsert into PostgreSQL (OverleafLoader)
    5. Upsert memberships
    6. Mark SyncRun as success/error
    7. Write audit log entry

This is the only public entry point for triggering a sync.
Call: run_sync(app, triggered_by="manual")
"""
import logging
from datetime import datetime, timezone

from flask import Flask

from app.extensions import db
from app.models.sync_run import SyncRun
from app.modules.admin import service as audit_service
from app.etl.extractors.adapter import OverleafMongoAdapter, make_adapter
from app.etl.extractors.extractor import OverleafExtractor
from app.etl.loaders.loader import OverleafLoader

logger = logging.getLogger(__name__)


def _fmt_delta(delta: int) -> str:
    """Format a delta as a signed string: +3, -2, 0."""
    if delta is None:
        return "?"
    if delta > 0:
        return f"+{delta}"
    return str(delta)


def run_sync(app: Flask, triggered_by: str = "manual") -> SyncRun:
    """
    Execute a full sync cycle.
    Must be called within an app context (or wraps itself in one).
    Returns the completed SyncRun record.
    """
    with app.app_context():
        sync_run = SyncRun(triggered_by=triggered_by)
        db.session.add(sync_run)
        db.session.commit()
        logger.info("SyncRun #%d started (triggered_by=%s)", sync_run.id, triggered_by)

        audit_service.log_action(
            action="sync_start",
            actor="system",
            detail=f"Sincronización iniciada (modo: {triggered_by})",
            level="info",
        )

        adapter = make_adapter(app)

        # Reference counts from the previous *successful* sync, so the delta
        # reflects changes in the Overleaf source (additions and removals)
        # independently of our local upsert-only loader.
        prev = (
            SyncRun.query
            .filter(SyncRun.id != sync_run.id, SyncRun.status == "success")
            .order_by(SyncRun.started_at.desc())
            .first()
        )
        prev_users_found = prev.users_found if prev else None
        prev_projects_found = prev.projects_found if prev else None

        try:
            # Step 1: Connect
            adapter.connect()

            with adapter.get_db() as mongo_db:
                extractor = OverleafExtractor(mongo_db)
                loader = OverleafLoader()

                # Step 2: Extract
                raw_users = extractor.extract_users()
                raw_projects = extractor.extract_projects()

                # Step 3: Upsert users first (needed for FK resolution)
                users_found, users_synced = loader.upsert_users(raw_users)
                sync_run.users_found = users_found
                sync_run.users_synced = users_synced
                db.session.flush()

                # Step 4: Build user map (overleaf_id → internal id)
                user_map = loader.build_user_map()

                # Step 5: Prepare memberships data alongside projects
                memberships_data = []
                for raw_proj in raw_projects:
                    members = []
                    for oid in raw_proj.get("collaborator_overleaf_ids", []):
                        if oid in user_map:
                            members.append({"overleaf_user_id": oid, "role": "collaborator"})
                    for oid in raw_proj.get("readonly_overleaf_ids", []):
                        if oid in user_map:
                            members.append({"overleaf_user_id": oid, "role": "read_only"})
                    memberships_data.append((raw_proj["overleaf_id"], members))

                # Step 6: Upsert projects + memberships
                projects_found, projects_synced = loader.upsert_projects(
                    raw_projects, memberships_data, user_map
                )
                sync_run.projects_found = projects_found
                sync_run.projects_synced = projects_synced

                db.session.commit()

            adapter.disconnect()

            # Compute deltas: change in Overleaf-source counts since last
            # successful sync. If this is the first run, leave as None.
            sync_run.users_delta = (
                users_found - prev_users_found if prev_users_found is not None else None
            )
            sync_run.projects_delta = (
                projects_found - prev_projects_found if prev_projects_found is not None else None
            )

            sync_run.mark_finished(
                status="success",
                message=(
                    f"Sincronización completada: "
                    f"{users_synced}/{users_found} usuarios "
                    f"({_fmt_delta(sync_run.users_delta)}), "
                    f"{projects_synced}/{projects_found} proyectos "
                    f"({_fmt_delta(sync_run.projects_delta)})."
                ),
            )
            db.session.commit()

            audit_service.log_action(
                action="sync_ok",
                actor="system",
                detail=sync_run.message,
                level="info",
            )
            logger.info("SyncRun #%d finished successfully.", sync_run.id)

        except Exception as exc:
            db.session.rollback()
            error_msg = f"Error de sincronización: {exc}"
            logger.error("SyncRun #%d failed: %s", sync_run.id, exc, exc_info=True)

            try:
                sync_run.mark_finished(status="error", message=error_msg)
                db.session.commit()
            except Exception:
                db.session.rollback()

            audit_service.log_action(
                action="sync_error",
                actor="system",
                detail=error_msg,
                level="error",
            )

        finally:
            try:
                adapter.disconnect()
            except Exception:
                pass

        return sync_run
