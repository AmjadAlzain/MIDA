"""Rename invoice_number to declaration_form_reg_no

Revision ID: 011_rename_invoice_to_declaration
Revises: 010_add_dummy_flag
Create Date: 2026-02-04

This migration:
1. Drops the old declaration_form_reg_no column (which was optional and redundant)
2. Drops the invoice_line column (not needed)
3. Renames invoice_number to declaration_form_reg_no
4. Updates the index to use the new column name
5. Updates all views to use the new column name
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "011_decl_form_reg"
down_revision: Union[str, None] = "010_add_dummy_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Drop all views FIRST (they depend on the columns we're modifying)
    op.execute("DROP VIEW IF EXISTS vw_import_history_by_item CASCADE")
    op.execute("DROP VIEW IF EXISTS vw_imports_port_klang CASCADE")
    op.execute("DROP VIEW IF EXISTS vw_imports_klia CASCADE")
    op.execute("DROP VIEW IF EXISTS vw_imports_bukit_kayu_hitam CASCADE")
    
    # Step 2: Drop the old (redundant) declaration_form_reg_no column
    op.drop_column("mida_import_records", "declaration_form_reg_no")
    
    # Step 3: Drop the invoice_line column
    op.drop_column("mida_import_records", "invoice_line")
    
    # Step 4: Drop the old index on invoice_number
    op.drop_index("ix_mida_import_records_invoice_number", table_name="mida_import_records")
    
    # Step 5: Rename invoice_number to declaration_form_reg_no
    op.alter_column(
        "mida_import_records",
        "invoice_number",
        new_column_name="declaration_form_reg_no",
        comment="Declaration Form Registration Number"
    )
    
    # Step 6: Create new index on declaration_form_reg_no
    op.create_index(
        "ix_mida_import_records_declaration_form_reg_no",
        "mida_import_records",
        ["declaration_form_reg_no"]
    )
    
    # Step 7: Recreate all import views with the updated column
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
            ir.quantity_imported,
            ir.port,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ir.certificate_item_id = ci.id
        JOIN mida_certificates c ON ci.certificate_id = c.id
        ORDER BY ir.import_date DESC, ir.created_at DESC
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
            ir.import_date,
            ir.declaration_form_reg_no,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ir.certificate_item_id = ci.id
        JOIN mida_certificates c ON ci.certificate_id = c.id
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
            ir.import_date,
            ir.declaration_form_reg_no,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ir.certificate_item_id = ci.id
        JOIN mida_certificates c ON ci.certificate_id = c.id
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
            ir.import_date,
            ir.declaration_form_reg_no,
            ir.quantity_imported,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ir.certificate_item_id = ci.id
        JOIN mida_certificates c ON ci.certificate_id = c.id
        WHERE ir.port = 'bukit_kayu_hitam'
        ORDER BY ir.import_date DESC, ir.created_at DESC
    """)


def downgrade() -> None:
    # Drop views first
    op.execute("DROP VIEW IF EXISTS vw_import_history_by_item")
    op.execute("DROP VIEW IF EXISTS vw_imports_port_klang")
    op.execute("DROP VIEW IF EXISTS vw_imports_klia")
    op.execute("DROP VIEW IF EXISTS vw_imports_bukit_kayu_hitam")
    
    # Drop new index
    op.drop_index("ix_mida_import_records_declaration_form_reg_no", table_name="mida_import_records")
    
    # Rename declaration_form_reg_no back to invoice_number
    op.alter_column(
        "mida_import_records",
        "declaration_form_reg_no",
        new_column_name="invoice_number"
    )
    
    # Recreate old index
    op.create_index(
        "ix_mida_import_records_invoice_number",
        "mida_import_records",
        ["invoice_number"]
    )
    
    # Add back invoice_line column
    op.add_column(
        "mida_import_records",
        sa.Column("invoice_line", sa.Integer(), nullable=True)
    )
    
    # Add back old declaration_form_reg_no column
    op.add_column(
        "mida_import_records",
        sa.Column(
            "declaration_form_reg_no",
            sa.String(100),
            nullable=True,
            comment="Declaration Form Registration Number"
        )
    )
    
    # Recreate old views (with invoice_number and invoice_line)
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
            ir.quantity_imported,
            ir.port,
            ir.balance_before,
            ir.balance_after,
            ir.remarks,
            ir.created_at
        FROM mida_import_records ir
        JOIN mida_certificate_items ci ON ir.certificate_item_id = ci.id
        JOIN mida_certificates c ON ci.certificate_id = c.id
        ORDER BY ir.import_date DESC, ir.created_at DESC
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
        JOIN mida_certificate_items ci ON ir.certificate_item_id = ci.id
        JOIN mida_certificates c ON ci.certificate_id = c.id
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
        JOIN mida_certificate_items ci ON ir.certificate_item_id = ci.id
        JOIN mida_certificates c ON ci.certificate_id = c.id
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
        JOIN mida_certificate_items ci ON ir.certificate_item_id = ci.id
        JOIN mida_certificates c ON ci.certificate_id = c.id
        WHERE ir.port = 'bukit_kayu_hitam'
        ORDER BY ir.import_date DESC, ir.created_at DESC
    """)
