"""
MIDA Certificate Service Layer.

Handles business logic for certificate CRUD operations with transactional guarantees.
All database writes are transactional - either all changes succeed or none do.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.mida_certificate import (
    CertificateStatus,
    MidaCertificate,
    MidaCertificateItem,
)
from app.repositories import mida_certificate_repo as repo
from app.schemas.mida_certificate import (
    CertificateDraftCreateRequest,
    CertificateDraftUpdateRequest,
    CertificateItemIn,
)


class CertificateConflictError(Exception):
    """Raised when attempting to modify a confirmed certificate."""

    pass


class CertificateNotFoundError(Exception):
    """Raised when a certificate is not found."""

    pass


def _build_item_model(item_in: CertificateItemIn, certificate_id: UUID) -> MidaCertificateItem:
    """Convert a CertificateItemIn schema to a MidaCertificateItem model."""
    return MidaCertificateItem(
        certificate_id=certificate_id,
        line_no=item_in.line_no,
        hs_code=item_in.hs_code,
        item_name=item_in.item_name,
        approved_quantity=item_in.approved_quantity,
        uom=item_in.uom,
        port_klang_qty=item_in.port_klang_qty,
        klia_qty=item_in.klia_qty,
        bukit_kayu_hitam_qty=item_in.bukit_kayu_hitam_qty,
    )


def create_or_replace_draft(
    db: Session, payload: CertificateDraftCreateRequest
) -> MidaCertificate:
    """
    Create a new certificate.

    If a certificate with the same certificate_number already exists,
    raises CertificateConflictError (409) - duplicates are not allowed.

    New certificates are created with:
    - 'active' status if exemption_end_date is None or >= today
    - 'expired' status if exemption_end_date < today

    All operations are transactional - items are created atomically.

    Args:
        db: Database session
        payload: Certificate data with header, items, and optional raw_ocr_json

    Returns:
        The created MidaCertificate with items

    Raises:
        CertificateConflictError: If a certificate with the same number already exists
    """
    existing = repo.get_certificate_by_number(db, payload.header.certificate_number)

    if existing:
        # Cannot create duplicate certificates - reject with conflict error
        raise CertificateConflictError(
            f"Certificate '{payload.header.certificate_number}' already exists in the database. "
            f"Duplicate certificates are not allowed."
        )

    # Determine status based on exemption_end_date
    today = date.today()
    if payload.header.exemption_end_date and payload.header.exemption_end_date < today:
        status = CertificateStatus.expired.value
    else:
        status = CertificateStatus.active.value

    # Create new certificate
    certificate = MidaCertificate(
        certificate_number=payload.header.certificate_number,
        company_name=payload.header.company_name,
        exemption_start_date=payload.header.exemption_start_date,
        exemption_end_date=payload.header.exemption_end_date,
        status=status,
        source_filename=payload.header.source_filename,
        raw_ocr_json=payload.raw_ocr_json,
    )

    # Use repository to create certificate with items atomically
    items = [
        MidaCertificateItem(
            line_no=item.line_no,
            hs_code=item.hs_code,
            item_name=item.item_name,
            approved_quantity=item.approved_quantity,
            uom=item.uom,
            port_klang_qty=item.port_klang_qty,
            klia_qty=item.klia_qty,
            bukit_kayu_hitam_qty=item.bukit_kayu_hitam_qty,
        )
        for item in payload.items
    ]

    certificate = repo.create_certificate_with_items(db, certificate, items)
    db.commit()
    db.refresh(certificate)
    return certificate


def update_draft_by_id(
    db: Session, certificate_id: UUID, payload: CertificateDraftUpdateRequest
) -> MidaCertificate:
    """
    Update an existing certificate by ID.

    Only active certificates can be updated. Expired certificates are read-only.
    All items are replaced (delete existing, insert new) atomically.

    Args:
        db: Database session
        certificate_id: UUID of the certificate to update
        payload: Updated certificate data with header and items

    Returns:
        The updated MidaCertificate with items

    Raises:
        CertificateNotFoundError: If certificate not found
        CertificateConflictError: If certificate is expired
    """
    certificate = repo.get_certificate_by_id(db, certificate_id)

    if certificate is None:
        raise CertificateNotFoundError(f"Certificate with id '{certificate_id}' not found")

    if certificate.status == CertificateStatus.expired.value:
        raise CertificateConflictError(
            f"Certificate '{certificate.certificate_number}' is expired and cannot be modified"
        )

    # Update header fields
    certificate.certificate_number = payload.header.certificate_number
    certificate.company_name = payload.header.company_name
    certificate.exemption_start_date = payload.header.exemption_start_date
    certificate.exemption_end_date = payload.header.exemption_end_date
    certificate.source_filename = payload.header.source_filename
    certificate.updated_at = datetime.now(timezone.utc)

    # Replace items atomically
    new_items = [_build_item_model(item, certificate.id) for item in payload.items]
    repo.replace_items(db, certificate.id, new_items)

    db.commit()
    db.refresh(certificate)
    return certificate


def confirm_certificate(db: Session, certificate_id: UUID) -> MidaCertificate:
    """
    Mark a certificate as expired, making it read-only.

    Behavior: Idempotent - if already expired, returns success without error.

    Args:
        db: Database session
        certificate_id: UUID of the certificate to expire

    Returns:
        The expired MidaCertificate

    Raises:
        CertificateNotFoundError: If certificate not found
    """
    certificate = repo.get_certificate_by_id(db, certificate_id)

    if certificate is None:
        raise CertificateNotFoundError(f"Certificate with id '{certificate_id}' not found")

    # Idempotent: if already expired, just return it
    if certificate.status == CertificateStatus.expired.value:
        return certificate

    # Update status to expired
    certificate.status = CertificateStatus.expired.value
    certificate.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(certificate)
    return certificate


def get_certificate_by_id(db: Session, certificate_id: UUID) -> Optional[MidaCertificate]:
    """
    Get a certificate by ID.

    Args:
        db: Database session
        certificate_id: UUID of the certificate

    Returns:
        MidaCertificate if found, None otherwise
    """
    return repo.get_certificate_by_id(db, certificate_id)


def get_certificate_by_number(db: Session, certificate_number: str) -> Optional[MidaCertificate]:
    """
    Get a certificate by its certificate number.

    Args:
        db: Database session
        certificate_number: The certificate number to look up

    Returns:
        MidaCertificate if found, None otherwise
    """
    return repo.get_certificate_by_number(db, certificate_number)


def list_certificates(
    db: Session,
    certificate_number: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MidaCertificate], int]:
    """
    List certificates with optional filters and pagination.

    Args:
        db: Database session
        certificate_number: Filter by certificate number (partial match)
        status: Filter by status ('active' or 'expired')
        limit: Maximum number of results (default 50, max 100)
        offset: Number of results to skip

    Returns:
        Tuple of (list of certificates, total count)
    """
    # Cap limit at 100 for safety
    limit = min(limit, 100)

    return repo.list_certificates(
        db,
        certificate_number=certificate_number,
        status=status,
        limit=limit,
        offset=offset,
    )
