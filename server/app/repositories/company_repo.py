"""Company repository for database operations."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company


def get_all_companies(db: Session) -> list[Company]:
    """Get all companies from the database."""
    stmt = select(Company).order_by(Company.name)
    return list(db.execute(stmt).scalars().all())


def get_company_by_id(db: Session, company_id: UUID) -> Optional[Company]:
    """Get a company by its ID."""
    stmt = select(Company).where(Company.id == company_id)
    return db.execute(stmt).scalar_one_or_none()


def get_company_by_name(db: Session, name: str) -> Optional[Company]:
    """Get a company by its name (case-insensitive)."""
    stmt = select(Company).where(Company.name.ilike(name))
    return db.execute(stmt).scalar_one_or_none()


def create_company(
    db: Session,
    name: str,
    sst_default_behavior: str = "mida_only",
    dual_flag_routing: str = "mida",
) -> Company:
    """Create a new company."""
    company = Company(
        name=name,
        sst_default_behavior=sst_default_behavior,
        dual_flag_routing=dual_flag_routing,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company
