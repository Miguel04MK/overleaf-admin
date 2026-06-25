"""Add scheduled_hour to sync_schedules and digest_hour to admin_notification_prefs

Revision ID: a1b2c3d4e5f7
Revises: f2g3h4i5j6k7
Create Date: 2026-05-26 13:00:00.000000

Cambios:
  sync_schedules:
    - ADD scheduled_hour (INTEGER nullable) — hora del día (0-23) a la que se ejecuta;
      NULL significa sin hora fija (intervalo puro).

  admin_notification_prefs:
    - ADD digest_hour (INTEGER nullable) — hora del día (0-23) a la que se envía
      el resumen periódico; NULL = sin hora fija.
    - El campo digest_frequency pasa a admitir más valores:
      '12h', '3days', '5days', '2weeks', 'monthly' (además de los ya existentes).
      No requiere cambio de columna porque es VARCHAR(16) y los nuevos valores
      caben en ese tamaño.
"""
from alembic import op
import sqlalchemy as sa


revision      = 'a1b2c3d4e5f7'
down_revision = 'f2g3h4i5j6k7'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table("sync_schedules", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("scheduled_hour", sa.Integer(), nullable=True)
        )

    with op.batch_alter_table("admin_notification_prefs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("digest_hour", sa.Integer(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("admin_notification_prefs", schema=None) as batch_op:
        batch_op.drop_column("digest_hour")

    with op.batch_alter_table("sync_schedules", schema=None) as batch_op:
        batch_op.drop_column("scheduled_hour")
