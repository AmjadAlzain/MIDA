"""Repository helpers for MIDA certificates."""

from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.mida_certificate import MidaCertificate, MidaCertificateItem


def get_certificate_by_number(
    db: Session, certificate_number: str
) -> Optional[MidaCertificate]:
    """Fetch a certificate by its unique certificate number."""
    stmt = select(MidaCertificate).where(
        MidaCertificate.certificate_number == certificate_number
    )
    return db.execute(stmt).scalar_one_or_none()


def get_certificate_by_id(
    db: Session, certificate_id: UUID
) -> Optional[MidaCertificate]:
    """
    Fetch a certificate by its UUID, eagerly loading items.

    Args:
        db: Database session
        certificate_id: UUID of the certificate

    Returns:
        MidaCertificate with items loaded, or None if not found
    """
    stmt = (
        select(MidaCertificate)
        .options(joinedload(MidaCertificate.items))
        .where(MidaCertificate.id == certificate_id)
    )
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
        certificate_number: Filter by certificate number (partial match, case-insensitive)
        status: Filter by status ('draft' or 'confirmed')
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of certificates with items, total count)
    """
    # Base query
    query = select(MidaCertificate).options(joinedload(MidaCertificate.items))
    count_query = select(func.count(MidaCertificate.id))

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
