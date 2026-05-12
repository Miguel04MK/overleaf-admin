"""Add admin_notification_prefs table

Revision ID: 6d7e8f9a0b1c
Revises: 5c6d7e8f9a0b
Create Date: 2026-05-11 10:05:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision      = '6d7e8f9a0b1c'
down_revision = '5c6d7e8f9a0b'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'admin_notification_prefs',
        sa.Column('id',       sa.Integer(), nullable=False),
        sa.Column('admin_id', sa.Integer(), nullable=False),
        # Level prefs
        sa.Column('notify_critical', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_danger',   sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_warning',  sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notify_info',     sa.Boolean(), nullable=False, server_default='false'),
        # Type prefs
        sa.Column('notify_service_down',            sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_sync_failed',             sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_quota_exceeded',          sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_quota_warning',           sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notify_project_limit_exceeded',  sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notify_project_limit_warning',   sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notify_repeated_errors',         sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notify_administrative_warning',  sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['admin_id'], ['admin_users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('admin_id'),
    )
    with op.batch_alter_table('admin_notification_prefs', schema=None) as batch_op:
        batch_op.create_index('ix_admin_notif_prefs_admin_id', ['admin_id'], unique=True)


def downgrade():
    with op.batch_alter_table('admin_notification_prefs', schema=None) as batch_op:
        batch_op.drop_index('ix_admin_notif_prefs_admin_id')
    op.drop_table('admin_notification_prefs')
