"""Metrics controller — dedicated analytics and usage metrics page."""
from flask import Blueprint, render_template
from flask_login import login_required

from app.model.services import metrics_service

metrics_bp = Blueprint(
    "metrics", __name__,
    url_prefix="/metricas",
    template_folder="../../templates",
)


@metrics_bp.route("/")
@login_required
def index():
    data = metrics_service.get_metrics_data()
    return render_template(
        "metrics/index.html",
        d=data,
        active_page="metrics",
    )
