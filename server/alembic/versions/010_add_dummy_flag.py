"""add is_dummy to mida_certificate_items

Revision ID: 010_add_dummy_flag
Revises: 009_hscode_master
Create Date: 2026-01-23

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "010_add_dummy_flag"
down_revision: Union[str, None] = "009_hscode_master"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('mida_certificate_items', sa.Column('is_dummy', sa.Boolean(), server_default='False', nullable=False))


def downgrade() -> None:
    op.drop_column('mida_certificate_items', 'is_dummy')
