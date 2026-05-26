"""Add sync_schedules table for multiple periodic schedules

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f456ab
Create Date: 2026-05-22 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision      = 'd4e5f6a7b8c9'
down_revision = 'c1d2e3f456ab'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'sync_schedules',
        sa.Column('id',               sa.Integer(),          nullable=False),
        sa.Column('name',             sa.String(length=128), nullable=False),
        sa.Column('sync_type',        sa.String(length=32),  nullable=False, server_default='full'),
        sa.Column('interval_minutes', sa.Integer(),          nullable=False, server_default='60'),
        sa.Column('enabled',          sa.Boolean(),          nullable=False, server_default='true'),
        sa.Column('last_run_at',      sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at',      sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',       sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by',       sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('sync_schedules')
