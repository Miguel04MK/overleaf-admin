"""Projects controller — list and detail views for synchronized Overleaf projects."""
from flask import Blueprint, render_template, request, abort, current_app, jsonify, url_for
from flask_login import login_required

from app.model.services import projects_service
from app.rest.common.helpers import parse_date

projects_bp = Blueprint("projects", __name__, url_prefix="/proyectos")


def _fmt_size(size_bytes: int | None) -> str | None:
    if not size_bytes or size_bytes <= 0:
        return None
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f} GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1_024:
        return f"{size_bytes / 1_024:.1f} KB"
    return f"{size_bytes} B"


def _serialize_project(proj, member_counts, member_names) -> dict:
    cnt = member_counts.get(proj.id, 0)
    return {
        "id":             proj.id,
        "name":           proj.name or "",
        "owner_id":       proj.owner.id if proj.owner else None,
        "owner_name":     proj.owner.display_name if proj.owner else None,
        "owner_url":      url_for("users.user_detail", user_id=proj.owner.id) if proj.owner else None,
        "member_count":   cnt,
        "member_names":   member_names.get(proj.id, []),
        "size_fmt":       _fmt_size(proj.size_bytes),
        "last_updated_at": proj.last_updated_at.strftime("%d/%m/%Y") if proj.last_updated_at else None,
        "created_at":     proj.created_at.strftime("%d/%m/%Y") if proj.created_at else None,
        "detail_url":     url_for("projects.project_detail", project_id=proj.id),
    }


def _parse_op(raw: str | None) -> str | None:
    return raw if raw in ("gt", "eq", "lt") else None


def _get_list_params():
    """Parse and sanitize shared query params for list + search endpoints."""
    _VALID_SORTS = {"name", "size", "updated", "created", "members"}
    page       = request.args.get("page", 1, type=int)
    search     = request.args.get("q", "").strip() or None
    owner_id   = request.args.get("owner_id", None, type=int)
    date_from  = request.args.get("date_from", "")
    date_to    = request.args.get("date_to", "")
    size_op    = _parse_op(request.args.get("size_op"))
    size_mb    = request.args.get("size_mb", type=float)
    members_op = _parse_op(request.args.get("members_op"))
    members_v  = request.args.get("members_val", type=int)
    sort_col   = request.args.get("sort", "updated")
    sort_order = request.args.get("order", "desc")
    per_page   = current_app.config.get("ITEMS_PER_PAGE", 20)
    if sort_col not in _VALID_SORTS:
        sort_col = "updated"
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    return dict(
        page=page, search=search, owner_id=owner_id,
        date_from_str=date_from, date_to_str=date_to,
        size_op=size_op, size_mb=size_mb,
        members_op=members_op, members_val=members_v,
        sort_col=sort_col, sort_order=sort_order,
        per_page=per_page,
    )


@projects_bp.route("/")
@login_required
def list_projects():
    p = _get_list_params()

    data   = projects_service.get_projects_list_data(
        page=p["page"], per_page=p["per_page"],
        search=p["search"], owner_id=p["owner_id"],
        date_from=parse_date(p["date_from_str"]),
        date_to=parse_date(p["date_to_str"]),
        size_op=p["size_op"], size_mb=p["size_mb"],
        members_op=p["members_op"], members_val=p["members_val"],
        sort=p["sort_col"], order=p["sort_order"],
    )
    owners = projects_service.get_owners_for_filter()
    selected_owner = next(
        (o for o in owners if o.id == p["owner_id"]), None
    ) if p["owner_id"] else None

    return render_template(
        "projects/list.html",
        active_page="projects",
        owners=owners,
        selected_owner=selected_owner,
        search=p["search"] or "",
        owner_id=p["owner_id"],
        date_from=p["date_from_str"],
        date_to=p["date_to_str"],
        size_op=p["size_op"], size_mb=p["size_mb"],
        members_op=p["members_op"], members_val=p["members_val"],
        sort_col=p["sort_col"],
        sort_order=p["sort_order"],
        **data,
    )


@projects_bp.route("/buscar")
@login_required
def search_projects():
    """JSON endpoint — same filters as list_projects, returns table data."""
    p = _get_list_params()

    data = projects_service.get_projects_list_data(
        page=p["page"], per_page=p["per_page"],
        search=p["search"], owner_id=p["owner_id"],
        date_from=parse_date(p["date_from_str"]),
        date_to=parse_date(p["date_to_str"]),
        size_op=p["size_op"], size_mb=p["size_mb"],
        members_op=p["members_op"], members_val=p["members_val"],
        sort=p["sort_col"], order=p["sort_order"],
    )
    pagination     = data["pagination"]
    member_counts  = data["member_counts"]
    member_names   = data["member_names"]

    return jsonify({
        "total":    pagination.total,
        "page":     pagination.page,
        "pages":    pagination.pages,
        "per_page": pagination.per_page,
        "has_prev": pagination.has_prev,
        "has_next": pagination.has_next,
        "prev_num": pagination.prev_num,
        "next_num": pagination.next_num,
        "projects": [
            _serialize_project(proj, member_counts, member_names)
            for proj in pagination.items
        ],
    })


@projects_bp.route("/<int:project_id>")
@login_required
def project_detail(project_id: int):
    data = projects_service.get_project_detail_data(project_id)
    if data is None:
        abort(404)
    return render_template(
        "projects/detail.html",
        active_page="projects",
        **data,
    )
