"""
Repository layer for MIDA Import tracking.

Provides database operations for import records, balance queries,
and settings management.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.models.mida_certificate import (
    MidaCertificate,
    MidaCertificateItem,
    MidaImportRecord,
    ImportPort,
)


# =============================================================================
# Import Record Operations
# =============================================================================

def create_import_record(
    db: Session,
    certificate_item_id: UUID,
    import_date: date,
    invoice_number: str,
    quantity_imported: Decimal,
    port: str,
    balance_before: Decimal,
    balance_after: Decimal,
    declaration_form_reg_no: Optional[str] = None,
    invoice_line: Optional[int] = None,
    remarks: Optional[str] = None,
) -> MidaImportRecord:
    """
    Create a new import record.
    
    Note: The database trigger will automatically update the item's
    remaining quantities and status after this insert.
    """
    record = MidaImportRecord(
        certificate_item_id=certificate_item_id,
        import_date=import_date,
        declaration_form_reg_no=declaration_form_reg_no,
        invoice_number=invoice_number,
        invoice_line=invoice_line,
        quantity_imported=quantity_imported,
        port=port,
        balance_before=balance_before,
        balance_after=balance_after,
        remarks=remarks,
    )
    db.add(record)
    db.flush()
    db.refresh(record)
    return record


def get_import_record_by_id(
    db: Session,
    record_id: UUID,
) -> Optional[MidaImportRecord]:
    """Get an import record by its UUID."""
    return db.get(MidaImportRecord, record_id)


def update_import_record(
    db: Session,
    record_id: UUID,
    import_date: Optional[date] = None,
    declaration_form_reg_no: Optional[str] = None,
    invoice_number: Optional[str] = None,
    invoice_line: Optional[int] = None,
    quantity_imported: Optional[Decimal] = None,
    port: Optional[str] = None,
    remarks: Optional[str] = None,
) -> Optional[MidaImportRecord]:
    """
    Update an existing import record.
    
    Note: Changing quantity_imported will require recalculating balances
    for all subsequent imports on this item/port.
    """
    record = db.get(MidaImportRecord, record_id)
    if not record:
        return None
    
    if import_date is not None:
        record.import_date = import_date
    if declaration_form_reg_no is not None:
        record.declaration_form_reg_no = declaration_form_reg_no
    if invoice_number is not None:
        record.invoice_number = invoice_number
    if invoice_line is not None:
        record.invoice_line = invoice_line
    if remarks is not None:
        record.remarks = remarks
    if quantity_imported is not None:
        # Recalculate balance
        old_qty = record.quantity_imported
        qty_diff = quantity_imported - old_qty
        record.quantity_imported = quantity_imported
        record.balance_after = record.balance_after - qty_diff
    if port is not None:
        record.port = port
    
    db.flush()
    db.refresh(record)
    return record


def delete_import_record(
    db: Session,
    record_id: UUID,
) -> bool:
    """
    Delete an import record.
    
    Note: This will NOT automatically recalculate balances for the item.
    The caller should handle balance recalculation if needed.
    """
    record = db.get(MidaImportRecord, record_id)
    if not record:
        return False
    
    db.delete(record)
    db.flush()
    return True


def get_import_record_with_context(
    db: Session,
    record_id: UUID,
) -> Optional[MidaImportRecord]:
    """Get an import record with eagerly loaded item and certificate."""
    stmt = (
        select(MidaImportRecord)
        .options(
            joinedload(MidaImportRecord.certificate_item)
            .joinedload(MidaCertificateItem.certificate)
        )
        .where(MidaImportRecord.id == record_id)
    )
    return db.scalars(stmt).first()


def list_import_records(
    db: Session,
    certificate_item_id: Optional[UUID] = None,
    port: Optional[str] = None,
    certificate_id: Optional[UUID] = None,
    invoice_number: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[MidaImportRecord], int]:
    """
    List import records with optional filters and pagination.
    
    Returns a tuple of (records, total_count).
    """
    # Base query with joins for filtering
    stmt = (
        select(MidaImportRecord)
        .join(MidaCertificateItem)
        .options(
            joinedload(MidaImportRecord.certificate_item)
            .joinedload(MidaCertificateItem.certificate)
        )
    )
    
    # Apply filters
    if certificate_item_id:
        stmt = stmt.where(MidaImportRecord.certificate_item_id == certificate_item_id)
    if port:
        stmt = stmt.where(MidaImportRecord.port == port)
    if certificate_id:
        stmt = stmt.where(MidaCertificateItem.certificate_id == certificate_id)
    if invoice_number:
        stmt = stmt.where(
            MidaImportRecord.invoice_number.ilike(f"%{invoice_number}%")
        )
    if start_date:
        stmt = stmt.where(MidaImportRecord.import_date >= start_date)
    if end_date:
        stmt = stmt.where(MidaImportRecord.import_date <= end_date)
    
    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0
    
    # Apply ordering and pagination
    stmt = stmt.order_by(
        MidaImportRecord.import_date.desc(),
        MidaImportRecord.created_at.desc()
    )
    stmt = stmt.limit(limit).offset(offset)
    
    records = list(db.scalars(stmt).unique())
    return records, total


def get_last_import_for_item_port(
    db: Session,
    certificate_item_id: UUID,
    port: str,
) -> Optional[MidaImportRecord]:
    """Get the most recent import record for an item at a specific port."""
    stmt = (
        select(MidaImportRecord)
        .where(MidaImportRecord.certificate_item_id == certificate_item_id)
        .where(MidaImportRecord.port == port)
        .order_by(MidaImportRecord.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def get_import_history_for_item(
    db: Session,
    certificate_item_id: UUID,
    port: Optional[str] = None,
) -> list[MidaImportRecord]:
    """Get all import records for an item, optionally filtered by port."""
    stmt = (
        select(MidaImportRecord)
        .where(MidaImportRecord.certificate_item_id == certificate_item_id)
    )
    if port:
        stmt = stmt.where(MidaImportRecord.port == port)
    stmt = stmt.order_by(MidaImportRecord.created_at)
    return list(db.scalars(stmt))


# =============================================================================
# Certificate Item Operations
# =============================================================================

def get_item_by_id(
    db: Session,
    item_id: UUID,
) -> Optional[MidaCertificateItem]:
    """Get a certificate item by its UUID."""
    return db.get(MidaCertificateItem, item_id)


def get_item_with_certificate(
    db: Session,
    item_id: UUID,
) -> Optional[MidaCertificateItem]:
    """Get a certificate item with its parent certificate loaded."""
    stmt = (
        select(MidaCertificateItem)
        .options(joinedload(MidaCertificateItem.certificate))
        .where(MidaCertificateItem.id == item_id)
    )
    return db.scalars(stmt).first()


def get_current_balance_for_port(
    db: Session,
    item_id: UUID,
    port: str,
) -> Optional[Decimal]:
    """Get the current remaining balance for an item at a specific port."""
    item = db.get(MidaCertificateItem, item_id)
    if not item:
        return None
    
    if port == ImportPort.PORT_KLANG.value:
        return item.remaining_port_klang
    elif port == ImportPort.KLIA.value:
        return item.remaining_klia
    elif port == ImportPort.BUKIT_KAYU_HITAM.value:
        return item.remaining_bukit_kayu_hitam
    return None


def update_item_warning_threshold(
    db: Session,
    item_id: UUID,
    warning_threshold: Optional[Decimal],
) -> Optional[MidaCertificateItem]:
    """Update an item's warning threshold."""
    item = db.get(MidaCertificateItem, item_id)
    if not item:
        return None
    
    item.warning_threshold = warning_threshold
    db.flush()
    
    # Recalculate status based on new threshold
    default_threshold = get_default_warning_threshold(db)
    threshold = warning_threshold if warning_threshold is not None else default_threshold
    
    if item.remaining_quantity is not None:
        if item.remaining_quantity < 0:
            item.quantity_status = "overdrawn"
        elif item.remaining_quantity == 0:
            item.quantity_status = "depleted"
        elif item.remaining_quantity <= threshold:
            item.quantity_status = "warning"
        else:
            item.quantity_status = "normal"
    
    db.flush()
    db.refresh(item)
    return item


