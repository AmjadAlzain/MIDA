"""add model_number to mida_certificates

Revision ID: 005_add_model_number
Revises: 004_add_declaration_form_reg_no
Create Date: 2026-01-04

Adds model_number column to mida_certificates table.
This field stores the model number for the certificate.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005_add_model_number"
down_revision: Union[str, None] = "004_add_declaration_form_reg_no"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add model_number column with server_default for existing rows
    op.add_column(
        "mida_certificates",
        sa.Column(
            "model_number",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="Model number for the certificate"
        )
    )
    
    # Remove the server_default after adding the column
    # (new rows will get value from application code)
    op.alter_column(
        "mida_certificates",
        "model_number",
        server_default=None
    )


def downgrade() -> None:
    op.drop_column("mida_certificates", "model_number")
