"""add declaration form registration number

Revision ID: 004_add_declaration_form_reg_no
Revises: 003_update_certificate_status
Create Date: 2024-12-29

Adds declaration_form_reg_no column to mida_import_records table
and updates all import views to include this field.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004_add_declaration_form_reg_no"
down_revision: Union[str, None] = "003_update_certificate_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new column to mida_import_records
    op.add_column(
        "mida_import_records",
        sa.Column(
            "declaration_form_reg_no",
            sa.String(100),
            nullable=True,
            comment="Declaration Form Registration Number"
        )
    )
    
    # Drop and recreate all import views with the new column
    op.execute("DROP VIEW IF EXISTS vw_import_history_by_item")
    op.execute("DROP VIEW IF EXISTS vw_imports_port_klang")
    op.execute("DROP VIEW IF EXISTS vw_imports_klia")
    op.execute("DROP VIEW IF EXISTS vw_imports_bukit_kayu_hitam")
    
    # View 1: Item-specific import history (all ports for one item)
    op.execute("""
        CREATE VIEW vw_import_history_by_item AS
        SELECT
            ir.id AS import_record_id,
            ir.certificate_item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ir.import_date,
            ir.declaration_form_reg_no,
            ir.invoice_number,
            ir.invoice_line,
            ir.port,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
        JOIN mida_certificates c ON c.id = ci.certificate_id
        ORDER BY ir.certificate_item_id, ir.created_at
    """)
    
    # View 2: Port Klang imports
    op.execute("""
        CREATE VIEW vw_imports_port_klang AS
        SELECT
            ir.id AS import_record_id,
            ir.certificate_item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ci.port_klang_qty AS approved_port_qty,
            ci.remaining_port_klang AS remaining_port_qty,
            ir.import_date,
            ir.declaration_form_reg_no,
            ir.invoice_number,
            ir.invoice_line,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
        JOIN mida_certificates c ON c.id = ci.certificate_id
        WHERE ir.port = 'port_klang'
        ORDER BY ir.import_date DESC, ir.created_at DESC
    """)
    
    # View 3: KLIA imports
    op.execute("""
        CREATE VIEW vw_imports_klia AS
        SELECT
            ir.id AS import_record_id,
            ir.certificate_item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ci.klia_qty AS approved_port_qty,
            ci.remaining_klia AS remaining_port_qty,
            ir.import_date,
            ir.declaration_form_reg_no,
            ir.invoice_number,
            ir.invoice_line,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
        JOIN mida_certificates c ON c.id = ci.certificate_id
        WHERE ir.port = 'klia'
        ORDER BY ir.import_date DESC, ir.created_at DESC
    """)
    
    # View 4: Bukit Kayu Hitam imports
    op.execute("""
        CREATE VIEW vw_imports_bukit_kayu_hitam AS
        SELECT
            ir.id AS import_record_id,
            ir.certificate_item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ci.bukit_kayu_hitam_qty AS approved_port_qty,
            ci.remaining_bukit_kayu_hitam AS remaining_port_qty,
            ir.import_date,
            ir.declaration_form_reg_no,
            ir.invoice_number,
            ir.invoice_line,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
        JOIN mida_certificates c ON c.id = ci.certificate_id
        WHERE ir.port = 'bukit_kayu_hitam'
        ORDER BY ir.import_date DESC, ir.created_at DESC
    """)


def downgrade() -> None:
    # Drop views first
    op.execute("DROP VIEW IF EXISTS vw_import_history_by_item")
    op.execute("DROP VIEW IF EXISTS vw_imports_port_klang")
    op.execute("DROP VIEW IF EXISTS vw_imports_klia")
    op.execute("DROP VIEW IF EXISTS vw_imports_bukit_kayu_hitam")
    
    # Drop the column
    op.drop_column("mida_import_records", "declaration_form_reg_no")
    
    # Recreate original views without declaration_form_reg_no
    op.execute("""
        CREATE VIEW vw_import_history_by_item AS
        SELECT
            ir.id AS import_record_id,
            ir.certificate_item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ir.import_date,
            ir.invoice_number,
            ir.invoice_line,
            ir.port,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
        JOIN mida_certificates c ON c.id = ci.certificate_id
        ORDER BY ir.certificate_item_id, ir.created_at
    """)
    
    op.execute("""
        CREATE VIEW vw_imports_port_klang AS
        SELECT
            ir.id AS import_record_id,
            ir.certificate_item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ci.port_klang_qty AS approved_port_qty,
            ci.remaining_port_klang AS remaining_port_qty,
            ir.import_date,
            ir.invoice_number,
            ir.invoice_line,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
        JOIN mida_certificates c ON c.id = ci.certificate_id
        WHERE ir.port = 'port_klang'
        ORDER BY ir.import_date DESC, ir.created_at DESC
    """)
    
    op.execute("""
        CREATE VIEW vw_imports_klia AS
        SELECT
            ir.id AS import_record_id,
            ir.certificate_item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ci.klia_qty AS approved_port_qty,
            ci.remaining_klia AS remaining_port_qty,
            ir.import_date,
            ir.invoice_number,
            ir.invoice_line,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
        JOIN mida_certificates c ON c.id = ci.certificate_id
        WHERE ir.port = 'klia'
        ORDER BY ir.import_date DESC, ir.created_at DESC
    """)
    
    op.execute("""
        CREATE VIEW vw_imports_bukit_kayu_hitam AS
        SELECT
            ir.id AS import_record_id,
            ir.certificate_item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ci.bukit_kayu_hitam_qty AS approved_port_qty,
            ci.remaining_bukit_kayu_hitam AS remaining_port_qty,
            ir.import_date,
            ir.invoice_number,
            ir.invoice_line,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
        JOIN mida_certificates c ON c.id = ci.certificate_id
        WHERE ir.port = 'bukit_kayu_hitam'
        ORDER BY ir.import_date DESC, ir.created_at DESC
    """)
