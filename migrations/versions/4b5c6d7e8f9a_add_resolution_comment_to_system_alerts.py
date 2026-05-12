"""add resolution_comment to system_alerts

Revision ID: 4b5c6d7e8f9a
Revises: 3a4b5c6d7e8f
Create Date: 2026-05-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '4b5c6d7e8f9a'
down_revision = '3a4b5c6d7e8f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'system_alerts',
        sa.Column('resolution_comment', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column('system_alerts', 'resolution_comment')