def list_items_with_balances(
    db: Session,
    certificate_id: Optional[UUID] = None,
    quantity_status: Optional[str] = None,
    hs_code: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list[MidaCertificateItem], int]:
    """List certificate items with their balance information."""
    stmt = (
        select(MidaCertificateItem)
        .options(joinedload(MidaCertificateItem.certificate))
    )
    
    if certificate_id:
        stmt = stmt.where(MidaCertificateItem.certificate_id == certificate_id)
    if quantity_status:
        stmt = stmt.where(MidaCertificateItem.quantity_status == quantity_status)
    if hs_code:
        stmt = stmt.where(MidaCertificateItem.hs_code.ilike(f"%{hs_code}%"))
    
    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0
    
    # Apply ordering and pagination
    stmt = stmt.order_by(
        MidaCertificateItem.certificate_id,
        MidaCertificateItem.line_no
    )
    stmt = stmt.limit(limit).offset(offset)
    
    items = list(db.scalars(stmt).unique())
    return items, total


def list_items_with_warnings(
    db: Session,
    certificate_id: Optional[UUID] = None,
) -> list[MidaCertificateItem]:
    """List all items with warning, depleted, or overdrawn status."""
    stmt = (
        select(MidaCertificateItem)
        .options(joinedload(MidaCertificateItem.certificate))
        .where(MidaCertificateItem.quantity_status.in_(["warning", "depleted", "overdrawn"]))
    )
    
    if certificate_id:
        stmt = stmt.where(MidaCertificateItem.certificate_id == certificate_id)
    
    # Order by severity (overdrawn > depleted > warning) then by certificate/line
    stmt = stmt.order_by(
        # Custom ordering based on status severity
        func.case(
            (MidaCertificateItem.quantity_status == "overdrawn", 1),
            (MidaCertificateItem.quantity_status == "depleted", 2),
            (MidaCertificateItem.quantity_status == "warning", 3),
            else_=4
        ),
        MidaCertificateItem.certificate_id,
        MidaCertificateItem.line_no
    )
    
    return list(db.scalars(stmt).unique())


