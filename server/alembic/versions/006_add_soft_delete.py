"""add soft delete to mida_certificates

Revision ID: 006_add_soft_delete
Revises: 005_add_model_number
Create Date: 2026-01-04

Adds deleted_at column for soft delete functionality.
Replaces simple unique constraint on certificate_number with partial unique index
that only enforces uniqueness on non-deleted records.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006_add_soft_delete"
down_revision: Union[str, None] = "005_add_model_number"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deleted_at column (nullable - NULL means not deleted)
    op.add_column(
        "mida_certificates",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when certificate was soft-deleted (NULL = not deleted)"
        )
    )
    
    # Create index on deleted_at for efficient filtering
    op.create_index(
        "ix_mida_certificates_deleted_at",
        "mida_certificates",
        ["deleted_at"]
    )
    
    # Drop the existing unique constraint on certificate_number
    op.drop_constraint(
        "mida_certificates_certificate_number_key",
        "mida_certificates",
        type_="unique"
    )
    
    # Drop the existing index on certificate_number (we'll replace it)
    op.drop_index(
        "ix_mida_certificates_certificate_number",
        "mida_certificates"
    )
    
    # Create partial unique index - only enforces uniqueness on non-deleted records
    # This allows a new certificate with the same number after the old one is deleted
    op.execute("""
        CREATE UNIQUE INDEX ix_mida_certificates_cert_number_active 
        ON mida_certificates(certificate_number) 
        WHERE deleted_at IS NULL
    """)


def downgrade() -> None:
    # Drop the partial unique index
    op.drop_index(
        "ix_mida_certificates_cert_number_active",
        "mida_certificates"
    )
    
    # Recreate the original unique constraint
    # Note: This will fail if there are duplicate certificate_numbers in deleted records
    op.create_unique_constraint(
        "mida_certificates_certificate_number_key",
        "mida_certificates",
        ["certificate_number"]
    )
    
    # Recreate the original index
    op.create_index(
        "ix_mida_certificates_certificate_number",
        "mida_certificates",
        ["certificate_number"]
    )
    
    # Drop the deleted_at index
    op.drop_index(
        "ix_mida_certificates_deleted_at",
        "mida_certificates"
    )
    
    # Drop deleted_at column
    op.drop_column("mida_certificates", "deleted_at")
