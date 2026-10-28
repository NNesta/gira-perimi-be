"""exam outcomes

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.base  # noqa: F401  (custom column types such as UTCDateTime)


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('exam_outcomes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('exam_date', sa.Date(), nullable=False),
    sa.Column('result', sa.String(length=12), nullable=False),
    sa.Column('testimonial', sa.Text(), nullable=True),
    sa.Column('testimonial_public', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('testimonial_status', sa.String(length=12), nullable=False),
    sa.Column('created_at', app.db.base.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.base.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_exam_outcomes_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_exam_outcomes')),
    sa.UniqueConstraint('user_id', 'exam_date', name='uq_exam_outcomes_user_date')
    )
    with op.batch_alter_table('exam_outcomes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_exam_outcomes_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('exam_outcomes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_exam_outcomes_user_id'))

    op.drop_table('exam_outcomes')
