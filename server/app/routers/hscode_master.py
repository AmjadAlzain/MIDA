"""
HSCODE Master Router.

Provides API endpoints for managing HSCODE Master data (Part Name to HSCODE/UOM mapping).
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.hscode_master_repo import (
    seed_hscode_master_data,
    get_hscode_master_count,
    lookup_by_part_name,
    load_cache_from_db,
    get_cache_size,
    is_cache_loaded,
)


router = APIRouter()


class SeedResponse(BaseModel):
    """Response for seeding HSCODE master data."""
    
    total_rows: int = Field(..., description="Total rows in CSV file")
    inserted: int = Field(..., description="Number of rows inserted")
    skipped: int = Field(..., description="Number of rows skipped")
    total_records: int = Field(..., description="Total records in database after seeding")
    cache_size: int = Field(..., description="Number of entries in memory cache")
    message: str = Field(..., description="Status message")


class CountResponse(BaseModel):
    """Response for getting record count."""
    
    database_count: int = Field(..., description="Total records in database")
    cache_size: int = Field(..., description="Number of entries in memory cache")
    cache_loaded: bool = Field(..., description="Whether cache is loaded")


class LookupRequest(BaseModel):
    """Request for looking up HSCODE by part name."""
    
    description: str = Field(..., description="Item description/part name to look up")
    fuzzy_threshold: float = Field(0.85, ge=0.0, le=1.0, description="Fuzzy match threshold (0.0-1.0)")


class LookupResponse(BaseModel):
    """Response for part name lookup."""
    
    found: bool = Field(..., description="Whether a match was found")
    part_name: Optional[str] = Field(None, description="Matched part name from master data")
    hs_code: Optional[str] = Field(None, description="HSCODE for the matched part")
    uom: Optional[str] = Field(None, description="UOM for the matched part (UNIT or KGM)")
    match_score: Optional[float] = Field(None, description="Match score (1.0 = exact match)")
    is_exact_match: Optional[bool] = Field(None, description="Whether match was exact")


@router.post(
    "/seed",
    response_model=SeedResponse,
    summary="Seed HSCODE master data from CSV",
    description="""
    Seed the HSCODE master table from the hscode_master.csv file.
    
    This will clear existing data and insert fresh records from the CSV.
    The CSV file must be located at `server/hscode_master.csv`.
    
    The cache is automatically reloaded after seeding.
    """,
    responses={
        200: {"description": "Seeding completed successfully"},
        404: {"description": "CSV file not found"},
        500: {"description": "Error during seeding"},
    },
)
async def seed_hscode_master(
    db: Session = Depends(get_db),
) -> SeedResponse:
    """Seed HSCODE master data from CSV file."""
    csv_path = Path(__file__).parent.parent.parent / "hscode_master.csv"
    
    if not csv_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CSV file not found: {csv_path}",
        )
    
    try:
        stats = seed_hscode_master_data(db, csv_path)
        total_records = get_hscode_master_count(db)
        
        return SeedResponse(
            total_rows=stats["total_rows"],
            inserted=stats["inserted"],
            skipped=stats["skipped"],
            total_records=total_records,
            cache_size=get_cache_size(),
            message=f"Successfully seeded {stats['inserted']} HSCODE master records",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error seeding HSCODE master data: {str(e)}",
        )


@router.get(
    "/count",
    response_model=CountResponse,
    summary="Get record count",
    description="Get the total number of HSCODE master records in the database and cache.",
)
async def get_count(
    db: Session = Depends(get_db),
) -> CountResponse:
    """Get the total number of HSCODE master records."""
    return CountResponse(
        database_count=get_hscode_master_count(db),
        cache_size=get_cache_size(),
        cache_loaded=is_cache_loaded(),
    )


@router.post(
    "/lookup",
    response_model=LookupResponse,
    summary="Look up HSCODE by part name",
    description="""
    Look up HSCODE and UOM by matching part name/description.
    
    First attempts exact match (after normalization), then falls back to
    fuzzy matching with the specified threshold.
    
    The cache is automatically loaded from database if not already loaded.
    """,
)
async def lookup_part_name(
    request: LookupRequest,
    db: Session = Depends(get_db),
) -> LookupResponse:
    """Look up HSCODE and UOM by part name."""
    result = lookup_by_part_name(
        description=request.description,
        fuzzy_threshold=request.fuzzy_threshold,
        db=db,
    )
    
    if result is None:
        return LookupResponse(
            found=False,
            part_name=None,
            hs_code=None,
            uom=None,
            match_score=None,
            is_exact_match=None,
        )
    
    return LookupResponse(
        found=True,
        part_name=result.part_name,
        hs_code=result.hs_code,
        uom=result.uom,
        match_score=result.match_score,
        is_exact_match=result.is_exact_match,
    )


@router.post(
    "/load-cache",
    response_model=CountResponse,
    summary="Load cache from database",
    description="Manually trigger loading the HSCODE master cache from database.",
)
async def load_cache(
    db: Session = Depends(get_db),
) -> CountResponse:
    """Load the HSCODE master cache from database."""
    load_cache_from_db(db)
    
    return CountResponse(
        database_count=get_hscode_master_count(db),
        cache_size=get_cache_size(),
        cache_loaded=is_cache_loaded(),
    )
