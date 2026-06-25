"""drop ip_address from audit_logs

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a8
Create Date: 2026-05-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision      = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a8'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_column('ip_address')


def downgrade():
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('ip_address', sa.String(length=45), nullable=True)
        )
