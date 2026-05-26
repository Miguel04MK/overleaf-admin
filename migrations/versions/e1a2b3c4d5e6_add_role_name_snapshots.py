"""Add role_from_name / role_to_name snapshot columns to role_change_logs

Revision ID: e1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-05-24 12:00:00.000000

These columns capture the role name at the time of the change so the
audit history stays readable even after a role is deleted.
"""
from alembic import op
import sqlalchemy as sa

revision = "e1a2b3c4d5e6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "role_change_logs",
        sa.Column("role_from_name", sa.String(64), nullable=True),
    )
    op.add_column(
        "role_change_logs",
        sa.Column("role_to_name", sa.String(64), nullable=True),
    )

    # Back-fill existing rows from the roles table where the FK is still valid.
    op.execute(
        """
        UPDATE role_change_logs
        SET role_from_name = r.name
        FROM roles r
        WHERE role_change_logs.role_from_id = r.id
          AND role_change_logs.role_from_name IS NULL
        """
    )
    op.execute(
        """
        UPDATE role_change_logs
        SET role_to_name = r.name
        FROM roles r
        WHERE role_change_logs.role_to_id = r.id
          AND role_change_logs.role_to_name IS NULL
        """
    )


def downgrade():
    op.drop_column("role_change_logs", "role_to_name")
    op.drop_column("role_change_logs", "role_from_name")
