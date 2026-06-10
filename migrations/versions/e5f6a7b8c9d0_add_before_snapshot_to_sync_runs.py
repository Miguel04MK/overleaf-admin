"""add users_before/projects_before snapshot columns to sync_runs

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-05-27

Añade dos columnas INTEGER nullable a sync_runs:
  - users_before    : total de OverleafUser en BD justo antes de ejecutar la sync
  - projects_before : total de OverleafProject en BD justo antes de ejecutar la sync

Con estos valores el delta (users_delta / projects_delta) pasa a ser:
  delta = registros creados en esta sync (users_created / projects_created)
  y la UI muestra: {after} / {before} +{delta}

Los registros históricos quedan con NULL en estas columnas y el front-end
los muestra en el formato legacy (users_synced / users_found).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision      = 'e5f6a7b8c9d0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('users_before',    sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('projects_before', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_column('projects_before')
        batch_op.drop_column('users_before')
