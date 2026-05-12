"""
seed_dev_admins.py
------------------
Creates two development admin accounts with default notification preferences.

Idempotent — safe to run multiple times. Existing accounts are left untouched.

Usage:
    cd overleaf-admin
    python scripts/seed_dev_admins.py
"""
import sys
import os

# Make sure the app package is importable when run from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from app.config.extensions import db
from app.model.entities.admin_user import AdminUser
from app.model.entities.admin_notification_pref import AdminNotificationPref

ADMINS = [
    {
        "username": "jorguejuan69",
        "email":    "jorguejuan69@gmail.com",
        "password": "admin",
    },
    {
        "username": "candyalvarez2004",
        "email":    "candyalvarez2004@gmail.com",
        "password": "admin",
    },
]


def seed():
    app = create_app()
    with app.app_context():
        created = 0
        for data in ADMINS:
            existing = AdminUser.query.filter(
                (AdminUser.username == data["username"]) |
                (AdminUser.email    == data["email"])
            ).first()

            if existing:
                print(f"  [skip] {data['email']} — ya existe (id={existing.id})")
                continue

            admin = AdminUser(
                username=data["username"],
                email=data["email"],
                is_active=True,
            )
            admin.set_password(data["password"])
            db.session.add(admin)
            db.session.flush()  # get admin.id before creating prefs

            # Create default notification preferences
            pref = AdminNotificationPref(admin_id=admin.id)
            db.session.add(pref)

            print(f"  [created] {data['email']} (username: {data['username']})")
            created += 1

        db.session.commit()
        print(f"\n[OK] Completado: {created} admin(s) creado(s), "
              f"{len(ADMINS) - created} omitido(s).")


if __name__ == "__main__":
    seed()
