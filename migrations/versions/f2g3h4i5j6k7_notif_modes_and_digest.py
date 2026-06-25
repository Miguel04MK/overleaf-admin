"""Notification modes (immediate vs digest) + digest_frequency; drop service_down

Revision ID: f2g3h4i5j6k7
Revises: e1a2b3c4d5e6
Create Date: 2026-05-26 12:00:00.000000

Cambios en admin_notification_prefs:
  - ADD digest_frequency (VARCHAR 16, default 'disabled')
  - ADD notify_*_digest_only (BOOLEAN, default FALSE) por cada tipo restante.
    Si está a True, el tipo va sólo en el resumen periódico; si está a False
    (y notify_* es True), va inmediato.
  - DROP notify_service_down (a petición del usuario).
"""
from alembic import op
import sqlalchemy as sa


revision      = 'f2g3h4i5j6k7'
down_revision = 'e1a2b3c4d5e6'
branch_labels = None
depends_on    = None


_DIGEST_ONLY_COLS = [
    "notify_critical_digest_only",
    "notify_danger_digest_only",
    "notify_warning_digest_only",
    "notify_info_digest_only",
    "notify_sync_failed_digest_only",
    "notify_quota_exceeded_digest_only",
    "notify_quota_warning_digest_only",
    "notify_project_limit_exceeded_digest_only",
    "notify_project_limit_warning_digest_only",
    "notify_repeated_errors_digest_only",
    "notify_administrative_warning_digest_only",
]


def upgrade():
    with op.batch_alter_table("admin_notification_prefs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("digest_frequency", sa.String(length=16),
                      nullable=False, server_default="disabled")
        )
        for col in _DIGEST_ONLY_COLS:
            batch_op.add_column(
                sa.Column(col, sa.Boolean(), nullable=False, server_default="false")
            )
        batch_op.drop_column("notify_service_down")


def downgrade():
    with op.batch_alter_table("admin_notification_prefs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("notify_service_down", sa.Boolean(),
                      nullable=False, server_default="true")
        )
        for col in reversed(_DIGEST_ONLY_COLS):
            batch_op.drop_column(col)
        batch_op.drop_column("digest_frequency")
