"""
MIDA Matcher Service.

Matches invoice items to MIDA certificate items using normalized text matching.
Supports exact and fuzzy matching with configurable thresholds.

Invoice items have:
- item_name: str
- net_weight: Decimal (weight in KG)
- quantity: Decimal
- quantity_uom: str (e.g., "UNT", "KGS", "KGM")
- amount_usd: Decimal

MIDA certificate items have:
- line_no: int
- item_name: str
- hs_code: str
- approved_quantity: Decimal
- uom: str (e.g., "UNIT", "KGM", "KGS")

Matching Strategy:
------------------
1. Normalize both item names (casefold, strip punctuation, collapse spaces)
2. Try exact normalized match first (score = 1.0, is_exact = True)
3. Fall back to fuzzy match using token-based similarity
4. Apply threshold filtering
5. Deterministic tie-breaking: higher score wins, prefer exact over fuzzy

Remaining Quantity:
-------------------
Currently treats mida_item.approved_quantity as remaining.
TODO: Replace with computed remaining after import deductions.

Warning Rules:
--------------
- UOM mismatch: invoice UOM not compatible with MIDA UOM
- Exceeds remaining: invoice qty > remaining approved qty
- Near limit: invoice qty >= 90% of remaining approved qty
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional


# =============================================================================
# Constants
# =============================================================================


class MatchMode(str, Enum):
    """Matching mode for item name comparison."""

    exact = "exact"
    fuzzy = "fuzzy"


class WarningSeverity(str, Enum):
    """Severity level for matching warnings."""

    info = "info"
    warning = "warning"
    error = "error"


# UOM normalization mapping
UOM_ALIASES: dict[str, str] = {
    # Unit/piece variants
    "unt": "UNIT",
    "unit": "UNIT",
    "units": "UNIT",
    "pcs": "UNIT",
    "pc": "UNIT",
    "piece": "UNIT",
    "pieces": "UNIT",
    "ea": "UNIT",
    "each": "UNIT",
    "nos": "UNIT",
    "no": "UNIT",
    "number": "UNIT",
    # Kilogram variants
    "kgm": "KGM",
    "kgs": "KGM",
    "kg": "KGM",
    "kilogram": "KGM",
    "kilograms": "KGM",
    # Meter variants
    "mtr": "MTR",
    "m": "MTR",
    "meter": "MTR",
    "meters": "MTR",
    "metre": "MTR",
    "metres": "MTR",
    # Liter variants
    "ltr": "LTR",
    "l": "LTR",
    "liter": "LTR",
    "liters": "LTR",
    "litre": "LTR",
    "litres": "LTR",
}

# UOM compatibility groups (UOMs in same group are compatible)
UOM_COMPATIBILITY: dict[str, set[str]] = {
    "UNIT": {"UNIT"},
    "KGM": {"KGM"},
    "MTR": {"MTR"},
    "LTR": {"LTR"},
}

# Near-limit threshold (90%)
NEAR_LIMIT_THRESHOLD = Decimal("0.90")


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class InvoiceItem:
    """An item from the invoice to be matched."""

    item_name: str
    quantity: Decimal
    quantity_uom: str
    net_weight: Optional[Decimal] = None
    amount_usd: Optional[Decimal] = None
    line_no: Optional[int] = None  # Invoice line number for reference

    @property
    def effective_quantity(self) -> Decimal:
        """Get effective quantity based on UOM."""
        norm_uom = normalize_uom(self.quantity_uom)
        if norm_uom == "KGM" and self.net_weight is not None:
            return self.net_weight
        return self.quantity


@dataclass
class MidaItem:
    """A MIDA certificate line item."""

    line_no: int
    item_name: str
    hs_code: str
    approved_quantity: Decimal
    uom: str
    item_id: Optional[str] = None  # UUID of the certificate item for database updates

    @property
    def remaining_quantity(self) -> Decimal:
        """
        Get remaining approved quantity.

        TODO: Replace with computed remaining after import deductions.
        For now, returns approved_quantity as remaining.
        """
        return self.approved_quantity


@dataclass
class MatchWarning:
    """A warning generated during matching."""

    invoice_item: str
    mida_item: str
    reason: str
    severity: WarningSeverity
    details: Optional[str] = None


@dataclass
class MatchResult:
    """Result of matching a single invoice item to a MIDA item."""

    invoice_item: InvoiceItem
    mida_item: Optional[MidaItem]
    match_score: float
    is_exact_match: bool
    remaining_qty: Decimal
    warnings: list[MatchWarning] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        """Whether a match was found."""
        return self.mida_item is not None


@dataclass
class MatchingResult:
    """Complete result of matching invoice items to MIDA items."""

    matches: list[MatchResult]
    unmatched_invoice_items: list[InvoiceItem]
    warnings: list[MatchWarning]
    total_invoice_items: int
    matched_count: int
    unmatched_count: int


# =============================================================================
# Normalization Functions
# =============================================================================


def normalize(text: str) -> str:
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


def normalize_uom(uom: str) -> str:
    """
    Normalize unit of measure to standard form.

    Args:
        uom: Input UOM string

    Returns:
        Normalized UOM (e.g., "UNIT", "KGM", "MTR")
    """
    if not uom:
        return "UNIT"  # Default to UNIT

    norm = uom.strip().lower()
    if not norm:
        return "UNIT"  # Default to UNIT for whitespace-only input

    return UOM_ALIASES.get(norm, uom.strip().upper())


def are_uoms_compatible(uom1: str, uom2: str) -> bool:
    """
    Check if two UOMs are compatible for quantity comparison.

    Args:
        uom1: First UOM
        uom2: Second UOM

    Returns:
        True if UOMs are compatible, False otherwise
    """
    norm1 = normalize_uom(uom1)
    norm2 = normalize_uom(uom2)

    # Same normalized UOM = compatible
    if norm1 == norm2:
        return True

    # Check compatibility groups
    group1 = UOM_COMPATIBILITY.get(norm1, {norm1})
    group2 = UOM_COMPATIBILITY.get(norm2, {norm2})

    return bool(group1 & group2)


# =============================================================================
# Matching Functions
# =============================================================================


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity score between two normalized texts.

    Uses token-based matching combined with sequence matching for
    better handling of word reordering.

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
    # Token similarity helps with word reordering
    # Sequence similarity helps with partial matches
    combined = (token_similarity * 0.4) + (sequence_similarity * 0.6)

    return combined


def find_best_match(
    invoice_item: InvoiceItem,
    mida_items: list[MidaItem],
    used_mida_indices: set[int],
    mode: MatchMode,
    threshold: float,
) -> tuple[Optional[int], float, bool]:
    """
    Find the best matching MIDA item for an invoice item.

    Implements 1-to-1 matching by excluding already-used MIDA items.
    Uses deterministic tie-breaking: higher score wins, prefer exact.

    Args:
        invoice_item: Invoice item to match
        mida_items: List of MIDA items
        used_mida_indices: Set of already-matched MIDA item indices
        mode: Matching mode (exact or fuzzy)
        threshold: Minimum score threshold for fuzzy matching

    Returns:
        Tuple of (best_match_index, score, is_exact)
        Returns (None, 0.0, False) if no match found
    """
    norm_invoice = normalize(invoice_item.item_name)

    if not norm_invoice:
        return None, 0.0, False

    best_idx: Optional[int] = None
    best_score: float = 0.0
    best_is_exact: bool = False

    for idx, mida_item in enumerate(mida_items):
        # Skip already-used MIDA items (1-to-1 matching)
        if idx in used_mida_indices:
            continue

        norm_mida = normalize(mida_item.item_name)

        if not norm_mida:
            continue

        # Check for exact match first
        if norm_invoice == norm_mida:
            score = 1.0
            is_exact = True
        elif mode == MatchMode.fuzzy:
            score = calculate_similarity(norm_invoice, norm_mida)
            is_exact = False
        else:
            # Exact mode but not an exact match
            continue

        # Apply threshold for fuzzy matches
        if not is_exact and score < threshold:
            continue

        # Deterministic tie-breaking:
        # 1. Higher score wins
        # 2. If same score, prefer exact over fuzzy
        # 3. If still tied, prefer lower line_no (stable ordering)
        should_update = False

        if score > best_score:
            should_update = True
        elif score == best_score:
            if is_exact and not best_is_exact:
                should_update = True
            elif is_exact == best_is_exact:
                # Same score, same exactness - prefer lower line_no
                if best_idx is not None and mida_item.line_no < mida_items[best_idx].line_no:
                    should_update = True

        if should_update:
            best_idx = idx
            best_score = score
            best_is_exact = is_exact

    return best_idx, best_score, best_is_exact


def check_quantity_warnings(
    invoice_item: InvoiceItem,
    mida_item: MidaItem,
    remaining_qty: Decimal,
) -> list[MatchWarning]:
    """
    Check for quantity-related warnings.

    Warning rules:
    - UOM mismatch: invoice UOM not compatible with MIDA UOM
    - Exceeds remaining: invoice qty > remaining approved qty
    - Near limit: invoice qty >= 90% of remaining approved qty

    Args:
        invoice_item: Invoice item
        mida_item: Matched MIDA item
        remaining_qty: Remaining approved quantity

    Returns:
        List of warnings (may be empty)
    """
    warnings: list[MatchWarning] = []
    invoice_desc = f"Line {invoice_item.line_no}: {invoice_item.item_name[:40]}"
    mida_desc = f"Line {mida_item.line_no}: {mida_item.item_name[:40]}"

    invoice_uom = normalize_uom(invoice_item.quantity_uom)
    mida_uom = normalize_uom(mida_item.uom)

    # Check UOM compatibility
    if not are_uoms_compatible(invoice_uom, mida_uom):
        warnings.append(
            MatchWarning(
                invoice_item=invoice_desc,
                mida_item=mida_desc,
                reason="UOM mismatch",
                severity=WarningSeverity.warning,
                details=f"Invoice UOM '{invoice_item.quantity_uom}' ({invoice_uom}) "
                f"not compatible with MIDA UOM '{mida_item.uom}' ({mida_uom})",
            )
        )
        # Can't compare quantities if UOM mismatch
        return warnings

    # Get effective quantity for comparison
    invoice_qty = invoice_item.effective_quantity

    # Check if quantity exceeds remaining
    if remaining_qty <= Decimal(0):
        warnings.append(
            MatchWarning(
                invoice_item=invoice_desc,
                mida_item=mida_desc,
                reason="No remaining quantity",
                severity=WarningSeverity.error,
                details=f"MIDA item has no remaining approved quantity (0 {mida_uom})",
            )
        )
    elif invoice_qty > remaining_qty:
        warnings.append(
            MatchWarning(
                invoice_item=invoice_desc,
                mida_item=mida_desc,
                reason="Exceeds remaining approved quantity",
                severity=WarningSeverity.error,
                details=f"Requested {invoice_qty} {invoice_uom}, "
                f"but only {remaining_qty} {mida_uom} remaining",
            )
        )
    elif remaining_qty > Decimal(0):
        # Check near-limit warning
        usage_ratio = invoice_qty / remaining_qty
        if usage_ratio >= NEAR_LIMIT_THRESHOLD:
            percentage = int(usage_ratio * 100)
            warnings.append(
                MatchWarning(
                    invoice_item=invoice_desc,
                    mida_item=mida_desc,
                    reason="Near limit",
                    severity=WarningSeverity.info,
                    details=f"Using {percentage}% of remaining approved quantity "
                    f"({invoice_qty} of {remaining_qty} {mida_uom})",
                )
            )

    return warnings


def match_items(
    invoice_items: list[InvoiceItem],
    mida_items: list[MidaItem],
    mode: MatchMode = MatchMode.fuzzy,
    threshold: float = 0.75,
) -> MatchingResult:
    """
    Match invoice items to MIDA certificate items.

    Implements 1-to-1 matching with deterministic tie-breaking.
    Each MIDA item can only be matched once.

    Args:
        invoice_items: List of invoice items to match
        mida_items: List of MIDA certificate items
        mode: Matching mode ('exact' or 'fuzzy')
        threshold: Minimum score for fuzzy matches (0.0-1.0)

    Returns:
        MatchingResult with matches, unmatched items, and warnings
    """
    matches: list[MatchResult] = []
    unmatched: list[InvoiceItem] = []
    all_warnings: list[MatchWarning] = []
    used_mida_indices: set[int] = set()

    # Track remaining quantities (will be modified as we match)
    # TODO: Initialize from actual remaining quantities when available
    remaining_qtys: dict[int, Decimal] = {
        idx: item.remaining_quantity for idx, item in enumerate(mida_items)
    }

    for invoice_item in invoice_items:
        best_idx, score, is_exact = find_best_match(
            invoice_item=invoice_item,
            mida_items=mida_items,
            used_mida_indices=used_mida_indices,
            mode=mode,
            threshold=threshold,
        )

        if best_idx is None:
            # No match found
            unmatched.append(invoice_item)
            matches.append(
                MatchResult(
                    invoice_item=invoice_item,
                    mida_item=None,
                    match_score=0.0,
                    is_exact_match=False,
                    remaining_qty=Decimal(0),
                    warnings=[],
                )
            )
            continue

        # Found a match
        mida_item = mida_items[best_idx]
        remaining_qty = remaining_qtys[best_idx]

        # Check for quantity warnings
        warnings = check_quantity_warnings(invoice_item, mida_item, remaining_qty)
        all_warnings.extend(warnings)

        # Update remaining quantity for this MIDA item
        # Use effective quantity based on UOM
        if are_uoms_compatible(invoice_item.quantity_uom, mida_item.uom):
            consumed = invoice_item.effective_quantity
            remaining_qtys[best_idx] = max(Decimal(0), remaining_qty - consumed)

        # Mark as used (1-to-1 matching)
        used_mida_indices.add(best_idx)

        matches.append(
            MatchResult(
                invoice_item=invoice_item,
                mida_item=mida_item,
                match_score=score,
                is_exact_match=is_exact,
                remaining_qty=remaining_qtys[best_idx],
                warnings=warnings,
            )
        )

    matched_count = sum(1 for m in matches if m.matched)

    return MatchingResult(
        matches=matches,
        unmatched_invoice_items=unmatched,
        warnings=all_warnings,
        total_invoice_items=len(invoice_items),
        matched_count=matched_count,
        unmatched_count=len(unmatched),
    )
