"""
MIDA Certificate CRUD Router.

Provides REST API endpoints for managing MIDA certificates:
- Create/update certificates
- Retrieve single or list of certificates

All endpoints use transactional database operations.
Expired certificates cannot be modified (returns 409 Conflict).
New certificates are saved with 'active' status.
"""

from io import BytesIO
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.mida_certificate import MidaCertificate, MidaCertificateItem, MidaImportRecord
from app.schemas.mida_certificate import (
    CertificateDraftCreateRequest,
    CertificateDraftUpdateRequest,
    CertificateListResponse,
    CertificateRead,
)
from app.services.mida_certificate_service import (
    CertificateConflictError,
    CertificateNotFoundError,
    CertificateRestoreConflictError,
    confirm_certificate,
    create_or_replace_draft,
    get_certificate_by_id,
    get_certificate_by_number,
    list_certificates,
    list_deleted_certificates,
    list_distinct_companies,
    list_certificates_by_company,
    permanent_delete_certificate,
    restore_certificate,
    soft_delete_certificate,
    update_draft_by_id,
)
from app.services.xlsx_export_service import (
    generate_certificate_xlsx,
    generate_item_balance_sheet_xlsx,
    generate_all_items_balance_sheets_xlsx,
)

router = APIRouter()


@router.get(
    "/check/{certificate_number:path}",
    status_code=status.HTTP_200_OK,
    summary="Check if certificate number exists",
    description="Check if a certificate with the given number already exists in the database.",
)
async def check_certificate_exists(
    certificate_number: str,
    db: Session = Depends(get_db),
):
    """Check if a certificate number already exists."""
    certificate = get_certificate_by_number(db, certificate_number)
    if certificate:
        return {
            "exists": True,
            "id": str(certificate.id),
            "status": certificate.status,
            "company_name": certificate.company_name,
        }
    return {"exists": False}


@router.get(
    "/companies",
    status_code=status.HTTP_200_OK,
    summary="List distinct company names",
    description="Get a list of all distinct company names from active certificates.",
)
async def get_companies(
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status ('active' or 'expired')"
    ),
    db: Session = Depends(get_db),
):
    """List distinct company names from certificates."""
    companies = list_distinct_companies(db, status=status_filter)
    return {"companies": companies}


@router.get(
    "/by-company/{company_name:path}",
    status_code=status.HTTP_200_OK,
    summary="List certificates by company",
    description="Get all certificates for a specific company.",
)
async def get_certificates_by_company(
    company_name: str,
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status ('active' or 'expired')"
    ),
    db: Session = Depends(get_db),
):
    """List certificates for a specific company."""
    certificates = list_certificates_by_company(db, company_name, status=status_filter)
    return {
        "company_name": company_name,
        "certificates": [
            {
                "id": str(cert.id),
                "certificate_number": cert.certificate_number,
                "model_number": cert.model_number,
                "exemption_start_date": cert.exemption_start_date.isoformat() if cert.exemption_start_date else None,
                "exemption_end_date": cert.exemption_end_date.isoformat() if cert.exemption_end_date else None,
                "status": cert.status,
                "item_count": len(cert.items) if cert.items else 0,
            }
            for cert in certificates
        ],
        "total": len(certificates),
    }


