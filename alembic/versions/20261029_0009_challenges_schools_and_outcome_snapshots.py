"""challenges schools and outcome snapshots

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-29 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.base  # noqa: F401  (custom column types such as UTCDateTime)


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('schools',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('created_at', app.db.base.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_schools'))
    )
    op.create_table('challenges',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('creator_id', sa.Uuid(), nullable=False),
    sa.Column('source_exam_id', sa.Uuid(), nullable=False),
    sa.Column('question_ids', sa.String(length=400), nullable=False),
    sa.Column('creator_score', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('created_at', app.db.base.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['creator_id'], ['users.id'], name=op.f('fk_challenges_creator_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_challenges')),
    sa.UniqueConstraint('code', name=op.f('uq_challenges_code')),
    sa.UniqueConstraint('source_exam_id', name=op.f('uq_challenges_source_exam_id'))
    )
    with op.batch_alter_table('challenges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_challenges_creator_id'), ['creator_id'], unique=False)

    op.create_table('school_classes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('school_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('join_code', sa.String(length=12), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', app.db.base.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name=op.f('fk_school_classes_school_id_schools'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_school_classes')),
    sa.UniqueConstraint('join_code', name=op.f('uq_school_classes_join_code'))
    )
    with op.batch_alter_table('school_classes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_school_classes_school_id'), ['school_id'], unique=False)

    op.create_table('school_instructors',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('school_id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('created_at', app.db.base.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['school_id'], ['schools.id'], name=op.f('fk_school_instructors_school_id_schools'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_school_instructors')),
    sa.UniqueConstraint('school_id', 'email', name='uq_school_instructors_school_email')
    )
    with op.batch_alter_table('school_instructors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_school_instructors_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_school_instructors_school_id'), ['school_id'], unique=False)

    op.create_table('class_members',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('class_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('joined_at', app.db.base.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['school_classes.id'], name=op.f('fk_class_members_class_id_school_classes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_class_members_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_class_members')),
    sa.UniqueConstraint('class_id', 'user_id', name='uq_class_members_class_user')
    )
    with op.batch_alter_table('class_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_class_members_class_id'), ['class_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_class_members_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('exam_attempts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('challenge_id', sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f('ix_exam_attempts_challenge_id'), ['challenge_id'], unique=False)
        batch_op.create_foreign_key(batch_op.f('fk_exam_attempts_challenge_id_challenges'), 'challenges', ['challenge_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('exam_outcomes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recent_average', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('mock_exams', sa.Integer(), nullable=True))



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('exam_outcomes', schema=None) as batch_op:
        batch_op.drop_column('mock_exams')
        batch_op.drop_column('recent_average')

    with op.batch_alter_table('exam_attempts', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_exam_attempts_challenge_id_challenges'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_exam_attempts_challenge_id'))
        batch_op.drop_column('challenge_id')

    with op.batch_alter_table('class_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_class_members_user_id'))
        batch_op.drop_index(batch_op.f('ix_class_members_class_id'))

    op.drop_table('class_members')
    with op.batch_alter_table('school_instructors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_school_instructors_school_id'))
        batch_op.drop_index(batch_op.f('ix_school_instructors_email'))

    op.drop_table('school_instructors')
    with op.batch_alter_table('school_classes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_school_classes_school_id'))

    op.drop_table('school_classes')
    with op.batch_alter_table('challenges', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_challenges_creator_id'))

    op.drop_table('challenges')
    op.drop_table('schools')
