"""
MIDA Import Tracking Router.

Provides REST API endpoints for:
- Recording imports against MIDA certificate items
- Querying item balances and remaining quantities
- Managing warning thresholds
- Viewing import history by item, port, or certificate
- Getting port-specific summaries
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.mida_import import (
    ImportRecordCreate,
    ImportRecordBulkCreate,
    ImportRecordRead,
    ImportRecordListResponse,
    ImportPreviewResponse,
    ImportHistoryResponse,
    ItemBalanceRead,
    ItemBalanceUpdate,
    ItemBalanceListResponse,
    WarningStatusResponse,
    PortSummaryResponse,
    DefaultThresholdUpdate,
    ImportPort,
)
from app.services.mida_import_service import (
    preview_import,
    preview_bulk_imports,
    record_import,
    record_bulk_imports,
    get_item_balance,
    list_item_balances,
    get_items_with_warnings,
    get_default_threshold,
    update_default_threshold,
    update_item_threshold,
    get_port_summary,
    get_all_ports_summary,
    get_import_history,
    ItemNotFoundError,
    InsufficientBalanceError,
    InvalidPortError,
    CertificateNotConfirmedError,
)

router = APIRouter()


# =============================================================================
# Import Recording Endpoints
# =============================================================================

@router.post(
    "/preview",
    response_model=ImportPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview import(s) before recording",
    description="""
    Preview what will happen when import(s) are recorded.
    
    Returns balance changes, status transitions, and any warnings
    without actually modifying the database. Use this to validate
    imports before committing them.
    """,
)
async def preview_imports(
    payload: ImportRecordBulkCreate,
    db: Session = Depends(get_db),
):
    """Preview one or more imports without recording them."""
    return preview_bulk_imports(db, payload.records)


@router.post(
    "",
    response_model=ImportRecordRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Import recorded successfully"},
        400: {"description": "Invalid import data"},
        404: {"description": "Certificate item not found"},
        409: {"description": "Insufficient balance (if overdraw disabled)"},
    },
    summary="Record a single import",
    description="""
    Record an import transaction against a certificate item.
    
    This will:
    1. Create an import record with balance tracking
    2. Update the item's remaining quantities (via database trigger)
    3. Update the item's quantity status if thresholds are crossed
    
    By default, overdrawing (negative balance) is allowed but flagged.
    """,
)
async def create_import(
    payload: ImportRecordCreate,
    allow_overdraw: bool = Query(
        True, description="Allow import even if it results in negative balance"
    ),
    db: Session = Depends(get_db),
):
    """Record a single import."""
    try:
        result = record_import(db, payload, allow_overdraw)
        return result.record
    except ItemNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidPortError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except InsufficientBalanceError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except CertificateNotConfirmedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post(
    "/bulk",
    response_model=list[ImportRecordRead],
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Imports recorded successfully"},
        400: {"description": "Invalid import data"},
        404: {"description": "Certificate item not found"},
        409: {"description": "Insufficient balance or other conflict"},
    },
    summary="Record multiple imports in one transaction",
    description="""
    Record multiple imports in a single database transaction.
    
    All imports succeed or all fail together (atomic operation).
    """,
)
async def create_bulk_imports(
    payload: ImportRecordBulkCreate,
    allow_overdraw: bool = Query(
        True, description="Allow imports even if they result in negative balance"
    ),
    db: Session = Depends(get_db),
):
    """Record multiple imports in one transaction."""
    try:
        results = record_bulk_imports(db, payload.records, allow_overdraw)
        return [r.record for r in results]
    except ItemNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidPortError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except InsufficientBalanceError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


# =============================================================================
# Import History Endpoints
# =============================================================================

@router.get(
    "/history",
    response_model=ImportHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get import history with filters",
    description="""
    Query import history with optional filters:
    - By specific item
    - By port
    - By certificate
    - By invoice number
    - By date range
    
    Results are ordered by import date (newest first).
    """,
)
async def get_history(
    item_id: Optional[UUID] = Query(None, description="Filter by item ID"),
    port: Optional[ImportPort] = Query(None, description="Filter by port"),
    certificate_id: Optional[UUID] = Query(None, description="Filter by certificate ID"),
    invoice_number: Optional[str] = Query(None, description="Filter by invoice number"),
    start_date: Optional[date] = Query(None, description="Filter from this date"),
    end_date: Optional[date] = Query(None, description="Filter until this date"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results to skip"),
    db: Session = Depends(get_db),
):
    """Get import history with filters."""
    port_value = port.value if port else None
    imports, total = get_import_history(
        db,
        item_id=item_id,
        port=port_value,
        certificate_id=certificate_id,
        invoice_number=invoice_number,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return ImportHistoryResponse(
        imports=imports,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/history/item/{item_id}",
    response_model=ImportHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get import history for a specific item",
    description="Get all imports for a specific certificate item across all ports.",
)
async def get_item_history(
    item_id: UUID,
    port: Optional[ImportPort] = Query(None, description="Filter by port"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get import history for a specific item."""
    port_value = port.value if port else None
    imports, total = get_import_history(
        db,
        item_id=item_id,
        port=port_value,
        limit=limit,
        offset=offset,
    )
    return ImportHistoryResponse(
        imports=imports,
        total=total,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Balance Endpoints
# =============================================================================

@router.get(
    "/balances",
    response_model=ItemBalanceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List item balances",
    description="""
    List all items with their current balance information.
    
    Includes:
    - Approved vs remaining quantities (total and per-port)
    - Warning threshold and status
    - Import statistics
    """,
)
async def list_balances(
    certificate_id: Optional[UUID] = Query(None, description="Filter by certificate"),
    quantity_status: Optional[str] = Query(
        None, description="Filter by status (normal, warning, depleted, overdrawn)"
    ),
    hs_code: Optional[str] = Query(None, description="Filter by HS code"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List item balances with filters."""
    items, total = list_item_balances(
        db,
        certificate_id=certificate_id,
        quantity_status=quantity_status,
        hs_code=hs_code,
        limit=limit,
        offset=offset,
    )
    return ItemBalanceListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/balances/{item_id}",
    response_model=ItemBalanceRead,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Item balance retrieved"},
        404: {"description": "Item not found"},
    },
    summary="Get balance for a specific item",
    description="Get detailed balance information for a single item.",
)
async def get_balance(
    item_id: UUID,
    db: Session = Depends(get_db),
):
    """Get balance for a specific item."""
    balance = get_item_balance(db, item_id)
    if not balance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id '{item_id}' not found",
        )
    return balance


@router.put(
    "/balances/{item_id}/threshold",
    response_model=ItemBalanceRead,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Threshold updated"},
        404: {"description": "Item not found"},
    },
    summary="Update item warning threshold",
    description="""
    Update the warning threshold for a specific item.
    
    Set to null to use the global default threshold.
    The item's quantity status will be recalculated based on the new threshold.
    """,
)
async def update_threshold(
    item_id: UUID,
    payload: ItemBalanceUpdate,
    db: Session = Depends(get_db),
):
    """Update an item's warning threshold."""
    item = update_item_threshold(db, item_id, payload.warning_threshold)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id '{item_id}' not found",
        )
    
    # Return updated balance
    balance = get_item_balance(db, item_id)
    return balance


# =============================================================================
# Warning Endpoints
# =============================================================================

@router.get(
    "/warnings",
    response_model=WarningStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all items with warnings",
    description="""
    Get all items that have warning, depleted, or overdrawn status.
    
    Results are ordered by severity:
    1. Overdrawn (negative balance)
    2. Depleted (zero balance)
    3. Warning (below threshold)
    """,
)
async def get_warnings(
    certificate_id: Optional[UUID] = Query(None, description="Filter by certificate"),
    db: Session = Depends(get_db),
):
    """Get all items with warnings."""
    return get_items_with_warnings(db, certificate_id)


# =============================================================================
# Port Summary Endpoints
# =============================================================================

@router.get(
    "/ports/summary",
    response_model=PortSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get summary for all ports",
    description="""
    Get import statistics for all three ports:
    - Port Klang
    - KLIA
    - Bukit Kayu Hitam
    
    Each port summary includes total records, quantities, and recent imports.
    """,
)
async def get_ports_summary(
    db: Session = Depends(get_db),
):
    """Get summary for all ports."""
    return get_all_ports_summary(db)


@router.get(
    "/ports/{port}/history",
    response_model=ImportHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get import history for a specific port",
    description="Get all imports that occurred at a specific port.",
)
async def get_port_history(
    port: ImportPort,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get import history for a specific port."""
    imports, total = get_import_history(
        db,
        port=port.value,
        limit=limit,
        offset=offset,
    )
    return ImportHistoryResponse(
        imports=imports,
        total=total,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Settings Endpoints
# =============================================================================

@router.get(
    "/settings/threshold",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get default warning threshold",
    description="Get the global default warning threshold used for items without custom thresholds.",
)
async def get_threshold_setting(
    db: Session = Depends(get_db),
):
    """Get the default warning threshold."""
    threshold = get_default_threshold(db)
    return {"default_threshold": threshold}


@router.put(
    "/settings/threshold",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Update default warning threshold",
    description="""
    Update the global default warning threshold.
    
    This affects all items that don't have a custom threshold set.
    Existing item statuses are NOT automatically recalculated.
    """,
)
async def update_threshold_setting(
    payload: DefaultThresholdUpdate,
    db: Session = Depends(get_db),
):
    """Update the default warning threshold."""
    success = update_default_threshold(db, payload.default_threshold)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update threshold setting",
        )
    return {"default_threshold": payload.default_threshold}
