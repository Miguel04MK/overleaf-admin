"""
Flask application factory.
"""
import os
import logging
from flask import Flask
from dotenv import load_dotenv

from app.config.config import config_map
from app.config.extensions import db, migrate, login_manager

load_dotenv()


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Load config
    cfg = config_map.get(config_name, config_map["default"])
    app.config.from_object(cfg)

    # Reverse proxy (despliegue institucional detrás de un proxy con HTTPS):
    # confía en X-Forwarded-Proto/For/Host para que url_for(_external=True)
    # genere https y request.remote_addr sea la IP real del cliente.
    # Se activa con BEHIND_PROXY=true; en local queda desactivado.
    if app.config.get("BEHIND_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1,
        )
        logging.getLogger(__name__).info(
            "ProxyFix activado: confiando en cabeceras X-Forwarded-* del proxy."
        )

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if app.config["DEBUG"] else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Import all models so Alembic can detect them
    from app.model.entities import (  # noqa: F401
        overleaf_user, overleaf_project, project_member,
        sync_run, sync_schedule, audit_log, project_sync_log,
        role, role_change_log, report_export_log,
        system_alert, app_setting, admin_notification_pref,
    )

    # Register user loader
    from app.model.entities.admin_user import AdminUser

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(AdminUser, int(user_id))

    # Register blueprints
    from app.rest.controllers.auth_controller import auth_bp
    from app.rest.controllers.dashboard_controller import dashboard_bp
    from app.rest.controllers.users_controller import users_bp
    from app.rest.controllers.projects_controller import projects_bp
    from app.rest.controllers.sync_controller import sync_bp
    from app.rest.controllers.admin_controller import audit_bp
    from app.rest.controllers.reports_controller import reports_bp
    from app.rest.controllers.roles_controller import roles_bp
    from app.rest.controllers.alerts_controller import alerts_bp
    from app.rest.controllers.metrics_controller import metrics_bp
    from app.rest.controllers.account_controller import account_bp
    from app.rest.controllers.admins_controller import admins_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(admins_bp)

    # Seed default roles and alert thresholds if DB is ready (idempotent)
    with app.app_context():
        try:
            from app.model.services.roles_service import seed_default_roles
            seed_default_roles()
        except Exception:
            pass  # DB might not be migrated yet
        try:
            from app.model.entities.app_setting import seed_defaults
            seed_defaults()
        except Exception:
            pass  # DB might not be migrated yet

    # ─── Filtros de Jinja ─────────────────────────────────────────────────
    # `localtime` convierte un datetime aware (almacenado en UTC) a la zona
    # horaria del sistema (configurada con la variable de entorno `TZ`).
    # Si el datetime viene "naive" lo asume UTC.
    @app.template_filter("localtime")
    def _localtime(dt):
        if dt is None:
            return None
        from datetime import timezone as _tz
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        return dt.astimezone()  # zona del sistema (TZ del contenedor)

    # `localdt` formatea un datetime aware ya en zona local con strftime.
    # Uso: {{ dt | localdt('%d/%m %H:%M') }}
    @app.template_filter("localdt")
    def _localdt(dt, fmt="%d/%m/%Y %H:%M"):
        if dt is None:
            return ""
        return _localtime(dt).strftime(fmt)

    # Context processor: inject ACTIVE alert count for sidebar badge.
    # Active = is_resolved == False. This is shown on every page so the badge
    # is always visible, not only inside /alertas/. The query is a single
    # COUNT — cheap enough to run per-request without caching.
    @app.context_processor
    def inject_alert_counts():
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            try:
                from app.model.services import alerts_service
                return {"sidebar_active_alerts": alerts_service.get_active_count()}
            except Exception:
                pass
        return {"sidebar_active_alerts": 0}

    # Register error handlers
    _register_error_handlers(app)

    # Arranca APScheduler para las programaciones (SyncSchedule). No-op si
    # SCHEDULER_ENABLED=False, en el watcher del autoreloader, o si APScheduler
    # no está instalado.
    try:
        from app.etl.scheduler import init_scheduler
        init_scheduler(app)
    except Exception as exc:
        # No queremos que un fallo del scheduler tumbe la app entera.
        logging.getLogger(__name__).warning(
            "init_scheduler falló: %s", exc, exc_info=True,
        )

    return app


def _register_error_handlers(app: Flask) -> None:
    from flask import render_template

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500
