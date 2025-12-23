"""create mida certificates and items

Revision ID: 001_mida_certificates
Revises:
Create Date: 2024-12-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_mida_certificates"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create mida_certificates table
    op.create_table(
        "mida_certificates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("certificate_number", sa.String(100), nullable=False),
        sa.Column("company_name", sa.String(500), nullable=False),
        sa.Column("exemption_start_date", sa.Date(), nullable=True),
        sa.Column("exemption_end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("source_filename", sa.String(500), nullable=True),
        sa.Column("raw_ocr_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("certificate_number"),
        sa.CheckConstraint("status IN ('draft', 'confirmed')", name="ck_mida_certificates_status"),
    )
    op.create_index("ix_mida_certificates_certificate_number", "mida_certificates", ["certificate_number"])
    op.create_index("ix_mida_certificates_status", "mida_certificates", ["status"])

    # Create mida_certificate_items table
    op.create_table(
        "mida_certificate_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("certificate_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("hs_code", sa.String(20), nullable=False),
        sa.Column("item_name", sa.Text(), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(18, 3), nullable=True),
        sa.Column("uom", sa.String(50), nullable=False),
        sa.Column("port_klang_qty", sa.Numeric(18, 3), nullable=True),
        sa.Column("klia_qty", sa.Numeric(18, 3), nullable=True),
        sa.Column("bukit_kayu_hitam_qty", sa.Numeric(18, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["certificate_id"], ["mida_certificates.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("certificate_id", "line_no", name="uq_cert_line"),
        sa.CheckConstraint("line_no > 0", name="ck_line_no_positive"),
        sa.CheckConstraint("approved_quantity IS NULL OR approved_quantity >= 0", name="ck_approved_quantity_non_negative"),
        sa.CheckConstraint("port_klang_qty IS NULL OR port_klang_qty >= 0", name="ck_port_klang_qty_non_negative"),
        sa.CheckConstraint("klia_qty IS NULL OR klia_qty >= 0", name="ck_klia_qty_non_negative"),
        sa.CheckConstraint("bukit_kayu_hitam_qty IS NULL OR bukit_kayu_hitam_qty >= 0", name="ck_bukit_kayu_hitam_qty_non_negative"),
    )
    op.create_index("ix_mida_certificate_items_hs_code", "mida_certificate_items", ["hs_code"])

    # Create Table2 compatibility view for export/reporting
    # Joins header + items into a single row per item
    op.execute("""
        CREATE VIEW vw_table2_exemption_records AS
        SELECT
            c.id AS certificate_id,
            c.certificate_number,
            c.company_name,
            c.exemption_start_date,
            c.exemption_end_date,
            c.status,
            c.source_filename,
            i.id AS item_id,
            i.line_no,
            i.hs_code,
            i.item_name,
            i.approved_quantity,
            i.uom,
            i.port_klang_qty,
            i.klia_qty,
            i.bukit_kayu_hitam_qty,
            c.created_at AS certificate_created_at,
            i.created_at AS item_created_at
        FROM mida_certificates c
        JOIN mida_certificate_items i ON i.certificate_id = c.id
        ORDER BY c.certificate_number, i.line_no
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_table2_exemption_records")
    op.drop_index("ix_mida_certificate_items_hs_code", table_name="mida_certificate_items")
    op.drop_table("mida_certificate_items")
    op.drop_index("ix_mida_certificates_status", table_name="mida_certificates")
    op.drop_index("ix_mida_certificates_certificate_number", table_name="mida_certificates")
    op.drop_table("mida_certificates")
