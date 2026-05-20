"""
tests/conftest.py
-----------------
Shared pytest fixtures for the entire test suite.

Uses SQLite in-memory so no PostgreSQL connection is required.
Each test function gets a fresh database (create_all / drop_all).
"""
import pytest
from sqlalchemy.pool import StaticPool

from app import create_app
from app.config.extensions import db as _db
from app.model.entities.admin_user import AdminUser
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.role import Role


# ── Application ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """
    Single Flask app instance for the whole session.
    TestingConfig switches the DB to SQLite :memory: + StaticPool
    so all connections within a process share the same DB.
    """
    flask_app = create_app("testing")
    # Override engine options to use StaticPool (critical for in-memory SQLite)
    flask_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    return flask_app


# ── Database ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db(app):
    """
    Function-scoped fixture: creates all tables, yields the db object,
    then drops everything.  seed_default_roles() is called explicitly
    so each test starts with the three built-in roles.
    """
    with app.app_context():
        _db.create_all()
        from app.model.services.roles_service import seed_default_roles
        seed_default_roles()
        yield _db
        _db.session.remove()
        _db.drop_all()


# ── HTTP clients ──────────────────────────────────────────────────────────────

@pytest.fixture
def client(app, db):
    """Unauthenticated test client (redirects on protected routes)."""
    return app.test_client()


@pytest.fixture
def admin_user(db):
    """A persisted AdminUser used for authentication."""
    u = AdminUser(username="testadmin", email="admin@test.com")
    u.set_password("s3cr3t!")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def auth_client(app, db, admin_user):
    """
    Test client with an active Flask-Login session.
    Injects the _user_id directly into the session cookie so that
    @login_required routes succeed without hitting the login form.
    """
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = str(admin_user.id)
        sess["_fresh"] = True
    return c


# ── Domain helpers ────────────────────────────────────────────────────────────

def make_user(db, overleaf_id, email=None, first_name=None, last_name=None,
              is_admin=False, max_quota_bytes=None, role=None):
    """Helper: create and persist an OverleafUser."""
    u = OverleafUser(
        overleaf_id=overleaf_id,
        email=email or f"{overleaf_id}@test.com",
        first_name=first_name,
        last_name=last_name,
        is_admin=is_admin,
        max_quota_bytes=max_quota_bytes,
        role=role,
    )
    db.session.add(u)
    db.session.commit()
    return u


def make_project(db, overleaf_id, name=None, owner=None, size_bytes=0):
    """Helper: create and persist an OverleafProject."""
    p = OverleafProject(
        overleaf_id=overleaf_id,
        name=name or overleaf_id,
        owner=owner,
        owner_overleaf_id=owner.overleaf_id if owner else None,
        size_bytes=size_bytes,
    )
    db.session.add(p)
    db.session.commit()
    return p


def make_role(db, name, description=None, quota_bytes=None,
              max_projects=None, is_default=False, color="secondary"):
    """Helper: create and persist a Role (not a preset one)."""
    r = Role(
        name=name,
        description=description,
        storage_quota_bytes=quota_bytes,
        max_projects=max_projects,
        is_default=is_default,
        color=color,
    )
    db.session.add(r)
    db.session.commit()
    return r
