"""Projects blueprint — list and detail views for synchronized Overleaf projects."""
from flask import Blueprint, render_template, request
from flask_login import login_required
from flask import current_app

from app.modules.projects import service as project_service

projects_bp = Blueprint("projects", __name__, url_prefix="/proyectos", template_folder="templates")


@projects_bp.route("/")
@login_required
def list_projects():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip() or None
    per_page = current_app.config.get("ITEMS_PER_PAGE", 20)

    pagination = project_service.get_projects_page(
        page=page, per_page=per_page, search=search
    )
    return render_template(
        "projects/list.html",
        pagination=pagination,
        search=search or "",
        active_page="projects",
    )
