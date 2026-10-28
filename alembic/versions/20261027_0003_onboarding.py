"""onboarding

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.base  # noqa: F401  (custom column types such as UTCDateTime)


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('onboarded_at', app.db.base.UTCDateTime(), nullable=True))

    # The welcome is for accounts that have not started yet: learners who already studied skip it.
    op.execute(
        "UPDATE users SET onboarded_at = created_at"
        " WHERE id IN (SELECT user_id FROM practice_answers)"
        " OR id IN (SELECT user_id FROM exam_attempts)"
        " OR id IN (SELECT user_id FROM lesson_progress)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('onboarded_at')
