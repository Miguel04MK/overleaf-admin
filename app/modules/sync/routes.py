"""Sync blueprint — manual sync trigger and status view."""
import threading
import logging

from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app.modules.sync import repository as sync_repository
from app.modules.admin import service as audit_service

logger = logging.getLogger(__name__)
sync_bp = Blueprint("sync", __name__, url_prefix="/sincronizacion", template_folder="templates")


@sync_bp.route("/")
@login_required
def status():
    runs = sync_repository.get_recent_runs(limit=20)
    return render_template(
        "sync/status.html",
        runs=runs,
        active_page="sync",
    )


@sync_bp.route("/ejecutar", methods=["POST"])
@login_required
def trigger():
    """Launch a manual sync in a background thread."""
    app = current_app._get_current_object()
    actor = current_user.username

    audit_service.log_action(
        action="sync_trigger",
        actor=actor,
        detail="Sincronización manual iniciada desde la interfaz web.",
        level="info",
    )

    def _run():
        from app.etl.runners.runner import run_sync
        run_sync(app, triggered_by="manual")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    flash(
        "Sincronización iniciada en segundo plano. "
        "Refresca esta página en unos segundos para ver el resultado.",
        "info",
    )
    return redirect(url_for("sync.status"))