@router.post(
    "/draft",
    response_model=CertificateRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Certificate created"},
        409: {"description": "Certificate with this number already exists"},
    },
    summary="Create a new certificate",
    description="""
    Create a new certificate.

    If a certificate with the same certificate_number already exists,
    returns 409 Conflict - duplicates are not allowed.

    New certificates are created with:
    - 'active' status if exemption_end_date is None or >= today
    - 'expired' status if exemption_end_date < today
    """,
)
async def create_draft(
    payload: CertificateDraftCreateRequest,
    db: Session = Depends(get_db),
):
    """Create or update a certificate."""
    try:
        certificate = create_or_replace_draft(db, payload)
        return certificate
    except CertificateConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.put(
    "/{certificate_id}",
    response_model=CertificateRead,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Certificate updated"},
        404: {"description": "Certificate not found"},
        409: {"description": "Certificate is expired and cannot be modified"},
    },
    summary="Update a certificate by ID",
    description="""
    Update an existing certificate by its UUID.

    Only active certificates can be updated. Expired certificates are read-only.
    All items are replaced (delete existing, insert new) atomically.
    """,
)
async def update_draft(
    certificate_id: UUID,
    payload: CertificateDraftUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update an existing certificate."""
    try:
        certificate = update_draft_by_id(db, certificate_id, payload)
        return certificate
    except CertificateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CertificateConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post(
    "/{certificate_id}/confirm",
    response_model=CertificateRead,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Certificate marked as expired (or already expired)"},
        404: {"description": "Certificate not found"},
    },
    summary="Mark a certificate as expired",
    description="""
    Mark a certificate as expired, making it read-only.

    This operation is idempotent - if the certificate is already expired,
    it returns success without error.

    Once expired, a certificate cannot be modified via update endpoints.
    """,
)
async def confirm(
    certificate_id: UUID,
    db: Session = Depends(get_db),
):
    """Mark a certificate as expired (makes it read-only)."""
    try:
        certificate = confirm_certificate(db, certificate_id)
        return certificate
    except CertificateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/deleted",
    response_model=CertificateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List deleted certificates",
    description="""
    List soft-deleted certificates with optional filters and pagination.

    These certificates have been deleted but can be restored.
    Most recently deleted certificates are shown first.
    """,
)
async def get_deleted_certificates(
    certificate_number: Optional[str] = Query(
        None, description="Filter by certificate number (partial match)"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
):
    """List soft-deleted certificates."""
    certificates, total = list_deleted_certificates(
        db,
        certificate_number=certificate_number,
        limit=limit,
        offset=offset,
    )
    return CertificateListResponse(
        items=certificates,
        total=total,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Export Endpoints
# =============================================================================

@router.get(
    "/{certificate_id}/export",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "XLSX file generated"},
        404: {"description": "Certificate not found"},
    },
    summary="Export certificate to XLSX",
    description="""
    Export a MIDA certificate to XLSX format with:
    - Certificate header information (company, dates, status)
    - Table of all items with approved and remaining quantities per port
    """,
)
async def export_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db),
):
    """Export a certificate to XLSX format."""
    # Load certificate with items
    certificate = db.query(MidaCertificate).options(
        selectinload(MidaCertificate.items)
    ).filter(
        MidaCertificate.id == certificate_id,
        MidaCertificate.deleted_at.is_(None),
    ).first()
    
    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with id '{certificate_id}' not found",
        )
    
    # Generate XLSX
    xlsx_bytes = generate_certificate_xlsx(certificate)
    
    # Create safe filename
    safe_cert_num = certificate.certificate_number.replace("/", "_").replace("\\", "_")
    filename = f"{safe_cert_num}_certificate.xlsx"
    
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/{certificate_id}/items/{item_id}/balance-sheet/export",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "XLSX file generated"},
        404: {"description": "Certificate or item not found"},
    },
    summary="Export item balance sheet to XLSX",
    description="""
    Export an item's balance sheet (import history) to XLSX format.
    
    If port is specified, exports only that port's history in a single sheet.
    If port is not specified (or 'all'), exports all 3 ports as separate sheets
    in the same workbook.
    
    Format:
    - Item and certificate info header at top
    - Import history table below
    """,
)
async def export_item_balance_sheet(
    certificate_id: UUID,
    item_id: UUID,
    port: Optional[str] = Query(
        None, 
        description="Port filter: port_klang, klia, bukit_kayu_hitam, or omit for all"
    ),
    db: Session = Depends(get_db),
):
    """Export an item's balance sheet to XLSX format."""
    # Load certificate
    certificate = db.query(MidaCertificate).filter(
        MidaCertificate.id == certificate_id,
        MidaCertificate.deleted_at.is_(None),
    ).first()
    
    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with id '{certificate_id}' not found",
        )
    
    # Load item
    item = db.query(MidaCertificateItem).filter(
        MidaCertificateItem.id == item_id,
        MidaCertificateItem.certificate_id == certificate_id,
    ).first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id '{item_id}' not found in certificate",
        )
    
    # Validate port if specified
    valid_ports = ["port_klang", "klia", "bukit_kayu_hitam"]
    if port and port != "all" and port not in valid_ports:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid port. Must be one of: {valid_ports}",
        )
    
    # Load import records separately to avoid SQLAlchemy issues
    import_records = db.query(MidaImportRecord).filter(
        MidaImportRecord.certificate_item_id == item_id
    ).order_by(MidaImportRecord.created_at).all()
    
    # Generate XLSX
    port_param = port if port and port != "all" else None
    xlsx_bytes = generate_item_balance_sheet_xlsx(item, certificate, port_param, import_records)
    
    # Create safe filename
    safe_cert_num = certificate.certificate_number.replace("/", "_").replace("\\", "_")
    port_suffix = f"_{port}" if port and port != "all" else "_all_ports"
    filename = f"{safe_cert_num}_item{item.line_no}_balance{port_suffix}.xlsx"
    
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/{certificate_id}/balance-sheets/export",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "XLSX file generated"},
        404: {"description": "Certificate not found"},
        400: {"description": "Invalid port specified"},
    },
    summary="Export all items' balance sheets to XLSX",
    description="""
    Export balance sheets for ALL items in a certificate to a single XLSX workbook.
    Each item gets its own sheet with its import history for the specified port.
    
    This is useful for getting a complete overview of all balance sheets 
    for a certificate at a specific port.
    """,
)
async def export_all_balance_sheets(
    certificate_id: UUID,
    port: str = Query(
        ...,
        description="Port to export: port_klang, klia, or bukit_kayu_hitam"
    ),
    db: Session = Depends(get_db),
):
    """Export all items' balance sheets for a specific port."""
    # Validate port
    valid_ports = ["port_klang", "klia", "bukit_kayu_hitam"]
    if port not in valid_ports:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid port. Must be one of: {valid_ports}",
        )
    
    # Load certificate with items
    certificate = db.query(MidaCertificate).options(
        selectinload(MidaCertificate.items)
    ).filter(
        MidaCertificate.id == certificate_id,
        MidaCertificate.deleted_at.is_(None),
    ).first()
    
    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with id '{certificate_id}' not found",
        )
    
    if not certificate.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Certificate has no items to export",
        )
    
    # Load all import records for items in this certificate
    item_ids = [item.id for item in certificate.items]
    all_import_records = db.query(MidaImportRecord).filter(
        MidaImportRecord.certificate_item_id.in_(item_ids)
    ).order_by(MidaImportRecord.created_at).all()
    
    # Group import records by item_id
    import_records_by_item: dict = {}
    for record in all_import_records:
        if record.certificate_item_id not in import_records_by_item:
            import_records_by_item[record.certificate_item_id] = []
        import_records_by_item[record.certificate_item_id].append(record)
    
    # Generate XLSX
    xlsx_bytes = generate_all_items_balance_sheets_xlsx(certificate, port, import_records_by_item)
    
    # Create safe filename
    safe_cert_num = certificate.certificate_number.replace("/", "_").replace("\\", "_")
    port_display = {"port_klang": "PortKlang", "klia": "KLIA", "bukit_kayu_hitam": "BKH"}
    filename = f"{safe_cert_num}_all_balances_{port_display.get(port, port)}.xlsx"
    
    return StreamingResponse(
        BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/{certificate_id}",
    response_model=CertificateRead,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Certificate found"},
        404: {"description": "Certificate not found"},
    },
    summary="Get a certificate by ID",
    description="Retrieve a single certificate by its UUID, including all items.",
)
async def get_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db),
):
    """Get a certificate by ID."""
    certificate = get_certificate_by_id(db, certificate_id)
    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with id '{certificate_id}' not found",
        )
    return certificate


