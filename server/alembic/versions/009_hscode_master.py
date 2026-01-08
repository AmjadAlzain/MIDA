"""create hscode_master table

Revision ID: 009_hscode_master
Revises: 008_companies
Create Date: 2026-01-08

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009_hscode_master"
down_revision: Union[str, None] = "008_companies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create hscode_master table
    op.create_table(
        "hscode_master",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("part_name", sa.String(255), nullable=False, comment="MIDA part name for matching"),
        sa.Column("hs_code", sa.String(20), nullable=False, comment="8-digit HSCODE"),
        sa.Column("uom", sa.String(10), nullable=False, comment="Unit of measure: UNIT or KGM"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hscode_master_part_name", "hscode_master", ["part_name"])
    op.create_index("ix_hscode_master_hs_code", "hscode_master", ["hs_code"])


def downgrade() -> None:
    op.drop_index("ix_hscode_master_hs_code", table_name="hscode_master")
    op.drop_index("ix_hscode_master_part_name", table_name="hscode_master")
    op.drop_table("hscode_master")
