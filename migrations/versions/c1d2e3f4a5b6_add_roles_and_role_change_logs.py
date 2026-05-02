"""add roles and role_change_logs

Revision ID: c1d2e3f4a5b6
Revises: eb22496b9099
Create Date: 2026-04-29 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'eb22496b9099'
branch_labels = None
depends_on = None

_NOW = datetime.now(timezone.utc).isoformat()
_MB  = 1024 ** 2
_GB  = 1024 ** 3


def upgrade():
    # ── 1. Create roles table ─────────────────────────────────────────────────
    op.create_table(
        'roles',
        sa.Column('id',          sa.Integer(),    nullable=False),
        sa.Column('name',        sa.String(64),   nullable=False),
        sa.Column('description', sa.Text(),       nullable=True),
        sa.Column('storage_quota_bytes', sa.BigInteger(), nullable=True),
        sa.Column('max_projects',        sa.Integer(),    nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('color',      sa.String(32), nullable=False, server_default='secondary'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_roles_name'), ['name'], unique=True)

    # ── 2. Seed default roles ─────────────────────────────────────────────────
    op.execute(f"""
        INSERT INTO roles (name, description, storage_quota_bytes, max_projects,
                           is_default, color, created_at, updated_at)
        VALUES
            ('alumno',   'Estudiante con acceso estándar a la plataforma.',
             {500 * _MB}, 20, TRUE,  'primary', NOW(), NOW()),
            ('profesor', 'Docente con mayor capacidad de almacenamiento.',
             {5 * _GB}, 50, FALSE, 'info',    NOW(), NOW()),
            ('admin',    'Administrador de la plataforma. Sin límites aplicados.',
             NULL, NULL, FALSE, 'warning', NOW(), NOW())
        ON CONFLICT (name) DO NOTHING;
    """)

    # ── 3. Add role_id FK to overleaf_users ───────────────────────────────────
    with op.batch_alter_table('overleaf_users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_overleaf_users_role_id',
            'roles', ['role_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_overleaf_users_role_id', ['role_id'], unique=False)

    # Assign default role (alumno) to all existing users
    op.execute("""
        UPDATE overleaf_users
        SET role_id = (SELECT id FROM roles WHERE is_default = TRUE LIMIT 1)
        WHERE role_id IS NULL;
    """)

    # ── 4. Create role_change_logs table ──────────────────────────────────────
    op.create_table(
        'role_change_logs',
        sa.Column('id',           sa.Integer(),   nullable=False),
        sa.Column('user_id',      sa.Integer(),   nullable=False),
        sa.Column('role_from_id', sa.Integer(),   nullable=True),
        sa.Column('role_to_id',   sa.Integer(),   nullable=True),
        sa.Column('action',       sa.String(16),  nullable=False),
        sa.Column('changed_by',   sa.String(128), nullable=False),
        sa.Column('changed_at',   sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason',       sa.Text(),      nullable=True),
        sa.ForeignKeyConstraint(['user_id'],      ['overleaf_users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_from_id'], ['roles.id'],          ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['role_to_id'],   ['roles.id'],          ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('role_change_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_role_change_logs_user_id'),    ['user_id'],    unique=False)
        batch_op.create_index(batch_op.f('ix_role_change_logs_changed_at'), ['changed_at'], unique=False)


def downgrade():
    with op.batch_alter_table('role_change_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_role_change_logs_changed_at'))
        batch_op.drop_index(batch_op.f('ix_role_change_logs_user_id'))
    op.drop_table('role_change_logs')

    with op.batch_alter_table('overleaf_users', schema=None) as batch_op:
        batch_op.drop_index('ix_overleaf_users_role_id')
        batch_op.drop_constraint('fk_overleaf_users_role_id', type_='foreignkey')
        batch_op.drop_column('role_id')

    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_roles_name'))
    op.drop_table('roles')
