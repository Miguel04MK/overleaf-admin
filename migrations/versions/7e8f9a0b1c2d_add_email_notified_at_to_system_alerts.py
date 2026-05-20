"""Add email_notified_at to system_alerts

Revision ID: 7e8f9a0b1c2d
Revises: 6d7e8f9a0b1c
Create Date: 2026-05-11 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision      = '7e8f9a0b1c2d'
down_revision = '6d7e8f9a0b1c'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('system_alerts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('email_notified_at', sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index('ix_system_alerts_email_notified_at', ['email_notified_at'])


def downgrade():
    with op.batch_alter_table('system_alerts', schema=None) as batch_op:
        batch_op.drop_index('ix_system_alerts_email_notified_at')
        batch_op.drop_column('email_notified_at')
