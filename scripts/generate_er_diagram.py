"""
Genera un diagrama Entidad-Relación del modelo de datos PostgreSQL.
Usa matplotlib para renderizar las tablas y sus relaciones.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os

# ── Definición del esquema ──────────────────────────────────────────────────

TABLES = {
    "roles": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("name", "VARCHAR(64)", "NOT NULL, UNIQUE"),
            ("description", "TEXT", ""),
            ("storage_quota_bytes", "BIGINT", ""),
            ("max_projects", "INTEGER", ""),
            ("is_default", "BOOLEAN", "NOT NULL"),
            ("color", "VARCHAR(32)", "NOT NULL"),
            ("created_at", "TIMESTAMP", "NOT NULL"),
            ("updated_at", "TIMESTAMP", "NOT NULL"),
        ],
    },
    "overleaf_users": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("overleaf_id", "VARCHAR(64)", "NOT NULL, UNIQUE"),
            ("email", "VARCHAR(255)", ""),
            ("first_name", "VARCHAR(255)", ""),
            ("last_name", "VARCHAR(255)", ""),
            ("is_admin", "BOOLEAN", "NOT NULL"),
            ("signup_date", "TIMESTAMP", ""),
            ("last_login_at", "TIMESTAMP", ""),
            ("max_quota_bytes", "BIGINT", ""),
            ("role_id", "INTEGER", "FK"),
            ("synced_at", "TIMESTAMP", "NOT NULL"),
        ],
    },
    "overleaf_projects": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("overleaf_id", "VARCHAR(64)", "NOT NULL, UNIQUE"),
            ("name", "VARCHAR(512)", ""),
            ("owner_id", "INTEGER", "FK"),
            ("owner_overleaf_id", "VARCHAR(64)", ""),
            ("created_at", "TIMESTAMP", ""),
            ("last_updated_at", "TIMESTAMP", ""),
            ("file_count", "INTEGER", ""),
            ("size_bytes", "BIGINT", ""),
            ("synced_at", "TIMESTAMP", "NOT NULL"),
        ],
    },
    "project_members": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("project_id", "INTEGER", "FK, NOT NULL"),
            ("user_id", "INTEGER", "FK, NOT NULL"),
            ("role", "VARCHAR(32)", "NOT NULL"),
            ("synced_at", "TIMESTAMP", "NOT NULL"),
        ],
    },
    "role_change_logs": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("user_id", "INTEGER", "FK, NOT NULL"),
            ("role_from_id", "INTEGER", "FK"),
            ("role_to_id", "INTEGER", "FK"),
            ("action", "VARCHAR(16)", "NOT NULL"),
            ("changed_by", "VARCHAR(128)", "NOT NULL"),
            ("changed_at", "TIMESTAMP", "NOT NULL"),
            ("reason", "TEXT", ""),
        ],
    },
    "sync_runs": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("started_at", "TIMESTAMP", "NOT NULL"),
            ("finished_at", "TIMESTAMP", ""),
            ("status", "VARCHAR(32)", "NOT NULL"),
            ("users_found", "INTEGER", ""),
            ("users_synced", "INTEGER", ""),
            ("projects_found", "INTEGER", ""),
            ("projects_synced", "INTEGER", ""),
            ("users_delta", "INTEGER", ""),
            ("projects_delta", "INTEGER", ""),
            ("triggered_by", "VARCHAR(32)", "NOT NULL"),
            ("triggered_by_user", "VARCHAR(128)", ""),
            ("message", "TEXT", ""),
        ],
    },
    "project_sync_logs": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("project_id", "INTEGER", "FK, NOT NULL"),
            ("sync_run_id", "INTEGER", "FK"),
            ("synced_at", "TIMESTAMP", "NOT NULL"),
            ("event", "VARCHAR(16)", "NOT NULL"),
            ("size_bytes", "BIGINT", ""),
            ("member_count", "INTEGER", ""),
        ],
    },
    "admin_users": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("username", "VARCHAR(64)", "NOT NULL, UNIQUE"),
            ("email", "VARCHAR(255)", "NOT NULL, UNIQUE"),
            ("password_hash", "VARCHAR(255)", "NOT NULL"),
            ("is_active", "BOOLEAN", "NOT NULL"),
            ("created_at", "TIMESTAMP", "NOT NULL"),
            ("last_login_at", "TIMESTAMP", ""),
        ],
    },
    "admin_notification_prefs": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("admin_id", "INTEGER", "FK, NOT NULL, UNIQUE"),
            ("notify_critical", "BOOLEAN", "NOT NULL"),
            ("notify_danger", "BOOLEAN", "NOT NULL"),
            ("notify_warning", "BOOLEAN", "NOT NULL"),
            ("notify_info", "BOOLEAN", "NOT NULL"),
            ("notify_service_down", "BOOLEAN", "NOT NULL"),
            ("notify_sync_failed", "BOOLEAN", "NOT NULL"),
            ("notify_quota_exceeded", "BOOLEAN", "NOT NULL"),
            ("notify_quota_warning", "BOOLEAN", "NOT NULL"),
            ("notify_project_limit_exceeded", "BOOLEAN", "NOT NULL"),
            ("notify_project_limit_warning", "BOOLEAN", "NOT NULL"),
            ("notify_repeated_errors", "BOOLEAN", "NOT NULL"),
            ("notify_administrative_warning", "BOOLEAN", "NOT NULL"),
        ],
    },
    "audit_logs": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("actor", "VARCHAR(64)", "NOT NULL"),
            ("action", "VARCHAR(64)", "NOT NULL"),
            ("detail", "TEXT", ""),
            ("level", "VARCHAR(16)", "NOT NULL"),
            ("ip_address", "VARCHAR(45)", ""),
            ("created_at", "TIMESTAMP", "NOT NULL"),
        ],
    },
    "system_alerts": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("type", "VARCHAR(64)", "NOT NULL"),
            ("level", "VARCHAR(16)", "NOT NULL"),
            ("title", "VARCHAR(255)", "NOT NULL"),
            ("message", "TEXT", "NOT NULL"),
            ("entity_type", "VARCHAR(32)", ""),
            ("entity_id", "VARCHAR(64)", ""),
            ("is_read", "BOOLEAN", "NOT NULL"),
            ("is_resolved", "BOOLEAN", "NOT NULL"),
            ("created_at", "TIMESTAMP", "NOT NULL"),
            ("resolved_at", "TIMESTAMP", ""),
            ("resolved_by", "VARCHAR(64)", ""),
            ("resolution_comment", "TEXT", ""),
            ("email_notified_at", "TIMESTAMP", ""),
            ("created_by_system", "BOOLEAN", "NOT NULL"),
            ("source", "VARCHAR(64)", ""),
            ("extra_data_json", "TEXT", ""),
        ],
    },
    "app_settings": {
        "columns": [
            ("key", "VARCHAR(64)", "PK"),
            ("value", "VARCHAR(255)", "NOT NULL"),
            ("description", "VARCHAR(255)", ""),
            ("updated_at", "TIMESTAMP", ""),
            ("updated_by", "VARCHAR(64)", ""),
        ],
    },
    "report_export_logs": {
        "columns": [
            ("id", "INTEGER", "PK"),
            ("report_type", "VARCHAR(64)", "NOT NULL"),
            ("format", "VARCHAR(16)", "NOT NULL"),
            ("generated_by", "VARCHAR(128)", "NOT NULL"),
            ("generated_at", "TIMESTAMP", "NOT NULL"),
            ("filters_json", "TEXT", ""),
            ("status", "VARCHAR(32)", "NOT NULL"),
            ("file_name", "VARCHAR(255)", ""),
            ("error_message", "TEXT", ""),
        ],
    },
}

# Foreign key relationships: (from_table, from_col, to_table, to_col, label)
RELATIONS = [
    ("overleaf_users", "role_id", "roles", "id", "N:1"),
    ("overleaf_projects", "owner_id", "overleaf_users", "id", "N:1"),
    ("project_members", "project_id", "overleaf_projects", "id", "N:1"),
    ("project_members", "user_id", "overleaf_users", "id", "N:1"),
    ("role_change_logs", "user_id", "overleaf_users", "id", "N:1"),
    ("role_change_logs", "role_from_id", "roles", "id", "N:1"),
    ("role_change_logs", "role_to_id", "roles", "id", "N:1"),
    ("project_sync_logs", "project_id", "overleaf_projects", "id", "N:1"),
    ("project_sync_logs", "sync_run_id", "sync_runs", "id", "N:1"),
    ("admin_notification_prefs", "admin_id", "admin_users", "id", "1:1"),
]

# ── Layout: posiciones manuales para evitar solapamientos ───────────────────

POSITIONS = {
    # Core cluster (center)
    "roles":              (1.0,  8.5),
    "overleaf_users":     (5.5,  8.5),
    "overleaf_projects":  (10.5, 8.5),
    "project_members":    (8.0,  5.0),
    "role_change_logs":   (2.5,  5.0),
    # Sync cluster (right)
    "sync_runs":          (14.5, 5.0),
    "project_sync_logs":  (14.5, 8.5),
    # Admin cluster (left)
    "admin_users":            (1.0,  1.5),
    "admin_notification_prefs": (5.5,  1.5),
    # Standalone tables (bottom)
    "audit_logs":         (9.5,  1.5),
    "system_alerts":      (13.5, 1.5),
    "app_settings":       (17.5, 8.5),
    "report_export_logs": (17.5, 5.0),
}

# ── Colores por grupo funcional ─────────────────────────────────────────────

COLORS = {
    "roles":              ("#e8f5e9", "#2e7d32"),  # green
    "overleaf_users":     ("#e3f2fd", "#1565c0"),  # blue
    "overleaf_projects":  ("#e3f2fd", "#1565c0"),
    "project_members":    ("#e3f2fd", "#1565c0"),
    "role_change_logs":   ("#e8f5e9", "#2e7d32"),
    "sync_runs":          ("#fff3e0", "#e65100"),  # orange
    "project_sync_logs":  ("#fff3e0", "#e65100"),
    "admin_users":        ("#fce4ec", "#c62828"),  # red
    "admin_notification_prefs": ("#fce4ec", "#c62828"),
    "audit_logs":         ("#f3e5f5", "#6a1b9a"),  # purple
    "system_alerts":      ("#fff8e1", "#f9a825"),  # amber
    "app_settings":       ("#eceff1", "#455a64"),  # grey
    "report_export_logs": ("#f3e5f5", "#6a1b9a"),
}


def draw_table(ax, name, table, x, y, bg_color, header_color):
    """Draw a single table box at (x, y)."""
    cols = table["columns"]
    row_h = 0.28
    header_h = 0.38
    w = 3.6
    total_h = header_h + len(cols) * row_h + 0.08

    # Shadow
    shadow = FancyBboxPatch(
        (x + 0.04, y - total_h + 0.04), w, total_h,
        boxstyle="round,pad=0.06", facecolor="#00000008",
        edgecolor="none", linewidth=0, zorder=1,
    )
    ax.add_patch(shadow)

    # Table body
    body = FancyBboxPatch(
        (x, y - total_h), w, total_h,
        boxstyle="round,pad=0.06", facecolor=bg_color,
        edgecolor="#bdbdbd", linewidth=0.8, zorder=2,
    )
    ax.add_patch(body)

    # Header
    header = FancyBboxPatch(
        (x, y - header_h), w, header_h,
        boxstyle="round,pad=0.06", facecolor=header_color,
        edgecolor=header_color, linewidth=0.8, zorder=3,
    )
    ax.add_patch(header)
    ax.text(
        x + w / 2, y - header_h / 2, name,
        ha="center", va="center", fontsize=8.5, fontweight="bold",
        color="white", zorder=4, fontfamily="monospace",
    )

    # Columns
    col_positions = {}
    for i, (col_name, col_type, flags) in enumerate(cols):
        cy = y - header_h - 0.04 - i * row_h - row_h / 2
        # Icon
        if "PK" in flags:
            icon = "PK"
            icon_color = "#f9a825"
        elif "FK" in flags:
            icon = "FK"
            icon_color = "#1565c0"
        else:
            icon = ""
            icon_color = "#757575"

        ax.text(x + 0.12, cy, icon, ha="left", va="center",
                fontsize=5.5, color=icon_color, zorder=4,
                fontfamily="monospace", fontweight="bold")
        ax.text(x + 0.35, cy, col_name, ha="left", va="center",
                fontsize=6.5, color="#212121", zorder=4,
                fontfamily="monospace",
                fontweight="bold" if "PK" in flags else "normal")
        ax.text(x + w - 0.12, cy, col_type, ha="right", va="center",
                fontsize=5.5, color="#757575", zorder=4,
                fontfamily="monospace")

        col_positions[col_name] = (x, x + w, cy)

    return {
        "x": x, "y": y, "w": w, "h": total_h,
        "cols": col_positions,
    }


def draw_relation(ax, t1_info, col1, t2_info, col2, label=""):
    """Draw a relationship line between two columns."""
    c1 = t1_info["cols"].get(col1)
    c2 = t2_info["cols"].get(col2)
    if not c1 or not c2:
        return

    x1_left, x1_right, y1 = c1
    x2_left, x2_right, y2 = c2

    # Decide connection side
    mid1 = (x1_left + x1_right) / 2
    mid2 = (x2_left + x2_right) / 2

    if mid1 < mid2:
        sx, ex = x1_right, x2_left
    else:
        sx, ex = x1_left, x2_right

    color = "#1565c0" if label == "1:1" else "#616161"

    ax.annotate(
        "", xy=(ex, y2), xytext=(sx, y1),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=1.0,
            connectionstyle="arc3,rad=0.15",
            shrinkA=2, shrinkB=2,
        ),
        zorder=1,
    )


def main():
    fig, ax = plt.subplots(1, 1, figsize=(24, 13), dpi=150)
    ax.set_xlim(-0.5, 21)
    ax.set_ylim(-0.5, 11)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")

    # Title
    ax.text(
        10.25, 10.6,
        "Modelo de Datos — Overleaf Admin (PostgreSQL)",
        ha="center", va="center", fontsize=16, fontweight="bold",
        color="#212121",
    )
    ax.text(
        10.25, 10.25,
        "13 tablas  |  10 foreign keys  |  Generado desde SQLAlchemy entities",
        ha="center", va="center", fontsize=9, color="#757575",
    )

    # Draw tables
    table_infos = {}
    for name, table in TABLES.items():
        x, y = POSITIONS[name]
        bg, hdr = COLORS[name]
        info = draw_table(ax, name, table, x, y, bg, hdr)
        table_infos[name] = info

    # Draw relations
    for from_t, from_c, to_t, to_c, label in RELATIONS:
        if from_t in table_infos and to_t in table_infos:
            draw_relation(ax, table_infos[from_t], from_c,
                          table_infos[to_t], to_c, label)

    # Legend
    legend_items = [
        ("#2e7d32", "Roles y permisos"),
        ("#1565c0", "Datos Overleaf (usuarios, proyectos)"),
        ("#e65100", "Sincronizacion"),
        ("#c62828", "Administracion"),
        ("#6a1b9a", "Auditoria e informes"),
        ("#f9a825", "Alertas del sistema"),
        ("#455a64", "Configuracion"),
    ]
    for i, (color, label) in enumerate(legend_items):
        lx = 0.2
        ly = 0.3 - i * 0.32
        ax.add_patch(FancyBboxPatch(
            (lx, ly), 0.25, 0.22,
            boxstyle="round,pad=0.02", facecolor=color,
            edgecolor="none", zorder=5,
        ))
        ax.text(lx + 0.35, ly + 0.11, label, va="center",
                fontsize=7, color="#424242", zorder=5)

    plt.tight_layout(pad=0.5)
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs", "modelo_datos_er.png"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"Diagrama guardado en: {out_path}")


if __name__ == "__main__":
    main()
