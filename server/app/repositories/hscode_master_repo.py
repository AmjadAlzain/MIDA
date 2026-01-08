"""Repository helpers for HSCODE Master Part Name to HSCODE/UOM lookups."""

from __future__ import annotations

import csv
import re
import unicodedata
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.hscode_master import HscodeMaster


# =============================================================================
# In-Memory Cache for Fast Lookups
# =============================================================================

@dataclass
class HscodeMasterEntry:
    """Cached entry for HSCODE master lookup."""
    part_name: str
    part_name_normalized: str
    hs_code: str
    uom: str


# Global cache - loaded at startup
_hscode_master_cache: list[HscodeMasterEntry] = []
_cache_loaded: bool = False


# =============================================================================
# Normalization Functions (same as mida_matcher.py)
# =============================================================================

def normalize_text(text: str) -> str:
    """
    Normalize text for matching.

    - Casefold (aggressive lowercase)
    - Strip punctuation
    - Collapse multiple spaces to single space
    - Strip leading/trailing whitespace
    - Normalize unicode characters

    Args:
        text: Input text to normalize

    Returns:
        Normalized text suitable for comparison
    """
    if not text:
        return ""

    # Normalize unicode (NFKD decomposition)
    text = unicodedata.normalize("NFKD", text)

    # Casefold (more aggressive than lower())
    text = text.casefold()

    # Remove punctuation and special characters (keep alphanumeric and spaces)
    text = re.sub(r"[^\w\s]", " ", text)

    # Collapse multiple spaces to single space
    text = re.sub(r"\s+", " ", text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity score between two normalized texts.

    Uses token-based matching combined with sequence matching.

    Args:
        text1: First text (already normalized)
        text2: Second text (already normalized)

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not text1 or not text2:
        return 0.0

    # Exact match
    if text1 == text2:
        return 1.0

    # Token-based similarity (handles word reordering)
    tokens1 = set(text1.split())
    tokens2 = set(text2.split())

    if not tokens1 or not tokens2:
        return 0.0

    # Jaccard similarity for tokens
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    token_similarity = intersection / union if union > 0 else 0.0

    # Sequence-based similarity (handles partial matches)
    sequence_similarity = SequenceMatcher(None, text1, text2).ratio()

    # Combined score (weighted average)
    combined = (token_similarity * 0.4) + (sequence_similarity * 0.6)

    return combined


# =============================================================================
# Cache Management
# =============================================================================

def load_cache_from_db(db: Session) -> None:
    """
    Load HSCODE master data from database into in-memory cache.
    
    Should be called at application startup after database is ready.
    
    Args:
        db: Database session
    """
    global _hscode_master_cache, _cache_loaded
    
    entries = db.execute(select(HscodeMaster)).scalars().all()
    
    _hscode_master_cache = [
        HscodeMasterEntry(
            part_name=entry.part_name,
            part_name_normalized=normalize_text(entry.part_name),
            hs_code=entry.hs_code,
            uom=entry.uom,
        )
        for entry in entries
    ]
    
    _cache_loaded = True
    print(f"HSCODE Master cache loaded: {len(_hscode_master_cache)} entries")


def clear_cache() -> None:
    """Clear the in-memory cache."""
    global _hscode_master_cache, _cache_loaded
    _hscode_master_cache = []
    _cache_loaded = False


def is_cache_loaded() -> bool:
    """Check if cache is loaded."""
    return _cache_loaded


def get_cache_size() -> int:
    """Get number of entries in cache."""
    return len(_hscode_master_cache)


# =============================================================================
# Lookup Functions
# =============================================================================

@dataclass
class PartNameLookupResult:
    """Result of a part name lookup."""
    part_name: str
    hs_code: str
    uom: str
    match_score: float
    is_exact_match: bool


def lookup_by_part_name(
    description: str,
    fuzzy_threshold: float = 0.85,
    db: Optional[Session] = None,
) -> Optional[PartNameLookupResult]:
    """
    Look up HSCODE and UOM by matching part name.
    
    First attempts exact match, then fuzzy match with threshold.
    
    Args:
        description: Item description/name to match
        fuzzy_threshold: Minimum similarity score for fuzzy matching (default 0.85)
        db: Optional database session (used to load cache if not loaded)
        
    Returns:
        PartNameLookupResult if found, None if no match
    """
    global _hscode_master_cache, _cache_loaded
    
    # Load cache from DB if not loaded and db session provided
    if not _cache_loaded and db is not None:
        load_cache_from_db(db)
    
    if not _hscode_master_cache:
        return None
    
    # Normalize input
    normalized_desc = normalize_text(description)
    
    if not normalized_desc:
        return None
    
    # 1. Try exact match first
    for entry in _hscode_master_cache:
        if entry.part_name_normalized == normalized_desc:
            return PartNameLookupResult(
                part_name=entry.part_name,
                hs_code=entry.hs_code,
                uom=entry.uom,
                match_score=1.0,
                is_exact_match=True,
            )
    
    # 2. Try fuzzy match
    best_match: Optional[HscodeMasterEntry] = None
    best_score: float = 0.0
    
    for entry in _hscode_master_cache:
        score = calculate_similarity(normalized_desc, entry.part_name_normalized)
        
        if score >= fuzzy_threshold and score > best_score:
            best_score = score
            best_match = entry
    
    if best_match is not None:
        return PartNameLookupResult(
            part_name=best_match.part_name,
            hs_code=best_match.hs_code,
            uom=best_match.uom,
            match_score=best_score,
            is_exact_match=False,
        )
    
    return None


# =============================================================================
# Database Seeding
# =============================================================================

def seed_hscode_master_data(db: Session, csv_path: Optional[Path] = None) -> dict:
    """
    Seed HSCODE master data from CSV file into database.
    
    Uses upsert to avoid duplicates if re-seeding.
    
    Args:
        db: Database session
        csv_path: Path to CSV file (defaults to server/hscode_master.csv)
        
    Returns:
        Dictionary with seeding statistics
    """
    if csv_path is None:
        # Default path relative to server directory
        csv_path = Path(__file__).parent.parent.parent / "hscode_master.csv"
    
    if not csv_path.exists():
        raise FileNotFoundError(f"HSCODE master CSV not found: {csv_path}")
    
    stats = {
        "total_rows": 0,
        "inserted": 0,
        "skipped": 0,
    }
    
    # Read CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    stats["total_rows"] = len(rows)
    
    # Clear existing data
    db.execute(HscodeMaster.__table__.delete())
    
    # Insert new data
    for row in rows:
        part_name = row.get("Part Name", "").strip()
        hs_code = row.get("HSCODE", "").strip()
        uom = row.get("UOM", "").strip()
        
        if not part_name or not hs_code:
            stats["skipped"] += 1
            continue
        
        entry = HscodeMaster(
            id=uuid.uuid4(),
            part_name=part_name,
            hs_code=hs_code,
            uom=uom,
        )
        db.add(entry)
        stats["inserted"] += 1
    
    db.commit()
    
    # Reload cache after seeding
    clear_cache()
    load_cache_from_db(db)
    
    return stats


def get_hscode_master_count(db: Session) -> int:
    """Get count of HSCODE master entries in database."""
    result = db.execute(select(func.count()).select_from(HscodeMaster))
    return result.scalar() or 0
