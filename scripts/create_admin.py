"""
scripts/create_admin.py
-----------------------
Creates the default admin user in PostgreSQL.

Usage:
    python scripts/create_admin.py

Or with custom credentials via env:
    ADMIN_USERNAME=myadmin ADMIN_PASSWORD=mypass python scripts/create_admin.py

Default credentials: admin / admin
"""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.extensions import db
from app.models.admin_user import AdminUser


def create_admin():
    app = create_app()
    with app.app_context():
        username = os.getenv("ADMIN_USERNAME", "admin")
        password = os.getenv("ADMIN_PASSWORD", "admin")
        email = os.getenv("ADMIN_EMAIL", "admin@localhost")

        existing = AdminUser.query.filter_by(username=username).first()
        if existing:
            print(f"[INFO] El usuario admin '{username}' ya existe. No se crea de nuevo.")
            print(f"       Para restablecer la contraseña, elimina el registro manualmente.")
            return

        user = AdminUser(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        print(f"[OK] Usuario administrador creado:")
        print(f"     Usuario:    {username}")
        print(f"     Email:      {email}")
        print(f"     Contraseña: {password}")
        print(f"\n[!] Cambia la contraseña en producción.")


if __name__ == "__main__":
    create_admin()
