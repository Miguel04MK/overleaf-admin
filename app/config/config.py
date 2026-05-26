"""
Application configuration.
Values are read from environment variables (set in .env).
"""
import os


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # SQLAlchemy / PostgreSQL
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql://overleaf_admin:overleaf_admin_pass@localhost:5432/overleaf_admin",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # MongoDB (Overleaf CE)
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/sharelatex")
    MONGO_DB = os.getenv("MONGO_DB", "sharelatex")

    # Sync settings
    SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", 0))

    # APScheduler — sincronización periódica gobernada por SyncSchedule.
    # En desarrollo y producción se arranca por defecto; en testing se desactiva.
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"

    # Docker monitoring (optional)
    DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")
    OVERLEAF_COMPOSE_PROJECT = os.getenv("OVERLEAF_COMPOSE_PROJECT", "sharelatex")

    # Pagination
    ITEMS_PER_PAGE = 20


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    SCHEDULER_ENABLED = False  # No arrancar APScheduler durante los tests
    # SQLite in-memory with StaticPool so all connections share the same DB
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
    }


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
