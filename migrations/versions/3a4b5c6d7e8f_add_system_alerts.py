"""Add system_alerts table

Revision ID: 3a4b5c6d7e8f
Revises: b3c5f80b18eb
Create Date: 2026-05-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '3a4b5c6d7e8f'
down_revision = 'b3c5f80b18eb'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'system_alerts',
        sa.Column('id',                sa.Integer(),     nullable=False),
        sa.Column('type',              sa.String(64),    nullable=False),
        sa.Column('level',             sa.String(16),    nullable=False),
        sa.Column('title',             sa.String(255),   nullable=False),
        sa.Column('message',           sa.Text(),        nullable=False),
        sa.Column('entity_type',       sa.String(32),    nullable=True),
        sa.Column('entity_id',         sa.String(64),    nullable=True),
        sa.Column('is_read',           sa.Boolean(),     nullable=False),
        sa.Column('is_resolved',       sa.Boolean(),     nullable=False),
        sa.Column('created_at',        sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at',       sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by',       sa.String(64),    nullable=True),
        sa.Column('created_by_system', sa.Boolean(),     nullable=False),
        sa.Column('source',            sa.String(64),    nullable=True),
        sa.Column('extra_data_json',   sa.Text(),        nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('system_alerts', schema=None) as batch_op:
        batch_op.create_index('ix_system_alerts_type',        ['type'],        unique=False)
        batch_op.create_index('ix_system_alerts_level',       ['level'],       unique=False)
        batch_op.create_index('ix_system_alerts_is_read',     ['is_read'],     unique=False)
        batch_op.create_index('ix_system_alerts_is_resolved', ['is_resolved'], unique=False)
        batch_op.create_index('ix_system_alerts_created_at',  ['created_at'],  unique=False)
        batch_op.create_index('ix_system_alerts_entity',      ['entity_type', 'entity_id'], unique=False)


def downgrade():
    with op.batch_alter_table('system_alerts', schema=None) as batch_op:
        batch_op.drop_index('ix_system_alerts_entity')
        batch_op.drop_index('ix_system_alerts_created_at')
        batch_op.drop_index('ix_system_alerts_is_resolved')
        batch_op.drop_index('ix_system_alerts_is_read')
        batch_op.drop_index('ix_system_alerts_level')
        batch_op.drop_index('ix_system_alerts_type')
    op.drop_table('system_alerts')
