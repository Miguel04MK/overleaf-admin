"""Add users_delta and projects_delta to sync_runs

Revision ID: a1b2c3d4e5f6
Revises: 995593f824d9
Create Date: 2026-04-20 10:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '995593f824d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('users_delta', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('projects_delta', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_column('projects_delta')
        batch_op.drop_column('users_delta')
