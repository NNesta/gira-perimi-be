"""push subscriptions

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.base  # noqa: F401  (custom column types such as UTCDateTime)


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('push_subscriptions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('endpoint', sa.String(length=1024), nullable=False),
    sa.Column('p256dh', sa.String(length=255), nullable=False),
    sa.Column('auth', sa.String(length=64), nullable=False),
    sa.Column('created_at', app.db.base.UTCDateTime(), nullable=False),
    sa.Column('last_sent_at', app.db.base.UTCDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_push_subscriptions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_push_subscriptions')),
    sa.UniqueConstraint('endpoint', name=op.f('uq_push_subscriptions_endpoint'))
    )
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_push_subscriptions_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_push_subscriptions_user_id'))

    op.drop_table('push_subscriptions')
