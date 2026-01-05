"""
HSCODE UOM Mapping Router.

Provides API endpoints for managing HSCODE to UOM mappings.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.hscode_uom_repo import (
    get_uom_by_hscode,
    get_uom_by_hscode_optional,
    seed_hscode_uom_from_csv,
    get_mapping_count,
    HscodeNotFoundError,
)
from app.models.hscode_uom_mapping import normalize_hscode


router = APIRouter()


class HscodeUomResponse(BaseModel):
    """Response for HSCODE UOM lookup."""
    
    hs_code: str = Field(..., description="The input HSCODE")
    normalized_hs_code: str = Field(..., description="The normalized HSCODE (dots removed)")
    uom: str = Field(..., description="The UOM for this HSCODE (UNIT or KGM)")


class SeedResponse(BaseModel):
    """Response for seeding HSCODE UOM data."""
    
    rows_affected: int = Field(..., description="Number of rows inserted/updated")
    total_mappings: int = Field(..., description="Total number of mappings after seeding")
    message: str = Field(..., description="Status message")


class MappingCountResponse(BaseModel):
    """Response for getting mapping count."""
    
    count: int = Field(..., description="Total number of HSCODE to UOM mappings")


@router.get(
    "/lookup/{hs_code}",
    response_model=HscodeUomResponse,
    summary="Look up UOM for an HSCODE",
    description="""
    Look up the UOM (Unit of Measure) for a given HSCODE.
    
    The HSCODE can be provided with or without dots (e.g., "8471.30.10" or "84713010").
    
    Returns:
    - UNIT: Balance deduction should use invoice quantity
    - KGM: Balance deduction should use net weight (kg)
    """,
    responses={
        200: {"description": "HSCODE found"},
        404: {"description": "HSCODE not found in mapping table"},
    },
)
async def lookup_hscode_uom(
    hs_code: str,
    db: Session = Depends(get_db),
) -> HscodeUomResponse:
    """Look up the UOM for an HSCODE."""
    try:
        uom = get_uom_by_hscode(db, hs_code)
        return HscodeUomResponse(
            hs_code=hs_code,
            normalized_hs_code=normalize_hscode(hs_code),
            uom=uom,
        )
    except HscodeNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/seed",
    response_model=SeedResponse,
    summary="Seed HSCODE UOM mappings from CSV",
    description="""
    Seed the HSCODE to UOM mapping table from the HSCODE.csv file.
    
    This will insert new mappings or update existing ones (upsert behavior).
    The CSV file must be located at `server/HSCODE.csv`.
    """,
    responses={
        200: {"description": "Seeding completed successfully"},
        404: {"description": "CSV file not found"},
        500: {"description": "Error during seeding"},
    },
)
async def seed_hscode_uom(
    db: Session = Depends(get_db),
) -> SeedResponse:
    """Seed HSCODE UOM mappings from the CSV file."""
    # Determine the CSV file path (relative to server directory)
    csv_path = Path(__file__).parent.parent.parent / "HSCODE.csv"
    
    if not csv_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CSV file not found: {csv_path}",
        )
    
    try:
        rows_affected = seed_hscode_uom_from_csv(db, str(csv_path))
        total_mappings = get_mapping_count(db)
        
        return SeedResponse(
            rows_affected=rows_affected,
            total_mappings=total_mappings,
            message=f"Successfully seeded {rows_affected} HSCODE to UOM mappings",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error seeding HSCODE UOM data: {str(e)}",
        )


@router.get(
    "/count",
    response_model=MappingCountResponse,
    summary="Get total mapping count",
    description="Get the total number of HSCODE to UOM mappings in the database.",
)
async def get_hscode_mapping_count(
    db: Session = Depends(get_db),
) -> MappingCountResponse:
    """Get the total number of HSCODE to UOM mappings."""
    count = get_mapping_count(db)
    return MappingCountResponse(count=count)
