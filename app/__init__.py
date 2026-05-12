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
        sync_run, audit_log, project_sync_log,
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
    from app.rest.controllers.admin_controller import audit_bp, dev_bp
    from app.modules.reports.routes import reports_bp
    from app.rest.controllers.roles_controller import roles_bp
    from app.rest.controllers.alerts_controller import alerts_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(dev_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(alerts_bp)

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

    # Context processor: inject unread alert count for sidebar badge
    @app.context_processor
    def inject_alert_counts():
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            try:
                from app.model.services import alerts_service
                return {"sidebar_unread_alerts": alerts_service.get_unread_count()}
            except Exception:
                pass
        return {"sidebar_unread_alerts": 0}

    # Register error handlers
    _register_error_handlers(app)

    return app


def _register_error_handlers(app: Flask) -> None:
    from flask import render_template

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500
