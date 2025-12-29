"""update certificate status values

Revision ID: 003_update_certificate_status
Revises: 002_mida_import_tracking
Create Date: 2024-12-29

Changes:
- Convert 'draft' status to 'active'
- Convert 'confirmed' status to 'active'  
- Add 'expired' status for certificates past their exemption_end_date
- Update check constraint to allow 'active' and 'expired' values
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_update_certificate_status"
down_revision: Union[str, None] = "002_mida_import_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Drop the old check constraint
    op.drop_constraint("ck_mida_certificates_status", "mida_certificates", type_="check")
    
    # Step 2: Convert all 'draft' certificates to 'active'
    op.execute("UPDATE mida_certificates SET status = 'active' WHERE status = 'draft'")
    
    # Step 3: Convert all 'confirmed' certificates to 'active'
    op.execute("UPDATE mida_certificates SET status = 'active' WHERE status = 'confirmed'")
    
    # Step 4: Set certificates with exemption_end_date < current date to 'expired'
    op.execute("""
        UPDATE mida_certificates 
        SET status = 'expired' 
        WHERE exemption_end_date IS NOT NULL 
          AND exemption_end_date < CURRENT_DATE
    """)
    
    # Step 5: Add new check constraint with 'active' and 'expired' values
    op.create_check_constraint(
        "ck_mida_certificates_status",
        "mida_certificates",
        "status IN ('active', 'expired')"
    )
    
    # Step 6: Update the default value for new certificates
    op.alter_column(
        "mida_certificates",
        "status",
        server_default="active"
    )


def downgrade() -> None:
    # Reverse the changes
    
    # Step 1: Drop the new check constraint
    op.drop_constraint("ck_mida_certificates_status", "mida_certificates", type_="check")
    
    # Step 2: Convert 'expired' back to 'confirmed'
    op.execute("UPDATE mida_certificates SET status = 'confirmed' WHERE status = 'expired'")
    
    # Step 3: Convert 'active' back to 'draft'
    op.execute("UPDATE mida_certificates SET status = 'draft' WHERE status = 'active'")
    
    # Step 4: Restore original check constraint
    op.create_check_constraint(
        "ck_mida_certificates_status",
        "mida_certificates",
        "status IN ('draft', 'confirmed')"
    )
    
    # Step 5: Restore original default
    op.alter_column(
        "mida_certificates",
        "status",
        server_default="draft"
    )
