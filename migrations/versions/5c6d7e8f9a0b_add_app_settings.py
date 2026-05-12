"""Add app_settings table for configurable thresholds

Revision ID: 5c6d7e8f9a0b
Revises: 4b5c6d7e8f9a
Create Date: 2026-05-11 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision      = '5c6d7e8f9a0b'
down_revision = '4b5c6d7e8f9a'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'app_settings',
        sa.Column('key',         sa.String(64),  nullable=False),
        sa.Column('value',       sa.String(255), nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('updated_at',  sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by',  sa.String(64),  nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade():
    op.drop_table('app_settings')
