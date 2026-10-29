"""exam answered count

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('exam_attempts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('answered', sa.SmallInteger(), nullable=True))
    # Exams graded before this revision: count the answers they were graded with.
    op.execute(
        "UPDATE exam_attempts SET answered = ("
        "SELECT count(*) FROM exam_answers "
        "WHERE exam_answers.attempt_id = exam_attempts.id AND exam_answers.selected IS NOT NULL"
        ") WHERE status = 'completed'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('exam_attempts', schema=None) as batch_op:
        batch_op.drop_column('answered')
