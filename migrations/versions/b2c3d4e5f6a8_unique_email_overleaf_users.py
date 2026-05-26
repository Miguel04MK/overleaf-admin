"""Add UNIQUE constraint on overleaf_users.email + clean existing duplicates

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-05-26 14:00:00.000000

Cambios:
  1. DATA MIGRATION — elimina filas duplicadas por email en overleaf_users,
     conservando la fila con synced_at más reciente (la más actualizada).
     Se registra en el log qué overleaf_ids se eliminaron.
  2. DDL — añade índice UNIQUE en la columna email.

El campo email ya era NOT NULL en la práctica (el extractor rechaza usuarios
sin email), pero sigue siendo nullable=True a nivel columna para permitir
el edge case de registros importados manualmente sin email.
PostgreSQL trata cada NULL como distinto, por lo que UNIQUE(nullable) funciona
correctamente: múltiples NULLs son permitidos.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision      = 'b2c3d4e5f6a8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on    = None


def upgrade():
    conn = op.get_bind()

    # ── 1. Limpiar duplicados por email ───────────────────────────────────────
    # Para cada grupo de emails duplicados conservamos el id con synced_at
    # más reciente y borramos el resto.
    duplicates = conn.execute(text("""
        SELECT email, COUNT(*) as cnt
        FROM overleaf_users
        WHERE email IS NOT NULL
        GROUP BY email
        HAVING COUNT(*) > 1
    """)).fetchall()

    for row in duplicates:
        email = row[0]
        # Obtener todos los ids de ese email ordenados por synced_at desc
        rows = conn.execute(text("""
            SELECT id, overleaf_id, synced_at
            FROM overleaf_users
            WHERE email = :email
            ORDER BY synced_at DESC NULLS LAST
        """), {"email": email}).fetchall()

        # El primero es el más reciente — lo conservamos
        keep_id        = rows[0][0]
        keep_oid       = rows[0][1]
        to_delete_ids  = [r[0] for r in rows[1:]]
        to_delete_oids = [r[1] for r in rows[1:]]

        print(
            f"[dedup] email={email!r}: conservando id={keep_id} overleaf_id={keep_oid!r}, "
            f"eliminando ids={to_delete_ids} overleaf_ids={to_delete_oids!r}"
        )

        for del_id in to_delete_ids:
            # Reasignar proyectos propiedad del duplicado → usuario que conservamos
            conn.execute(text("""
                UPDATE overleaf_projects
                SET owner_id = :keep_id
                WHERE owner_id = :del_id
            """), {"keep_id": keep_id, "del_id": del_id})

            # Reasignar memberships del duplicado → usuario que conservamos
            # (si ya existe membership para keep_id en el mismo proyecto, eliminar
            # la del duplicado para no violar el unique(project_id, user_id))
            conn.execute(text("""
                DELETE FROM project_members
                WHERE user_id = :del_id
                  AND project_id IN (
                      SELECT project_id FROM project_members WHERE user_id = :keep_id
                  )
            """), {"del_id": del_id, "keep_id": keep_id})

            conn.execute(text("""
                UPDATE project_members
                SET user_id = :keep_id
                WHERE user_id = :del_id
            """), {"keep_id": keep_id, "del_id": del_id})

            # Reasignar role_change_logs
            conn.execute(text("""
                UPDATE role_change_logs
                SET user_id = :keep_id
                WHERE user_id = :del_id
            """), {"keep_id": keep_id, "del_id": del_id})

        conn.execute(text("""
            DELETE FROM overleaf_users
            WHERE id = ANY(:ids)
        """), {"ids": to_delete_ids})

    # ── 2. Añadir constraint UNIQUE ───────────────────────────────────────────
    with op.batch_alter_table("overleaf_users", schema=None) as batch_op:
        batch_op.create_index(
            "ix_overleaf_users_email",
            ["email"],
            unique=True,
        )


def downgrade():
    with op.batch_alter_table("overleaf_users", schema=None) as batch_op:
        batch_op.drop_index("ix_overleaf_users_email")