@router.get(
    "",
    response_model=CertificateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List certificates",
    description="""
    List certificates with optional filters and pagination.

    Filters:
    - certificate_number: Partial match (case-insensitive)
    - status: Exact match ('draft' or 'confirmed')

    Pagination:
    - limit: Maximum results per page (default 50, max 100)
    - offset: Number of results to skip
    """,
)
async def get_certificates(
    certificate_number: Optional[str] = Query(
        None, description="Filter by certificate number (partial match)"
    ),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status ('draft' or 'confirmed')"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
):
    """List certificates with optional filters."""
    certificates, total = list_certificates(
        db,
        certificate_number=certificate_number,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return CertificateListResponse(
        items=certificates,
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Soft Delete / Restore / Permanent Delete Endpoints
# ============================================================================

@router.delete(
    "/{certificate_id}",
    response_model=CertificateRead,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Certificate soft-deleted"},
        404: {"description": "Certificate not found or already deleted"},
    },
    summary="Soft delete a certificate",
    description="""
    Soft delete a certificate by setting its deleted_at timestamp.

    The certificate will be excluded from:
    - Certificate listings (unless viewing deleted certificates)
    - MIDA invoice matching

    The certificate can be restored later or permanently deleted.
    """,
)
async def delete_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db),
):
    """Soft delete a certificate."""
    try:
        certificate = soft_delete_certificate(db, certificate_id)
        return certificate
    except CertificateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{certificate_id}/restore",
    response_model=CertificateRead,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Certificate restored"},
        404: {"description": "Certificate not found or not deleted"},
        409: {"description": "Certificate number already in use by active certificate"},
    },
    summary="Restore a soft-deleted certificate",
    description="""
    Restore a soft-deleted certificate by clearing its deleted_at timestamp.

    This will fail if:
    - The certificate is not found
    - The certificate is not deleted
    - Another active certificate already uses the same certificate number
    """,
)
async def restore_deleted_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db),
):
    """Restore a soft-deleted certificate."""
    try:
        certificate = restore_certificate(db, certificate_id)
        return certificate
    except CertificateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CertificateRestoreConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.delete(
    "/{certificate_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Certificate permanently deleted"},
        404: {"description": "Certificate not found"},
    },
    summary="Permanently delete a certificate",
    description="""
    Permanently delete a certificate from the database.

    **WARNING**: This action cannot be undone!
    All related items and import records will also be deleted.

    This can be used for both active and soft-deleted certificates.
    """,
)
async def permanently_delete_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db),
):
    """Permanently delete a certificate."""
    try:
        permanent_delete_certificate(db, certificate_id)
        return None
    except CertificateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
