"""Repository helpers for HSCODE to UOM mappings."""

from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.hscode_uom_mapping import HscodeUomMapping, normalize_hscode


class HscodeNotFoundError(Exception):
    """Raised when an HSCODE is not found in the mapping table."""
    pass


def normalize_uom_value(uom: str) -> str:
    """
    Normalize UOM value to standard format.
    
    - KGM variations (KGM, KG, KGS, KILOGRAM, etc.) -> "KGM"
    - UNIT variations (UNIT, UNT, UNITS, PCS, etc.) -> "UNT"
    
    Args:
        uom: Raw UOM value from database
        
    Returns:
        Normalized UOM: "KGM" or "UNT"
    """
    if not uom:
        return ""
    
    uom_upper = uom.upper().strip()
    
    # KGM variations
    if uom_upper in ("KGM", "KG", "KGS", "KILOGRAM", "KILOGRAMS"):
        return "KGM"
    
    # UNIT variations - convert to UNT
    if uom_upper in ("UNIT", "UNT", "UNITS", "PCS", "PC", "PIECE", "PIECES", "EA", "EACH", "NOS", "NO"):
        return "UNT"
    
    # Default: return as-is (uppercase)
    return uom_upper


def get_uom_by_hscode(db: Session, hs_code: str) -> str:
    """
    Get the UOM for a given HSCODE.
    
    Comparison ignores dots and trailing zeros in both the input and database values.
    Example: "79.100.100" matches "79100100" in DB (both normalize to "791001" after stripping trailing zeros)
    
    If no exact match is found, returns the UOM of the most similar HSCODE (longest common prefix).
    
    Args:
        db: Database session
        hs_code: The HSCODE to look up (can be with or without dots, with or without trailing zeros)
        
    Returns:
        The UOM for the HSCODE ("UNIT" or "KGM")
        
    Raises:
        HscodeNotFoundError: If no matching or similar HSCODE is found in the mapping table
    """
    # Normalize input HSCODE (remove dots and whitespace)
    normalized = normalize_hscode(hs_code)

    if not normalized:
        raise HscodeNotFoundError(f"Invalid HSCODE: '{hs_code}'")

    # Stripped form: remove trailing zeros for comparison only
    normalized_stripped = normalized.rstrip('0')

    # Fetch all mappings and compare using stripped forms to be robust
    mappings = db.execute(select(HscodeUomMapping)).scalars().all()
    if not mappings:
        raise HscodeNotFoundError(f"HSCODE mapping table is empty")

    # First prefer exact stripped match (b.stripped == a.stripped)
    for m in mappings:
        try:
            db_norm = normalize_hscode(m.hs_code).rstrip('0')
        except Exception:
            db_norm = normalize_hscode(m.hs_code)
        if db_norm == normalized_stripped:
            return normalize_uom_value(m.uom)

    # No exact stripped match — fallback to longest common-stripped-prefix
    best_match = None
    best_prefix_len = 0
    for m in mappings:
        db_norm = normalize_hscode(m.hs_code).rstrip('0')
        # compute common prefix length between normalized_stripped and db_norm
        maxlen = min(len(normalized_stripped), len(db_norm))
        common = 0
        for i in range(maxlen):
            if normalized_stripped[i] == db_norm[i]:
                common += 1
            else:
                break
        if common > best_prefix_len:
            best_prefix_len = common
            best_match = m

    if best_match and best_prefix_len > 0:
        return normalize_uom_value(best_match.uom)

    raise HscodeNotFoundError(f"HSCODE '{hs_code}' (normalized: '{normalized}') not found in UOM mapping table")


def get_uom_by_hscode_optional(db: Session, hs_code: str) -> Optional[str]:
    """
    Get the UOM for a given HSCODE, returning None if not found.
    
    Args:
        db: Database session
        hs_code: The HSCODE to look up (can be with or without dots)
        
    Returns:
        The UOM for the HSCODE ("UNIT" or "KGM"), or None if not found
    """
    try:
        return get_uom_by_hscode(db, hs_code)
    except HscodeNotFoundError:
        return None


def bulk_upsert_hscode_uom(
    db: Session,
    mappings: list[tuple[str, str]],
    batch_size: int = 500,
) -> int:
    """
    Bulk insert or update HSCODE to UOM mappings.
    
    Args:
        db: Database session
        mappings: List of (hs_code, uom) tuples
        batch_size: Number of rows per batch (default: 500)
        
    Returns:
        Number of rows affected
    """
    if not mappings:
        return 0
    
    # Prepare data for insert
    data = [
        {
            "id": uuid.uuid4(),
            "hs_code": normalize_hscode(hs_code),
            "uom": uom,
        }
        for hs_code, uom in mappings
        if normalize_hscode(hs_code)  # Skip empty HSCODEs
    ]
    
    if not data:
        return 0
    
    total_affected = 0
    
    # Process in batches to avoid parameter limit issues
    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]
        
        # Use PostgreSQL's INSERT ... ON CONFLICT for upsert
        stmt = insert(HscodeUomMapping).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["hs_code"],
            set_={"uom": stmt.excluded.uom},
        )
        
        result = db.execute(stmt)
        total_affected += result.rowcount
    
    db.commit()
    
    return total_affected


def seed_hscode_uom_from_csv(db: Session, csv_path: str) -> int:
    """
    Seed HSCODE to UOM mappings from a CSV file.
    
    Expected CSV format:
        HS Code,Unit
        1012100,UNT
        2011000,KGM
        ...
    
    UOM normalization:
        - UNT, UNIT -> UNIT
        - KGM, KG, KGS, tonne -> KGM
        - Other UOMs are skipped
    
    Args:
        db: Database session
        csv_path: Path to the CSV file
        
    Returns:
        Number of rows inserted/updated
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    mappings: list[tuple[str, str]] = []
    
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hs_code = row.get("HS Code", "").strip()
            unit = row.get("Unit", "").strip()
            
            if not hs_code or not unit:
                continue
            
            # Normalize UOM
            unit_lower = unit.lower()
            if unit_lower in ("unt", "unit", "units"):
                uom = "UNIT"
            elif unit_lower in ("kgm", "kg", "kgs", "kilogram", "kilograms", "tonne"):
                uom = "KGM"
            else:
                # Skip unknown UOMs (l, m2, m3, etc.)
                continue
            
            mappings.append((hs_code, uom))
    
    return bulk_upsert_hscode_uom(db, mappings)


def get_mapping_count(db: Session) -> int:
    """Get the total number of HSCODE to UOM mappings."""
    from sqlalchemy import func
    
    stmt = select(func.count()).select_from(HscodeUomMapping)
    return db.execute(stmt).scalar() or 0


def delete_all_mappings(db: Session) -> int:
    """Delete all HSCODE to UOM mappings (for testing/reset)."""
    from sqlalchemy import delete
    
    stmt = delete(HscodeUomMapping)
    result = db.execute(stmt)
    db.commit()
    return result.rowcount
