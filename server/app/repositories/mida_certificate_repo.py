"""Repository helpers for MIDA certificates."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.mida_certificate import MidaCertificate, MidaCertificateItem


def get_certificate_by_number(
    db: Session, certificate_number: str, include_deleted: bool = False
) -> Optional[MidaCertificate]:
    """Fetch a certificate by its unique certificate number.
    
    Args:
        db: Database session
        certificate_number: The certificate number to look up
        include_deleted: If True, include soft-deleted certificates
        
    Returns:
        MidaCertificate if found, None otherwise
    """
    stmt = select(MidaCertificate).where(
        MidaCertificate.certificate_number == certificate_number
    )
    if not include_deleted:
        stmt = stmt.where(MidaCertificate.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def get_certificate_by_id(
    db: Session, certificate_id: UUID, include_deleted: bool = False
) -> Optional[MidaCertificate]:
    """
    Fetch a certificate by its UUID, eagerly loading items.

    Args:
        db: Database session
        certificate_id: UUID of the certificate
        include_deleted: If True, include soft-deleted certificates

    Returns:
        MidaCertificate with items loaded, or None if not found
    """
    stmt = (
        select(MidaCertificate)
        .options(joinedload(MidaCertificate.items))
        .where(MidaCertificate.id == certificate_id)
    )
    if not include_deleted:
        stmt = stmt.where(MidaCertificate.deleted_at.is_(None))
    return db.execute(stmt).unique().scalar_one_or_none()


def create_certificate_with_items(
    db: Session,
    certificate: MidaCertificate,
    items: list[MidaCertificateItem],
) -> MidaCertificate:
    """
    Insert a certificate and its items in a single transaction.

    The caller should handle session commit/rollback at the service layer.
    """
    db.add(certificate)
    db.flush()  # get certificate.id

    for item in items:
        item.certificate_id = certificate.id
        db.add(item)

    db.flush()
    return certificate


def replace_items(
    db: Session, certificate_id: UUID, new_items: list[MidaCertificateItem]
) -> None:
    """
    Replace all items for a certificate atomically.

    Deletes all existing items for the certificate, then inserts new items.
    Must be called within a transaction (caller handles commit/rollback).
    
    WARNING: This will cascade delete all import records! Use update_items_preserve_history
    if you need to preserve import history.

    Args:
        db: Database session
        certificate_id: UUID of the certificate
        new_items: List of new items to insert (should have certificate_id set)
    """
    # Delete all existing items for this certificate
    delete_stmt = delete(MidaCertificateItem).where(
        MidaCertificateItem.certificate_id == certificate_id
    )
    db.execute(delete_stmt)
    db.flush()

    # Insert new items
    for item in new_items:
        item.certificate_id = certificate_id
        db.add(item)

    db.flush()


def update_items_preserve_history(
    db: Session, 
    certificate_id: UUID, 
    new_items: list[MidaCertificateItem]
) -> None:
    """
    Update items for a certificate while preserving import history.
    
    This function matches items by line_no and updates them in-place,
    preserving their UUIDs and associated import records.
    
    Matching logic:
    1. Items with the same line_no are updated in-place
    2. Items that exist in DB but not in new_items are deleted
    3. Items in new_items that don't match existing items are inserted
    
    Args:
        db: Database session
        certificate_id: UUID of the certificate
        new_items: List of new items to insert/update
    """
    # Get existing items
    stmt = select(MidaCertificateItem).where(
        MidaCertificateItem.certificate_id == certificate_id
    )
    existing_items = list(db.execute(stmt).scalars().all())
    
    # Create lookup by line_no for existing items
    existing_by_line = {item.line_no: item for item in existing_items}
    
    # Track which existing items were matched
    matched_line_nos = set()
    
    for new_item in new_items:
        line_no = new_item.line_no
        
        if line_no in existing_by_line:
            # Update existing item in-place (preserves UUID and import records)
            existing_item = existing_by_line[line_no]
            existing_item.hs_code = new_item.hs_code
            existing_item.item_name = new_item.item_name
            existing_item.approved_quantity = new_item.approved_quantity
            existing_item.uom = new_item.uom
            existing_item.port_klang_qty = new_item.port_klang_qty
            existing_item.klia_qty = new_item.klia_qty
            existing_item.bukit_kayu_hitam_qty = new_item.bukit_kayu_hitam_qty
            matched_line_nos.add(line_no)
        else:
            # Insert new item
            new_item.certificate_id = certificate_id
            db.add(new_item)
    
    # Delete items that are no longer present
    for line_no, existing_item in existing_by_line.items():
        if line_no not in matched_line_nos:
            # This will cascade delete import records for removed items only
            db.delete(existing_item)
    
    db.flush()


def list_certificates(
    db: Session,
    certificate_number: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    include_deleted: bool = False,
) -> tuple[list[MidaCertificate], int]:
    """
    List certificates with optional filters and pagination.

    Args:
        db: Database session
        certificate_number: Filter by certificate number (partial match, case-insensitive)
        status: Filter by status ('draft' or 'confirmed')
        limit: Maximum number of results
        offset: Number of results to skip
        include_deleted: If True, include soft-deleted certificates

    Returns:
        Tuple of (list of certificates with items, total count)
    """
    # Base query
    query = select(MidaCertificate).options(joinedload(MidaCertificate.items))
    count_query = select(func.count(MidaCertificate.id))

    # Filter out deleted certificates by default
    if not include_deleted:
        query = query.where(MidaCertificate.deleted_at.is_(None))
        count_query = count_query.where(MidaCertificate.deleted_at.is_(None))

    # Apply filters
    if certificate_number:
        query = query.where(
            MidaCertificate.certificate_number.ilike(f"%{certificate_number}%")
        )
        count_query = count_query.where(
            MidaCertificate.certificate_number.ilike(f"%{certificate_number}%")
        )

    if status:
        query = query.where(MidaCertificate.status == status)
        count_query = count_query.where(MidaCertificate.status == status)

    # Get total count
    total = db.execute(count_query).scalar() or 0

    # Apply pagination and ordering
    query = (
        query.order_by(MidaCertificate.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    # Execute and return unique results (due to joinedload)
    certificates = db.execute(query).unique().scalars().all()

    return list(certificates), total


def list_deleted_certificates(
    db: Session,
    certificate_number: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MidaCertificate], int]:
    """
    List soft-deleted certificates with optional filters and pagination.

    Args:
        db: Database session
        certificate_number: Filter by certificate number (partial match, case-insensitive)
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of deleted certificates with items, total count)
    """
    # Base query - only deleted certificates
    query = select(MidaCertificate).options(joinedload(MidaCertificate.items))
    count_query = select(func.count(MidaCertificate.id))

    # Only include deleted certificates
    query = query.where(MidaCertificate.deleted_at.is_not(None))
    count_query = count_query.where(MidaCertificate.deleted_at.is_not(None))

    # Apply filters
    if certificate_number:
        query = query.where(
            MidaCertificate.certificate_number.ilike(f"%{certificate_number}%")
        )
        count_query = count_query.where(
            MidaCertificate.certificate_number.ilike(f"%{certificate_number}%")
        )

    # Get total count
    total = db.execute(count_query).scalar() or 0

    # Apply pagination and ordering (most recently deleted first)
    query = (
        query.order_by(MidaCertificate.deleted_at.desc())
        .offset(offset)
        .limit(limit)
    )

    # Execute and return unique results (due to joinedload)
    certificates = db.execute(query).unique().scalars().all()

    return list(certificates), total


def soft_delete_certificate(db: Session, certificate_id: UUID) -> Optional[MidaCertificate]:
    """
    Soft delete a certificate by setting deleted_at timestamp.

    Args:
        db: Database session
        certificate_id: UUID of the certificate to delete

    Returns:
        The soft-deleted MidaCertificate, or None if not found
    """
    certificate = get_certificate_by_id(db, certificate_id, include_deleted=False)
    if certificate is None:
        return None
    
    certificate.deleted_at = datetime.now(timezone.utc)
    db.flush()
    return certificate


def restore_certificate(db: Session, certificate_id: UUID) -> Optional[MidaCertificate]:
    """
    Restore a soft-deleted certificate by clearing deleted_at.

    Args:
        db: Database session
        certificate_id: UUID of the certificate to restore

    Returns:
        The restored MidaCertificate, or None if not found
    """
    # Get the deleted certificate
    stmt = (
        select(MidaCertificate)
        .options(joinedload(MidaCertificate.items))
        .where(
            MidaCertificate.id == certificate_id,
            MidaCertificate.deleted_at.is_not(None)
        )
    )
    certificate = db.execute(stmt).unique().scalar_one_or_none()
    
    if certificate is None:
        return None
    
    certificate.deleted_at = None
    db.flush()
    return certificate


def permanent_delete_certificate(db: Session, certificate_id: UUID) -> bool:
    """
    Permanently delete a certificate from the database.

    Args:
        db: Database session
        certificate_id: UUID of the certificate to delete

    Returns:
        True if deleted, False if not found
    """
    # First check if certificate exists (include deleted)
    certificate = get_certificate_by_id(db, certificate_id, include_deleted=True)
    if certificate is None:
        return False
    
    # Delete the certificate (cascade will handle items)
    db.delete(certificate)
    db.flush()
    return True


def list_distinct_companies(
    db: Session,
    status: Optional[str] = None,
) -> list[str]:
    """
    List distinct company names from active (non-deleted) certificates.

    Args:
        db: Database session
        status: Filter by status ('active' or 'expired')

    Returns:
        List of distinct company names, sorted alphabetically
    """
    query = select(MidaCertificate.company_name).distinct()
    
    # Filter out deleted certificates
    query = query.where(MidaCertificate.deleted_at.is_(None))
    
    # Apply status filter if provided
    if status:
        query = query.where(MidaCertificate.status == status)
    
    # Order alphabetically
    query = query.order_by(MidaCertificate.company_name)
    
    result = db.execute(query).scalars().all()
    return list(result)


def list_certificates_by_company(
    db: Session,
    company_name: str,
    status: Optional[str] = None,
) -> list[MidaCertificate]:
    """
    List certificates for a specific company.

    Args:
        db: Database session
        company_name: Company name to filter by
        status: Filter by status ('active' or 'expired')

    Returns:
        List of certificates with items for the given company
    """
    query = select(MidaCertificate).options(joinedload(MidaCertificate.items))
    
    # Filter by company and non-deleted
    query = query.where(
        MidaCertificate.company_name == company_name,
        MidaCertificate.deleted_at.is_(None)
    )
    
    # Apply status filter if provided
    if status:
        query = query.where(MidaCertificate.status == status)
    
    # Order by certificate number
    query = query.order_by(MidaCertificate.certificate_number)
    
    certificates = db.execute(query).unique().scalars().all()
    return list(certificates)


def get_certificates_by_ids(
    db: Session,
    certificate_ids: list[UUID],
) -> list[MidaCertificate]:
    """
    Fetch multiple certificates by their UUIDs, eagerly loading items.

    Args:
        db: Database session
        certificate_ids: List of certificate UUIDs

    Returns:
        List of certificates with items loaded
    """
    if not certificate_ids:
        return []
    
    query = (
        select(MidaCertificate)
        .options(joinedload(MidaCertificate.items))
        .where(
            MidaCertificate.id.in_(certificate_ids),
            MidaCertificate.deleted_at.is_(None)
        )
    )
    
    certificates = db.execute(query).unique().scalars().all()
    return list(certificates)
