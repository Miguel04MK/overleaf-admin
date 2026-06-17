"""add last_digest_sent_at to admin_notification_prefs

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-10

Tracker para el resumen periódico de alertas: marca cuándo se envió el último
digest a cada admin, para que el scheduler decida si toca enviar el siguiente
según `digest_frequency` y `digest_hour`.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision      = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('admin_notification_prefs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('last_digest_sent_at', sa.DateTime(timezone=True), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('admin_notification_prefs', schema=None) as batch_op:
        batch_op.drop_column('last_digest_sent_at')
