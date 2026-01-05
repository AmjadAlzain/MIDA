"""create hscode_uom_mappings table

Revision ID: 007_hscode_uom_mappings
Revises: 006_add_soft_delete
Create Date: 2026-01-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "007_hscode_uom_mappings"
down_revision: Union[str, None] = "006_add_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create hscode_uom_mappings table
    op.create_table(
        "hscode_uom_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hs_code", sa.String(20), nullable=False, comment="Normalized HSCODE (dots removed)"),
        sa.Column("uom", sa.String(10), nullable=False, comment="Unit of measure: UNIT or KGM"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hs_code", name="uq_hscode_uom_mappings_hs_code"),
        sa.CheckConstraint("uom IN ('UNIT', 'KGM')", name="ck_hscode_uom_mappings_uom_valid"),
    )
    op.create_index("ix_hscode_uom_mappings_hs_code", "hscode_uom_mappings", ["hs_code"])
    
    # Seed data from CSV - this will be done via a separate script or API endpoint
    # The migration just creates the table structure
    # Data population is handled by the seed_hscode_uom_data() function in the repo


def downgrade() -> None:
    op.drop_index("ix_hscode_uom_mappings_hs_code", table_name="hscode_uom_mappings")
    op.drop_table("hscode_uom_mappings")
