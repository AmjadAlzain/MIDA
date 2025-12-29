"""
Service layer for MIDA Import tracking.

Provides business logic for recording imports, checking warnings,
calculating balances, and managing settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.mida_certificate import (
    MidaCertificateItem,
    MidaImportRecord,
    ImportPort,
    QuantityStatus,
)
from app.repositories import mida_import_repo
from app.schemas.mida_import import (
    ImportRecordCreate,
    ImportPreview,
    ImportPreviewResponse,
    ItemBalanceRead,
    ItemWarning,
    WarningStatusResponse,
    PortSummary,
    PortSummaryResponse,
    ImportRecordWithContext,
)


# =============================================================================
# Custom Exceptions
# =============================================================================

class ImportError(Exception):
    """Base exception for import operations."""
    pass


class ItemNotFoundError(ImportError):
    """Raised when a certificate item is not found."""
    pass


class InsufficientBalanceError(ImportError):
    """Raised when import would result in negative balance (if blocking is enabled)."""
    pass


class InvalidPortError(ImportError):
    """Raised when trying to import to a port with no allocated quantity."""
    pass


class CertificateNotConfirmedError(ImportError):
    """Raised when trying to import against a non-confirmed certificate."""
    pass


# =============================================================================
# Import Result Data Classes
# =============================================================================

@dataclass
class ImportResult:
    """Result of an import operation."""
    record: MidaImportRecord
    item: MidaCertificateItem
    previous_status: str
    new_status: str
    triggered_warning: bool
    triggered_depletion: bool
    triggered_overdraw: bool
    warning_message: Optional[str] = None


# =============================================================================
# Import Operations
# =============================================================================

def preview_import(
    db: Session,
    import_data: ImportRecordCreate,
) -> ImportPreview:
    """
    Preview what will happen when an import is recorded.
    
    Returns a preview with balance changes and status transitions.
    """
    # Get the item with certificate
    item = mida_import_repo.get_item_with_certificate(db, import_data.certificate_item_id)
    if not item:
        raise ItemNotFoundError(f"Item with id '{import_data.certificate_item_id}' not found")
    
    # Get current balance for the port
    port = import_data.port.value
    current_balance = mida_import_repo.get_current_balance_for_port(
        db, import_data.certificate_item_id, port
    )
    
    if current_balance is None:
        # Check if port has any allocated quantity
        if port == ImportPort.PORT_KLANG.value and item.port_klang_qty is None:
            raise InvalidPortError(f"Item has no allocated quantity for Port Klang")
        elif port == ImportPort.KLIA.value and item.klia_qty is None:
            raise InvalidPortError(f"Item has no allocated quantity for KLIA")
        elif port == ImportPort.BUKIT_KAYU_HITAM.value and item.bukit_kayu_hitam_qty is None:
            raise InvalidPortError(f"Item has no allocated quantity for Bukit Kayu Hitam")
        current_balance = Decimal("0")
    
    # Calculate new balance
    balance_after = current_balance - import_data.quantity_imported
    
    # Determine new status
    default_threshold = mida_import_repo.get_default_warning_threshold(db)
    threshold = item.warning_threshold if item.warning_threshold is not None else default_threshold
    
    if balance_after < 0:
        new_status = QuantityStatus.OVERDRAWN.value
    elif balance_after == 0:
        new_status = QuantityStatus.DEPLETED.value
    elif balance_after <= threshold:
        new_status = QuantityStatus.WARNING.value
    else:
        new_status = QuantityStatus.NORMAL.value
    
    # Determine warning flags
    will_trigger_warning = (
        item.quantity_status == QuantityStatus.NORMAL.value and
        new_status == QuantityStatus.WARNING.value
    )
    will_deplete = (
        item.quantity_status != QuantityStatus.DEPLETED.value and
        new_status == QuantityStatus.DEPLETED.value
    )
    will_overdraw = (
        item.quantity_status != QuantityStatus.OVERDRAWN.value and
        new_status == QuantityStatus.OVERDRAWN.value
    )
    
    # Build warning message
    warning_message = None
    if will_overdraw:
        warning_message = f"WARNING: This import will overdraw the balance by {abs(balance_after)} {item.uom}"
    elif will_deplete:
        warning_message = f"NOTICE: This import will deplete the remaining balance"
    elif will_trigger_warning:
        warning_message = f"NOTICE: Balance will fall below warning threshold ({threshold} {item.uom})"
    
    return ImportPreview(
        certificate_item_id=item.id,
        certificate_number=item.certificate.certificate_number,
        item_name=item.item_name,
        hs_code=item.hs_code,
        port=port,
        quantity_to_import=import_data.quantity_imported,
        current_balance=current_balance,
        balance_after_import=balance_after,
        new_status=new_status,
        will_trigger_warning=will_trigger_warning,
        will_deplete=will_deplete,
        will_overdraw=will_overdraw,
        warning_message=warning_message,
    )


def preview_bulk_imports(
    db: Session,
    imports: list[ImportRecordCreate],
) -> ImportPreviewResponse:
    """Preview multiple imports at once."""
    previews = []
    has_warnings = False
    has_depletions = False
    has_overdrawns = False
    
    for import_data in imports:
        try:
            preview = preview_import(db, import_data)
            previews.append(preview)
            
            if preview.will_trigger_warning:
                has_warnings = True
            if preview.will_deplete:
                has_depletions = True
            if preview.will_overdraw:
                has_overdrawns = True
        except ImportError as e:
            # Include error as warning message in preview
            previews.append(ImportPreview(
                certificate_item_id=import_data.certificate_item_id,
                certificate_number="ERROR",
                item_name=str(e),
                hs_code="",
                port=import_data.port.value,
                quantity_to_import=import_data.quantity_imported,
                current_balance=Decimal("0"),
                balance_after_import=Decimal("0"),
                new_status="error",
                will_trigger_warning=False,
                will_deplete=False,
                will_overdraw=True,
                warning_message=str(e),
            ))
            has_overdrawns = True
    
    return ImportPreviewResponse(
        previews=previews,
        has_warnings=has_warnings,
        has_depletions=has_depletions,
        has_overdrawns=has_overdrawns,
        total_items=len(previews),
    )


def record_import(
    db: Session,
    import_data: ImportRecordCreate,
    allow_overdraw: bool = True,
) -> ImportResult:
    """
    Record an import transaction.
    
    This creates an import record and the database trigger automatically
    updates the item's remaining quantities and status.
    
    Args:
        db: Database session
        import_data: Import record data
        allow_overdraw: If False, raises error when import would cause negative balance
    
    Returns:
        ImportResult with the created record and status information
    """
    # Get the item with certificate
    item = mida_import_repo.get_item_with_certificate(db, import_data.certificate_item_id)
    if not item:
        raise ItemNotFoundError(f"Item with id '{import_data.certificate_item_id}' not found")
    
    # Check if certificate is confirmed (optional enforcement)
    # Uncomment if imports should only be allowed for confirmed certificates
    # if item.certificate.status != "confirmed":
    #     raise CertificateNotConfirmedError(
    #         f"Certificate '{item.certificate.certificate_number}' is not confirmed"
    #     )
    
    # Get current balance for the port
    port = import_data.port.value
    current_balance = mida_import_repo.get_current_balance_for_port(
        db, import_data.certificate_item_id, port
    )
    
    if current_balance is None:
        # Check if port has any allocated quantity
        allocated = None
        if port == ImportPort.PORT_KLANG.value:
            allocated = item.port_klang_qty
        elif port == ImportPort.KLIA.value:
            allocated = item.klia_qty
        elif port == ImportPort.BUKIT_KAYU_HITAM.value:
            allocated = item.bukit_kayu_hitam_qty
        
        if allocated is None:
            raise InvalidPortError(
                f"Item '{item.item_name}' has no allocated quantity for port '{port}'"
            )
        current_balance = allocated
    
    # Calculate new balance
    balance_after = current_balance - import_data.quantity_imported
    
    # Check if overdraw is allowed
    if not allow_overdraw and balance_after < 0:
        raise InsufficientBalanceError(
            f"Insufficient balance. Current: {current_balance}, "
            f"Requested: {import_data.quantity_imported}, "
            f"Would result in: {balance_after}"
        )
    
    # Store previous status for comparison
    previous_status = item.quantity_status
    
    # Create the import record (trigger will update item balances)
    record = mida_import_repo.create_import_record(
        db=db,
        certificate_item_id=import_data.certificate_item_id,
        import_date=import_data.import_date,
        invoice_number=import_data.invoice_number,
        invoice_line=import_data.invoice_line,
        quantity_imported=import_data.quantity_imported,
        port=port,
        balance_before=current_balance,
        balance_after=balance_after,
        remarks=import_data.remarks,
    )
    
    # Refresh item to get updated status from trigger
    db.refresh(item)
    new_status = item.quantity_status
    
    # Determine what was triggered
    triggered_warning = (
        previous_status == QuantityStatus.NORMAL.value and
        new_status == QuantityStatus.WARNING.value
    )
    triggered_depletion = (
        previous_status != QuantityStatus.DEPLETED.value and
        new_status == QuantityStatus.DEPLETED.value
    )
    triggered_overdraw = (
        previous_status != QuantityStatus.OVERDRAWN.value and
        new_status == QuantityStatus.OVERDRAWN.value
    )
    
    # Build warning message
    warning_message = None
    if triggered_overdraw:
        warning_message = f"Item is now OVERDRAWN by {abs(balance_after)} {item.uom}"
    elif triggered_depletion:
        warning_message = f"Item is now DEPLETED (balance = 0)"
    elif triggered_warning:
        warning_message = f"Item is now below warning threshold"
    
    db.commit()
    
    return ImportResult(
        record=record,
        item=item,
        previous_status=previous_status,
        new_status=new_status,
        triggered_warning=triggered_warning,
        triggered_depletion=triggered_depletion,
        triggered_overdraw=triggered_overdraw,
        warning_message=warning_message,
    )


def record_bulk_imports(
    db: Session,
    imports: list[ImportRecordCreate],
    allow_overdraw: bool = True,
    stop_on_error: bool = False,
) -> list[ImportResult]:
    """
    Record multiple imports in a single transaction.
    
    Args:
        db: Database session
        imports: List of import records to create
        allow_overdraw: If False, raises error when import would cause negative balance
        stop_on_error: If True, stops processing on first error; otherwise collects all results
    
    Returns:
        List of ImportResult for each import
    """
    results = []
    
    for import_data in imports:
        try:
            result = record_import(db, import_data, allow_overdraw)
            results.append(result)
        except ImportError as e:
            if stop_on_error:
                db.rollback()
                raise
            # Create a failed result - would need to handle this in response
            raise
    
    return results


# =============================================================================
# Balance Queries
# =============================================================================

def get_item_balance(
    db: Session,
    item_id: UUID,
) -> Optional[ItemBalanceRead]:
    """Get current balance information for an item."""
    item = mida_import_repo.get_item_with_certificate(db, item_id)
    if not item:
        return None
    
    # Get import statistics
    imports = mida_import_repo.get_import_history_for_item(db, item_id)
    total_imports = len(imports)
    total_imported = sum(i.quantity_imported for i in imports) if imports else Decimal("0")
    
    # Calculate remaining percentage
    remaining_percentage = None
    if item.approved_quantity and item.approved_quantity > 0 and item.remaining_quantity is not None:
        remaining_percentage = (item.remaining_quantity / item.approved_quantity) * 100
    
    return ItemBalanceRead(
        item_id=item.id,
        certificate_id=item.certificate_id,
        certificate_number=item.certificate.certificate_number,
        company_name=item.certificate.company_name,
        line_no=item.line_no,
        hs_code=item.hs_code,
        item_name=item.item_name,
        uom=item.uom,
        approved_quantity=item.approved_quantity,
        port_klang_qty=item.port_klang_qty,
        klia_qty=item.klia_qty,
        bukit_kayu_hitam_qty=item.bukit_kayu_hitam_qty,
        remaining_quantity=item.remaining_quantity,
        remaining_port_klang=item.remaining_port_klang,
        remaining_klia=item.remaining_klia,
        remaining_bukit_kayu_hitam=item.remaining_bukit_kayu_hitam,
        remaining_percentage=remaining_percentage,
        total_imports=total_imports,
        total_imported=total_imported,
        warning_threshold=item.warning_threshold,
        quantity_status=item.quantity_status,
    )


def list_item_balances(
    db: Session,
    certificate_id: Optional[UUID] = None,
    quantity_status: Optional[str] = None,
    hs_code: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ItemBalanceRead], int]:
    """List item balances with optional filters."""
    items, total = mida_import_repo.list_items_with_balances(
        db,
        certificate_id=certificate_id,
        quantity_status=quantity_status,
        hs_code=hs_code,
        limit=limit,
        offset=offset,
    )
    
    balances = []
    for item in items:
        balance = get_item_balance(db, item.id)
        if balance:
            balances.append(balance)
    
    return balances, total


# =============================================================================
# Warning Queries
# =============================================================================

def get_items_with_warnings(
    db: Session,
    certificate_id: Optional[UUID] = None,
) -> WarningStatusResponse:
    """Get all items with warning, depleted, or overdrawn status."""
    items = mida_import_repo.list_items_with_warnings(db, certificate_id)
    
    warnings = []
    total_warnings = 0
    total_depleted = 0
    total_overdrawn = 0
    
    for item in items:
        # Calculate severity order
        if item.quantity_status == QuantityStatus.OVERDRAWN.value:
            severity_order = 1
            total_overdrawn += 1
        elif item.quantity_status == QuantityStatus.DEPLETED.value:
            severity_order = 2
            total_depleted += 1
        else:
            severity_order = 3
            total_warnings += 1
        
        warnings.append(ItemWarning(
            item_id=item.id,
            certificate_id=item.certificate_id,
            certificate_number=item.certificate.certificate_number,
            company_name=item.certificate.company_name,
            line_no=item.line_no,
            hs_code=item.hs_code,
            item_name=item.item_name,
            uom=item.uom,
            approved_quantity=item.approved_quantity,
            remaining_quantity=item.remaining_quantity,
            remaining_port_klang=item.remaining_port_klang,
            remaining_klia=item.remaining_klia,
            remaining_bukit_kayu_hitam=item.remaining_bukit_kayu_hitam,
            warning_threshold=item.warning_threshold,
            quantity_status=item.quantity_status,
            severity_order=severity_order,
        ))
    
    return WarningStatusResponse(
        items=warnings,
        total_warnings=total_warnings,
        total_depleted=total_depleted,
        total_overdrawn=total_overdrawn,
    )


# =============================================================================
# Settings Operations
# =============================================================================

def get_default_threshold(db: Session) -> Decimal:
    """Get the default warning threshold."""
    return mida_import_repo.get_default_warning_threshold(db)


def update_default_threshold(db: Session, threshold: Decimal) -> bool:
    """Update the default warning threshold."""
    success = mida_import_repo.update_default_warning_threshold(db, threshold)
    if success:
        db.commit()
    return success


def update_item_threshold(
    db: Session,
    item_id: UUID,
    threshold: Optional[Decimal],
) -> Optional[MidaCertificateItem]:
    """Update an item's warning threshold."""
    item = mida_import_repo.update_item_warning_threshold(db, item_id, threshold)
    if item:
        db.commit()
    return item


