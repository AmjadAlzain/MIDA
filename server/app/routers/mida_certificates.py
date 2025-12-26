"""
MIDA Certificate CRUD Router.

Provides REST API endpoints for managing MIDA certificates:
- Create/update drafts
- Confirm certificates (make read-only)
- Retrieve single or list of certificates

All endpoints use transactional database operations.
Confirmed certificates cannot be modified (returns 409 Conflict).
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.mida_certificate import (
    CertificateDraftCreateRequest,
    CertificateDraftUpdateRequest,
    CertificateListResponse,
    CertificateRead,
)
from app.services.mida_certificate_service import (
    CertificateConflictError,
    CertificateNotFoundError,
    confirm_certificate,
    create_or_replace_draft,
    get_certificate_by_id,
    list_certificates,
    update_draft_by_id,
)

router = APIRouter()


@router.post(
    "/draft",
    response_model=CertificateRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Certificate created"},
        200: {"description": "Existing draft updated"},
        409: {"description": "Certificate is confirmed and cannot be modified"},
    },
    summary="Create or replace a draft certificate",
    description="""
    Create a new draft certificate or replace an existing draft.

    If a certificate with the same certificate_number exists:
    - If status is 'confirmed': returns 409 Conflict
    - If status is 'draft': updates header and replaces all items (returns 200)

    If no certificate exists: creates new draft with items (returns 201).

    All items are replaced atomically - partial updates are not supported.
    """,
)
async def create_draft(
    payload: CertificateDraftCreateRequest,
    db: Session = Depends(get_db),
):
    """Create or replace a draft certificate."""
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
        409: {"description": "Certificate is confirmed and cannot be modified"},
    },
    summary="Update a draft certificate by ID",
    description="""
    Update an existing draft certificate by its UUID.

    Only draft certificates can be updated. Confirmed certificates are read-only.
    All items are replaced (delete existing, insert new) atomically.
    """,
)
async def update_draft(
    certificate_id: UUID,
    payload: CertificateDraftUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update an existing draft certificate."""
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
        200: {"description": "Certificate confirmed (or already confirmed)"},
        404: {"description": "Certificate not found"},
    },
    summary="Confirm a certificate",
    description="""
    Confirm a certificate, making it read-only.

    This operation is idempotent - if the certificate is already confirmed,
    it returns success without error.

    Once confirmed, a certificate cannot be modified via update endpoints.
    """,
)
async def confirm(
    certificate_id: UUID,
    db: Session = Depends(get_db),
):
    """Confirm a certificate (makes it read-only)."""
    try:
        certificate = confirm_certificate(db, certificate_id)
        return certificate
    except CertificateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
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
    limit: int = Query(50, ge=1, le=100, description="Maximum results per page"),
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
