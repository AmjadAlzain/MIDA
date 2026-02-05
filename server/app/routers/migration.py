"""
MIDA Migration Router.

Provides REST API endpoints for:
- Previewing balance sheet migrations from XLSX files
- Applying migrations with user-provided conflict resolutions
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.migration import (
    ImportPort,
    MigrationPreviewResponse,
    MigrationApplyRequest,
    MigrationApplyResponse,
)
from app.services.migration_service import (
    preview_migration,
    apply_migration,
    InvalidFileError,
    CertificateNotFoundError,
    MigrationError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Migration Endpoints
# =============================================================================

@router.post(
    "/preview",
    response_model=MigrationPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview balance sheet migration",
    description="""
    Upload an XLSX balance sheet file and get a preview of what will be migrated.
    
    The preview includes:
    - Certificate matching against database
    - Item-by-item matching with status (matched, name_mismatch, not_found)
    - Duplicate invoice detection
    - Invoice counts per item
    
    This endpoint does NOT modify the database. Use the apply endpoint
    after reviewing the preview and providing conflict resolutions.
    """,
    responses={
        200: {"description": "Preview generated successfully"},
        400: {"description": "Invalid file or parsing error"},
        422: {"description": "Validation error"},
    },
)
async def preview_balance_sheet_migration(
    file: Annotated[UploadFile, File(description="XLSX balance sheet file")],
    port: Annotated[ImportPort, Form(description="Import port for all records")],
    preselected_certificate: Annotated[str | None, Form(description="Pre-selected certificate number from URL")] = None,
    use_certificate: Annotated[str | None, Form(description="Force use this certificate number for item matching")] = None,
    db: Session = Depends(get_db),
):
    """
    Preview migration from uploaded XLSX balance sheet.
    
    The file should follow the company template format with:
    - One sheet per item
    - Header rows containing certificate number, item name, line number
    - Invoice table starting at row 15
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )
    
    if not file.filename.lower().endswith(('.xlsx', '.xlsm')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an XLSX file",
        )
    
    # Read file content
    try:
        file_content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}",
        )
    
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )
    
    # Preview migration
    try:
        preview = preview_migration(db, file_content, port, preselected_certificate, use_certificate)
        return preview
    except InvalidFileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error during migration preview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process file: {str(e)}",
        )


@router.post(
    "/apply",
    response_model=MigrationApplyResponse,
    status_code=status.HTTP_200_OK,
    summary="Apply balance sheet migration",
    description="""
    Apply a migration based on the preview data and user resolutions.
    
    For items with name_mismatch status, you must provide a resolution:
    - rename_db: Update the database item name to match the XLSX
    - keep_db_name: Keep the database name but apply the invoice data
    - skip: Skip this item entirely
    
    Items with matched status are processed automatically.
    Items with not_found status are skipped.
    
    Duplicate invoices (same form_reg_no + item + port) are skipped
    and returned in the flagged_duplicates array for manual review.
    """,
    responses={
        200: {"description": "Migration applied successfully"},
        400: {"description": "Invalid request or missing resolutions"},
        404: {"description": "Certificate not found"},
    },
)
async def apply_balance_sheet_migration(
    request: MigrationApplyRequest,
    db: Session = Depends(get_db),
):
    """
    Apply migration with user-provided conflict resolutions.
    
    Creates synthetic import records for each invoice row,
    recalculates balances, and updates item remaining quantities.
    """
    try:
        result = apply_migration(db, request)
        return result
    except CertificateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except MigrationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Unexpected error during migration apply: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration failed: {str(e)}",
        )


@router.post(
    "/fix-remaining-quantities/{certificate_id}",
    status_code=status.HTTP_200_OK,
    summary="Initialize remaining quantities for a certificate",
    description="""
    Fix items that have NULL remaining quantities by initializing them
    based on approved quantities and existing import records.
    
    This is useful for certificates created before remaining quantities
    were automatically initialized.
    """,
)
async def fix_remaining_quantities(
    certificate_id: str,
    db: Session = Depends(get_db),
):
    """
    Initialize remaining quantities for all items in a certificate.
    
    For each item:
    1. If remaining_quantity is NULL and no imports exist, set to approved_quantity
    2. If remaining_quantity is NULL but imports exist, recalculate from imports
    """
    from uuid import UUID
    from decimal import Decimal
    from app.repositories import mida_certificate_repo, mida_import_repo
    
    try:
        cert_uuid = UUID(certificate_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid certificate ID format",
        )
    
    certificate = mida_certificate_repo.get_certificate_by_id(db, cert_uuid)
    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with id '{certificate_id}' not found",
        )
    
    fixed_count = 0
    for item in certificate.items:
        # Check if remaining quantities need initialization
        if item.remaining_quantity is None:
            # Check if there are any imports for this item
            imports = mida_import_repo.get_import_history_for_item(db, item.id)
            
            if imports:
                # Recalculate from existing imports
                mida_import_repo.recalculate_item_remaining_quantities(db, item.id)
            else:
                # No imports - initialize to approved quantity
                approved_qty = item.approved_quantity or Decimal("0")
                
                # Check if port allocations are set
                has_port_allocations = (
                    (item.port_klang_qty is not None and item.port_klang_qty > 0) or
                    (item.klia_qty is not None and item.klia_qty > 0) or
                    (item.bukit_kayu_hitam_qty is not None and item.bukit_kayu_hitam_qty > 0)
                )
                
                if has_port_allocations:
                    item.remaining_port_klang = item.port_klang_qty or Decimal("0")
                    item.remaining_klia = item.klia_qty or Decimal("0")
                    item.remaining_bukit_kayu_hitam = item.bukit_kayu_hitam_qty or Decimal("0")
                    item.remaining_quantity = item.remaining_port_klang + item.remaining_klia + item.remaining_bukit_kayu_hitam
                else:
                    item.remaining_quantity = approved_qty
                    item.remaining_port_klang = approved_qty
                    item.remaining_klia = approved_qty
                    item.remaining_bukit_kayu_hitam = approved_qty
                
                item.quantity_status = "normal"
            
            fixed_count += 1
    
    db.commit()
    
    return {
        "success": True,
        "certificate_id": certificate_id,
        "certificate_number": certificate.certificate_number,
        "items_fixed": fixed_count,
        "total_items": len(certificate.items),
    }