# =============================================================================
# Port Summary Operations
# =============================================================================

def get_port_summary(db: Session, port: str) -> PortSummary:
    """Get summary for a specific port."""
    summary = mida_import_repo.get_port_import_summary(db, port)
    
    recent_imports = []
    for record in summary["recent_imports"]:
        recent_imports.append(ImportRecordWithContext(
            id=record.id,
            certificate_item_id=record.certificate_item_id,
            import_date=record.import_date,
            invoice_number=record.invoice_number,
            invoice_line=record.invoice_line,
            quantity_imported=record.quantity_imported,
            port=record.port,
            balance_before=record.balance_before,
            balance_after=record.balance_after,
            remarks=record.remarks,
            created_at=record.created_at,
            updated_at=record.updated_at,
            certificate_number=record.certificate_item.certificate.certificate_number,
            company_name=record.certificate_item.certificate.company_name,
            item_hs_code=record.certificate_item.hs_code,
            item_name=record.certificate_item.item_name,
            item_uom=record.certificate_item.uom,
        ))
    
    return PortSummary(
        port=port,
        total_records=summary["total_records"],
        total_quantity_imported=summary["total_quantity"],
        unique_items=summary["unique_items"],
        unique_certificates=summary["unique_certificates"],
        recent_imports=recent_imports,
    )


