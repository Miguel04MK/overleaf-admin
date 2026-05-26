"""Extend sync_runs with sync_type and breakdown counters

Revision ID: c1d2e3f456ab
Revises: 8f9a0b1c2d3e
Create Date: 2026-05-22 16:00:00.000000

Adds the columns needed for the new sync module:
- sync_type: full / users / projects / resync_total / scheduled
- users_created / users_updated and projects_created / projects_updated
- members_synced
- errors_count and error_detail
"""
from alembic import op
import sqlalchemy as sa


revision      = 'c1d2e3f456ab'
down_revision = '8f9a0b1c2d3e'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sync_type',        sa.String(length=32), nullable=False, server_default='full'))
        batch_op.add_column(sa.Column('users_created',    sa.Integer(),         nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('users_updated',    sa.Integer(),         nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('projects_created', sa.Integer(),         nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('projects_updated', sa.Integer(),         nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('members_synced',   sa.Integer(),         nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('errors_count',     sa.Integer(),         nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('error_detail',     sa.Text(),            nullable=True))


def downgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_column('error_detail')
        batch_op.drop_column('errors_count')
        batch_op.drop_column('members_synced')
        batch_op.drop_column('projects_updated')
        batch_op.drop_column('projects_created')
        batch_op.drop_column('users_updated')
        batch_op.drop_column('users_created')
        batch_op.drop_column('sync_type')
