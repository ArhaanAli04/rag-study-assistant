"""add feedback fields to messages

Revision ID: 1e5877c62358
Revises: 
Create Date: 2025-12-11 19:45:09.392956

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e5877c62358'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('feedback', sa.String(), nullable=True))
    op.add_column('messages', sa.Column('feedback_comment', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'feedback_comment')
    op.drop_column('messages', 'feedback')
