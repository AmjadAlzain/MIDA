"""add import tracking tables, views, triggers

Revision ID: 002_mida_import_tracking
Revises: 001_mida_certificates
Create Date: 2024-12-29

This migration adds:
1. Remaining quantity columns to mida_certificate_items
2. Warning threshold and quantity status columns
3. mida_import_records master table for tracking all imports
4. Views for item-specific, port-specific, and item+port queries
5. Triggers for automatic balance calculation and status updates
6. Functions for querying import history
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_mida_import_tracking"
down_revision: Union[str, None] = "001_mida_certificates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Default warning threshold (can be overridden per item)
DEFAULT_WARNING_THRESHOLD = 100


def upgrade() -> None:
    # ==========================================================================
    # STEP 1: Add new columns to mida_certificate_items
    # ==========================================================================
    
    # Remaining quantity columns (initialized to approved quantities)
    op.add_column(
        "mida_certificate_items",
        sa.Column("remaining_quantity", sa.Numeric(18, 3), nullable=True)
    )
    op.add_column(
        "mida_certificate_items",
        sa.Column("remaining_port_klang", sa.Numeric(18, 3), nullable=True)
    )
    op.add_column(
        "mida_certificate_items",
        sa.Column("remaining_klia", sa.Numeric(18, 3), nullable=True)
    )
    op.add_column(
        "mida_certificate_items",
        sa.Column("remaining_bukit_kayu_hitam", sa.Numeric(18, 3), nullable=True)
    )
    
    # Warning threshold (user-configurable per item)
    op.add_column(
        "mida_certificate_items",
        sa.Column(
            "warning_threshold",
            sa.Numeric(18, 3),
            nullable=True,
            comment="Quantity level below which warnings are triggered"
        )
    )
    
    # Quantity status enum
    op.add_column(
        "mida_certificate_items",
        sa.Column(
            "quantity_status",
            sa.String(20),
            nullable=False,
            server_default="normal",
            comment="Current status: normal, warning, depleted, overdrawn"
        )
    )
    
    # Add check constraint for quantity_status
    op.create_check_constraint(
        "ck_quantity_status_valid",
        "mida_certificate_items",
        "quantity_status IN ('normal', 'warning', 'depleted', 'overdrawn')"
    )
    
    # Add check constraint for warning_threshold
    op.create_check_constraint(
        "ck_warning_threshold_non_negative",
        "mida_certificate_items",
        "warning_threshold IS NULL OR warning_threshold >= 0"
    )
    
    # Add index for quantity_status queries
    op.create_index(
        "ix_mida_certificate_items_quantity_status",
        "mida_certificate_items",
        ["quantity_status"]
    )
    
    # Initialize remaining quantities from approved quantities for existing rows
    op.execute("""
        UPDATE mida_certificate_items
        SET remaining_quantity = approved_quantity,
            remaining_port_klang = port_klang_qty,
            remaining_klia = klia_qty,
            remaining_bukit_kayu_hitam = bukit_kayu_hitam_qty
    """)
    
    # ==========================================================================
    # STEP 2: Create mida_import_records master table
    # ==========================================================================
    
    op.create_table(
        "mida_import_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("certificate_item_id", sa.Uuid(), nullable=False),
        sa.Column("import_date", sa.Date(), nullable=False),
        sa.Column("invoice_number", sa.String(100), nullable=False),
        sa.Column("invoice_line", sa.Integer(), nullable=True),
        sa.Column("quantity_imported", sa.Numeric(18, 3), nullable=False),
        sa.Column(
            "port",
            sa.String(30),
            nullable=False,
            comment="Import port: port_klang, klia, bukit_kayu_hitam"
        ),
        sa.Column("balance_before", sa.Numeric(18, 3), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 3), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["certificate_item_id"],
            ["mida_certificate_items.id"],
            ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "port IN ('port_klang', 'klia', 'bukit_kayu_hitam')",
            name="ck_import_port_valid"
        ),
        sa.CheckConstraint(
            "quantity_imported > 0",
            name="ck_quantity_imported_positive"
        ),
    )
    
    # Create indexes for efficient queries
    op.create_index(
        "ix_mida_import_records_certificate_item_id",
        "mida_import_records",
        ["certificate_item_id"]
    )
    op.create_index(
        "ix_mida_import_records_port",
        "mida_import_records",
        ["port"]
    )
    op.create_index(
        "ix_mida_import_records_import_date",
        "mida_import_records",
        ["import_date"]
    )
    op.create_index(
        "ix_mida_import_records_invoice_number",
        "mida_import_records",
        ["invoice_number"]
    )
    op.create_index(
        "ix_mida_import_records_item_port_date",
        "mida_import_records",
        ["certificate_item_id", "port", "import_date"]
    )
    
    # ==========================================================================
    # STEP 3: Create global settings table for default warning threshold
    # ==========================================================================
    
    op.create_table(
        "mida_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("setting_key", sa.String(100), nullable=False, unique=True),
        sa.Column("setting_value", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Insert default warning threshold setting
    op.execute(f"""
        INSERT INTO mida_settings (id, setting_key, setting_value, description)
        VALUES (
            1,
            'default_warning_threshold',
            '{DEFAULT_WARNING_THRESHOLD}',
            'Default quantity threshold below which items trigger warning status. Can be overridden per item.'
        )
    """)
    
    # ==========================================================================
    # STEP 4: Create views for different query patterns
    # ==========================================================================
    
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
    
    # View 2: Port Klang imports (all items imported through Port Klang)
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
    
    # View 3: KLIA imports (all items imported through KLIA)
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
    
    # View 5: Items with quantity warnings (approaching depletion)
    op.execute("""
        CREATE VIEW vw_items_with_warnings AS
        SELECT
            ci.id AS item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ci.approved_quantity,
            ci.remaining_quantity,
            ci.port_klang_qty,
            ci.remaining_port_klang,
            ci.klia_qty,
            ci.remaining_klia,
            ci.bukit_kayu_hitam_qty,
            ci.remaining_bukit_kayu_hitam,
            ci.warning_threshold,
            ci.quantity_status,
            CASE
                WHEN ci.quantity_status = 'overdrawn' THEN 1
                WHEN ci.quantity_status = 'depleted' THEN 2
                WHEN ci.quantity_status = 'warning' THEN 3
                ELSE 4
            END AS severity_order
        FROM mida_certificate_items ci
        JOIN mida_certificates c ON c.id = ci.certificate_id
        WHERE ci.quantity_status IN ('warning', 'depleted', 'overdrawn')
        ORDER BY severity_order, c.certificate_number, ci.line_no
    """)
    
    # View 6: Item remaining quantities summary (all items with current balances)
    op.execute("""
        CREATE VIEW vw_item_balances_summary AS
        SELECT
            ci.id AS item_id,
            ci.certificate_id,
            c.certificate_number,
            c.company_name,
            c.exemption_start_date,
            c.exemption_end_date,
            ci.line_no,
            ci.hs_code,
            ci.item_name,
            ci.uom,
            ci.approved_quantity,
            ci.remaining_quantity,
            CASE WHEN ci.approved_quantity > 0
                THEN ROUND((ci.remaining_quantity / ci.approved_quantity) * 100, 2)
                ELSE NULL
            END AS remaining_percentage,
            ci.port_klang_qty,
            ci.remaining_port_klang,
            ci.klia_qty,
            ci.remaining_klia,
            ci.bukit_kayu_hitam_qty,
            ci.remaining_bukit_kayu_hitam,
            ci.warning_threshold,
            ci.quantity_status,
            (
                SELECT COUNT(*)
                FROM mida_import_records ir
                WHERE ir.certificate_item_id = ci.id
            ) AS total_imports,
            (
                SELECT SUM(ir.quantity_imported)
                FROM mida_import_records ir
                WHERE ir.certificate_item_id = ci.id
            ) AS total_imported
        FROM mida_certificate_items ci
        JOIN mida_certificates c ON c.id = ci.certificate_id
        ORDER BY c.certificate_number, ci.line_no
    """)
    
    # ==========================================================================
    # STEP 5: Create PostgreSQL function to get item+port history
    # ==========================================================================
    
    op.execute("""
        CREATE OR REPLACE FUNCTION get_item_port_history(
            p_item_id UUID,
            p_port VARCHAR(30) DEFAULT NULL
        )
        RETURNS TABLE (
            import_record_id UUID,
            certificate_item_id UUID,
            certificate_number VARCHAR(100),
            item_name TEXT,
            hs_code VARCHAR(20),
            uom VARCHAR(50),
            import_date DATE,
            invoice_number VARCHAR(100),
            invoice_line INTEGER,
            port VARCHAR(30),
            quantity_imported NUMERIC(18,3),
            balance_before NUMERIC(18,3),
            balance_after NUMERIC(18,3),
            remarks TEXT,
            created_at TIMESTAMP
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                ir.id,
                ir.certificate_item_id,
                c.certificate_number,
                ci.item_name,
                ci.hs_code,
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
            WHERE ir.certificate_item_id = p_item_id
              AND (p_port IS NULL OR ir.port = p_port)
            ORDER BY ir.created_at;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # ==========================================================================
    # STEP 6: Create function to calculate quantity status
    # ==========================================================================
    
    op.execute("""
        CREATE OR REPLACE FUNCTION calculate_quantity_status(
            p_remaining NUMERIC,
            p_warning_threshold NUMERIC,
            p_default_threshold NUMERIC
        )
        RETURNS VARCHAR(20) AS $$
        DECLARE
            v_threshold NUMERIC;
        BEGIN
            -- Use item-specific threshold if set, otherwise use default
            v_threshold := COALESCE(p_warning_threshold, p_default_threshold);
            
            IF p_remaining IS NULL THEN
                RETURN 'normal';
            ELSIF p_remaining < 0 THEN
                RETURN 'overdrawn';
            ELSIF p_remaining = 0 THEN
                RETURN 'depleted';
            ELSIF p_remaining <= v_threshold THEN
                RETURN 'warning';
            ELSE
                RETURN 'normal';
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # ==========================================================================
    # STEP 7: Create trigger function to update item balances after import
    # ==========================================================================
    
    op.execute("""
        CREATE OR REPLACE FUNCTION update_item_balance_after_import()
        RETURNS TRIGGER AS $$
        DECLARE
            v_default_threshold NUMERIC;
            v_item_threshold NUMERIC;
            v_new_remaining NUMERIC;
            v_new_status VARCHAR(20);
        BEGIN
            -- Get default threshold from settings
            SELECT CAST(setting_value AS NUMERIC)
            INTO v_default_threshold
            FROM mida_settings
            WHERE setting_key = 'default_warning_threshold';
            
            v_default_threshold := COALESCE(v_default_threshold, 100);
            
            -- Update the appropriate remaining quantity based on port
            IF NEW.port = 'port_klang' THEN
                UPDATE mida_certificate_items
                SET remaining_port_klang = remaining_port_klang - NEW.quantity_imported,
                    remaining_quantity = COALESCE(remaining_quantity, 0) - NEW.quantity_imported,
                    updated_at = NOW()
                WHERE id = NEW.certificate_item_id;
                
            ELSIF NEW.port = 'klia' THEN
                UPDATE mida_certificate_items
                SET remaining_klia = remaining_klia - NEW.quantity_imported,
                    remaining_quantity = COALESCE(remaining_quantity, 0) - NEW.quantity_imported,
                    updated_at = NOW()
                WHERE id = NEW.certificate_item_id;
                
            ELSIF NEW.port = 'bukit_kayu_hitam' THEN
                UPDATE mida_certificate_items
                SET remaining_bukit_kayu_hitam = remaining_bukit_kayu_hitam - NEW.quantity_imported,
                    remaining_quantity = COALESCE(remaining_quantity, 0) - NEW.quantity_imported,
                    updated_at = NOW()
                WHERE id = NEW.certificate_item_id;
            END IF;
            
            -- Get updated remaining quantity and item threshold
            SELECT remaining_quantity, warning_threshold
            INTO v_new_remaining, v_item_threshold
            FROM mida_certificate_items
            WHERE id = NEW.certificate_item_id;
            
            -- Calculate and update status
            v_new_status := calculate_quantity_status(
                v_new_remaining,
                v_item_threshold,
                v_default_threshold
            );
            
            UPDATE mida_certificate_items
            SET quantity_status = v_new_status
            WHERE id = NEW.certificate_item_id;
            
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create the trigger
    op.execute("""
        CREATE TRIGGER trg_update_item_balance_after_import
        AFTER INSERT ON mida_import_records
        FOR EACH ROW
        EXECUTE FUNCTION update_item_balance_after_import();
    """)
    
    # ==========================================================================
    # STEP 8: Create trigger to initialize remaining quantities on item insert
    # ==========================================================================
    
    op.execute("""
        CREATE OR REPLACE FUNCTION initialize_remaining_quantities()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Initialize remaining quantities if not set
            IF NEW.remaining_quantity IS NULL THEN
                NEW.remaining_quantity := NEW.approved_quantity;
            END IF;
            IF NEW.remaining_port_klang IS NULL THEN
                NEW.remaining_port_klang := NEW.port_klang_qty;
            END IF;
            IF NEW.remaining_klia IS NULL THEN
                NEW.remaining_klia := NEW.klia_qty;
            END IF;
            IF NEW.remaining_bukit_kayu_hitam IS NULL THEN
                NEW.remaining_bukit_kayu_hitam := NEW.bukit_kayu_hitam_qty;
            END IF;
            
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER trg_initialize_remaining_quantities
        BEFORE INSERT ON mida_certificate_items
        FOR EACH ROW
        EXECUTE FUNCTION initialize_remaining_quantities();
    """)
    
    # ==========================================================================
    # STEP 9: Update the Table2 compatibility view to include remaining quantities
    # ==========================================================================
    
    op.execute("DROP VIEW IF EXISTS vw_table2_exemption_records")
    
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
            i.remaining_quantity,
            i.uom,
            i.port_klang_qty,
            i.remaining_port_klang,
            i.klia_qty,
            i.remaining_klia,
            i.bukit_kayu_hitam_qty,
            i.remaining_bukit_kayu_hitam,
            i.warning_threshold,
            i.quantity_status,
            c.created_at AS certificate_created_at,
            i.created_at AS item_created_at
        FROM mida_certificates c
        JOIN mida_certificate_items i ON i.certificate_id = c.id
        ORDER BY c.certificate_number, i.line_no
    """)


def downgrade() -> None:
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS trg_initialize_remaining_quantities ON mida_certificate_items")
    op.execute("DROP TRIGGER IF EXISTS trg_update_item_balance_after_import ON mida_import_records")
    
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS initialize_remaining_quantities()")
    op.execute("DROP FUNCTION IF EXISTS update_item_balance_after_import()")
    op.execute("DROP FUNCTION IF EXISTS calculate_quantity_status(NUMERIC, NUMERIC, NUMERIC)")
    op.execute("DROP FUNCTION IF EXISTS get_item_port_history(UUID, VARCHAR)")
    
    # Drop views
    op.execute("DROP VIEW IF EXISTS vw_table2_exemption_records")
    op.execute("DROP VIEW IF EXISTS vw_item_balances_summary")
    op.execute("DROP VIEW IF EXISTS vw_items_with_warnings")
    op.execute("DROP VIEW IF EXISTS vw_imports_bukit_kayu_hitam")
    op.execute("DROP VIEW IF EXISTS vw_imports_klia")
    op.execute("DROP VIEW IF EXISTS vw_imports_port_klang")
    op.execute("DROP VIEW IF EXISTS vw_import_history_by_item")
    
    # Drop settings table
    op.drop_table("mida_settings")
    
    # Drop import records table with indexes
    op.drop_index("ix_mida_import_records_item_port_date", table_name="mida_import_records")
    op.drop_index("ix_mida_import_records_invoice_number", table_name="mida_import_records")
    op.drop_index("ix_mida_import_records_import_date", table_name="mida_import_records")
    op.drop_index("ix_mida_import_records_port", table_name="mida_import_records")
    op.drop_index("ix_mida_import_records_certificate_item_id", table_name="mida_import_records")
    op.drop_table("mida_import_records")
    
    # Drop new columns from mida_certificate_items
    op.drop_index("ix_mida_certificate_items_quantity_status", table_name="mida_certificate_items")
    op.drop_constraint("ck_warning_threshold_non_negative", "mida_certificate_items", type_="check")
    op.drop_constraint("ck_quantity_status_valid", "mida_certificate_items", type_="check")
    op.drop_column("mida_certificate_items", "quantity_status")
    op.drop_column("mida_certificate_items", "warning_threshold")
    op.drop_column("mida_certificate_items", "remaining_bukit_kayu_hitam")
    op.drop_column("mida_certificate_items", "remaining_klia")
    op.drop_column("mida_certificate_items", "remaining_port_klang")
    op.drop_column("mida_certificate_items", "remaining_quantity")
    
    # Recreate original Table2 compatibility view
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
