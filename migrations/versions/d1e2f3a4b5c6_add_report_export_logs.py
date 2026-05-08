"""add report_export_logs table

Revision ID: d1e2f3a4b5c6
Revises: eb22496b9099
Create Date: 2026-05-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "eb22496b9099"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_export_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("generated_by", sa.String(length=128), nullable=False, server_default="system"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("(now())")),
        sa.Column("filters_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_export_logs_report_type", "report_export_logs", ["report_type"])
    op.create_index("ix_report_export_logs_generated_at", "report_export_logs", ["generated_at"])


def downgrade():
    op.drop_index("ix_report_export_logs_generated_at", table_name="report_export_logs")
    op.drop_index("ix_report_export_logs_report_type", table_name="report_export_logs")
    op.drop_table("report_export_logs")
