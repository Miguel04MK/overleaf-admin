"""Add triggered_by_user to sync_runs

Revision ID: 8f9a0b1c2d3e
Revises: 7e8f9a0b1c2d
Create Date: 2026-05-16 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision      = '8f9a0b1c2d3e'
down_revision = '7e8f9a0b1c2d'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column(
        'sync_runs',
        sa.Column('triggered_by_user', sa.String(128), nullable=True),
    )


def downgrade():
    op.drop_column('sync_runs', 'triggered_by_user')
