"""session versions and email sign-in links

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-29 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.base  # noqa: F401  (custom column types such as UTCDateTime)


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing sessions carry no version, which counts as 0: nobody is signed out by this upgrade.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_version', sa.Integer(), server_default=sa.text('0'), nullable=False))
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_version', sa.Integer(), server_default=sa.text('0'), nullable=False))

    op.create_table('email_logins',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('created_at', app.db.base.UTCDateTime(), nullable=False),
    sa.Column('expires_at', app.db.base.UTCDateTime(), nullable=False),
    sa.Column('used_at', app.db.base.UTCDateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_logins')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_email_logins_token_hash'))
    )
    with op.batch_alter_table('email_logins', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_logins_email'), ['email'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('email_logins', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_logins_email'))

    op.drop_table('email_logins')
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.drop_column('session_version')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('session_version')
