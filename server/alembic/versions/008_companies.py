"""create companies table

Revision ID: 008_companies
Revises: 007_hscode_uom_mappings
Create Date: 2026-01-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "008_companies"
down_revision: Union[str, None] = "007_hscode_uom_mappings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create companies table
    op.create_table(
        "companies",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("sst_default_behavior", sa.String(50), nullable=False, server_default="mida_only"),
        sa.Column("dual_flag_routing", sa.String(50), nullable=False, server_default="mida"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Create index on company name for faster lookups
    op.create_index("ix_companies_name", "companies", ["name"])
    
    # Seed initial companies: HICOM and Hong Leong
    op.execute(
        """
        INSERT INTO companies (id, name, sst_default_behavior, dual_flag_routing, created_at)
        VALUES 
            (gen_random_uuid(), 'HICOM YAMAHA MOTOR SDN BHD', 'all_on', 'form_d', NOW()),
            (gen_random_uuid(), 'HONG LEONG YAMAHA MOTOR SDN BHD', 'mida_only', 'mida', NOW())
        """
    )


def downgrade() -> None:
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_table("companies")