def get_all_ports_summary(db: Session) -> PortSummaryResponse:
    """Get summary for all ports."""
    port_klang = get_port_summary(db, ImportPort.PORT_KLANG.value)
    klia = get_port_summary(db, ImportPort.KLIA.value)
    bukit_kayu_hitam = get_port_summary(db, ImportPort.BUKIT_KAYU_HITAM.value)
    
    overall_total = (
        port_klang.total_records +
        klia.total_records +
        bukit_kayu_hitam.total_records
    )
    
    return PortSummaryResponse(
        port_klang=port_klang,
        klia=klia,
        bukit_kayu_hitam=bukit_kayu_hitam,
        overall_total_imports=overall_total,
    )


# =============================================================================
# Import History Operations
# =============================================================================

def get_import_history(
    db: Session,
    item_id: Optional[UUID] = None,
    port: Optional[str] = None,
    certificate_id: Optional[UUID] = None,
    invoice_number: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ImportRecordWithContext], int]:
    """Get import history with optional filters."""
    records, total = mida_import_repo.list_import_records(
        db,
        certificate_item_id=item_id,
        port=port,
        certificate_id=certificate_id,
        invoice_number=invoice_number,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    
    history = []
    for record in records:
        history.append(ImportRecordWithContext(
            id=record.id,
            certificate_item_id=record.certificate_item_id,
            import_date=record.import_date,
            invoice_number=record.invoice_number,
            invoice_line=record.invoice_line,
            quantity_imported=record.quantity_imported,
            port=record.port,
            balance_before=record.balance_before,
            balance_after=record.balance_after,
            remarks=record.remarks,
            created_at=record.created_at,
            updated_at=record.updated_at,
            certificate_number=record.certificate_item.certificate.certificate_number,
            company_name=record.certificate_item.certificate.company_name,
            item_hs_code=record.certificate_item.hs_code,
            item_name=record.certificate_item.item_name,
            item_uom=record.certificate_item.uom,
        ))
    
    return history, total