# =============================================================================
# Settings Operations
# =============================================================================

def get_setting(db: Session, setting_key: str) -> Optional[str]:
    """Get a setting value by key."""
    result = db.execute(
        text("SELECT setting_value FROM mida_settings WHERE setting_key = :key"),
        {"key": setting_key}
    )
    row = result.fetchone()
    return row[0] if row else None


def update_setting(db: Session, setting_key: str, setting_value: str) -> bool:
    """Update a setting value."""
    result = db.execute(
        text("""
            UPDATE mida_settings
            SET setting_value = :value, updated_at = NOW()
            WHERE setting_key = :key
        """),
        {"key": setting_key, "value": setting_value}
    )
    db.flush()
    return result.rowcount > 0


def get_default_warning_threshold(db: Session) -> Decimal:
    """Get the default warning threshold from settings."""
    value = get_setting(db, "default_warning_threshold")
    return Decimal(value) if value else Decimal("100")


def update_default_warning_threshold(db: Session, threshold: Decimal) -> bool:
    """Update the default warning threshold."""
    return update_setting(db, "default_warning_threshold", str(threshold))


# =============================================================================
# Port Summary Operations
# =============================================================================

def get_port_import_summary(
    db: Session,
    port: str,
    limit_recent: int = 10,
) -> dict:
    """Get summary statistics for imports at a specific port."""
    # Get total records and quantity
    stats = db.execute(
        text("""
            SELECT
                COUNT(*) as total_records,
                COALESCE(SUM(quantity_imported), 0) as total_quantity,
                COUNT(DISTINCT certificate_item_id) as unique_items
            FROM mida_import_records
            WHERE port = :port
        """),
        {"port": port}
    ).fetchone()
    
    # Get unique certificates count
    cert_count = db.execute(
        text("""
            SELECT COUNT(DISTINCT ci.certificate_id)
            FROM mida_import_records ir
            JOIN mida_certificate_items ci ON ci.id = ir.certificate_item_id
            WHERE ir.port = :port
        """),
        {"port": port}
    ).scalar() or 0
    
    # Get recent imports
    stmt = (
        select(MidaImportRecord)
        .options(
            joinedload(MidaImportRecord.certificate_item)
            .joinedload(MidaCertificateItem.certificate)
        )
        .where(MidaImportRecord.port == port)
        .order_by(MidaImportRecord.created_at.desc())
        .limit(limit_recent)
    )
    recent = list(db.scalars(stmt).unique())
    
    return {
        "total_records": stats[0] if stats else 0,
        "total_quantity": stats[1] if stats else Decimal("0"),
        "unique_items": stats[2] if stats else 0,
        "unique_certificates": cert_count,
        "recent_imports": recent,
    }


def get_all_ports_summary(db: Session) -> dict:
    """Get summary for all ports."""
    return {
        "port_klang": get_port_import_summary(db, ImportPort.PORT_KLANG.value),
        "klia": get_port_import_summary(db, ImportPort.KLIA.value),
        "bukit_kayu_hitam": get_port_import_summary(db, ImportPort.BUKIT_KAYU_HITAM.value),
    }


# =============================================================================
# View Query Operations (using the SQL views)
# =============================================================================

def query_item_import_history(
    db: Session,
    item_id: UUID,
    port: Optional[str] = None,
) -> list[dict]:
    """Query import history using the database function."""
    if port:
        result = db.execute(
            text("SELECT * FROM get_item_port_history(:item_id, :port)"),
            {"item_id": str(item_id), "port": port}
        )
    else:
        result = db.execute(
            text("SELECT * FROM get_item_port_history(:item_id, NULL)"),
            {"item_id": str(item_id)}
        )
    
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


def query_items_with_warnings_view(db: Session) -> list[dict]:
    """Query items with warnings from the database view."""
    result = db.execute(text("SELECT * FROM vw_items_with_warnings"))
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


def query_item_balances_summary(
    db: Session,
    certificate_id: Optional[UUID] = None,
) -> list[dict]:
    """Query item balances summary from the database view."""
    if certificate_id:
        result = db.execute(
            text("SELECT * FROM vw_item_balances_summary WHERE certificate_id = :cert_id"),
            {"cert_id": str(certificate_id)}
        )
    else:
        result = db.execute(text("SELECT * FROM vw_item_balances_summary"))
    
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]
