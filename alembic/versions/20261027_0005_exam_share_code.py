"""exam share code

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('exam_attempts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('share_code', sa.String(length=16), nullable=True))
        batch_op.create_unique_constraint(batch_op.f('uq_exam_attempts_share_code'), ['share_code'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('exam_attempts', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_exam_attempts_share_code'), type_='unique')
        batch_op.drop_column('share_code')
