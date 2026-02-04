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
- uom: str (e.g., "UNT", "KGM", "KGS")

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
from datetime import date
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
    # Unit/piece variants - normalized to UNT
    "unt": "UNT",
    "unit": "UNT",
    "units": "UNT",
    "pcs": "UNT",
    "pc": "UNT",
    "piece": "UNT",
    "pieces": "UNT",
    "ea": "UNT",
    "each": "UNT",
    "nos": "UNT",
    "no": "UNT",
    "number": "UNT",
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
    "UNT": {"UNT"},
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
    model_no: Optional[str] = None  # Model number for matching

    @property
    def effective_quantity(self) -> Decimal:
        """Get effective quantity based on UOM. Uses net_weight for KGM, quantity for UNT/others."""
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
    certificate_id: Optional[str] = None  # UUID of the parent certificate
    certificate_number: Optional[str] = None  # Certificate number for display
    certificate_model_number: Optional[str] = None  # Model number from the certificate
    certificate_end_date: Optional[date] = None  # Expiration date for tie-breaking
    remaining_balance: Optional[Decimal] = None  # Remaining balance for tie-breaking
    
    # Port specific remaining balances (for display)
    remaining_port_klang: Optional[Decimal] = None
    remaining_klia: Optional[Decimal] = None
    remaining_bukit_kayu_hitam: Optional[Decimal] = None

    @property
    def remaining_quantity(self) -> Decimal:
        """
        Get remaining approved quantity.

        Uses remaining_balance if set, otherwise approved_quantity.
        """
        if self.remaining_balance is not None:
            return self.remaining_balance
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
    certificate_id: Optional[str] = None  # UUID of the matched certificate
    certificate_number: Optional[str] = None  # Certificate number for display

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
    missing_model_no_count: int = 0  # Items without model number (cannot match)


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
        Normalized UOM (e.g., "UNT", "KGM", "MTR")
    """
    if not uom:
        return "UNT"  # Default to UNT

    norm = uom.strip().lower()
    if not norm:
        return "UNT"  # Default to UNT for whitespace-only input

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
    mode: MatchMode,
    threshold: float,
    remaining_qtys: Optional[dict[int, Decimal]] = None,
    exhausted_indices: Optional[set[int]] = None,
) -> tuple[Optional[int], float, bool]:
    """
    Find the best matching MIDA item for an invoice item.

    Implements sequential deduction for duplicate items:
    - When multiple MIDA items have the same name, prefer the one with the
      lowest line_no that can still cover the invoice quantity.
    - Skip items marked as exhausted (balance too low to cover any more invoices).

    Args:
        invoice_item: Invoice item to match
        mida_items: List of MIDA items
        mode: Matching mode (exact or fuzzy)
        threshold: Minimum score threshold for fuzzy matching
        remaining_qtys: Optional dict of remaining quantities by item index
        exhausted_indices: Optional set of item indices to skip (balance exhausted)

    Returns:
        Tuple of (best_match_index, score, is_exact)
        Returns (None, 0.0, False) if no match found
    """
    norm_invoice = normalize(invoice_item.item_name)

    if not norm_invoice:
        return None, 0.0, False

    if exhausted_indices is None:
        exhausted_indices = set()

    # Get invoice quantity for checking if MIDA item can cover it
    invoice_qty = invoice_item.effective_quantity

    best_idx: Optional[int] = None
    best_score: float = 0.0
    best_is_exact: bool = False

    for idx, mida_item in enumerate(mida_items):
        # Skip exhausted items
        if idx in exhausted_indices:
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

        # Check if this item has sufficient balance to cover invoice quantity
        # If not, skip it (Option B: move to next duplicate entirely)
        if remaining_qtys is not None:
            item_remaining = remaining_qtys.get(idx, Decimal(0))
            if item_remaining < invoice_qty:
                # This item can't cover the full invoice quantity, skip it
                # unless there's no other option (will be handled by fallback below)
                continue

        # Deterministic tie-breaking:
        # 1. Higher score wins
        # 2. If same score, prefer exact over fuzzy
        # 3. If same score and exactness, prefer LOWER line_no (sequential deduction)
        should_update = False

        if score > best_score:
            should_update = True
        elif score == best_score:
            if is_exact and not best_is_exact:
                should_update = True
            elif is_exact == best_is_exact:
                # Same score, same exactness - prefer lower line_no for sequential deduction
                if best_idx is not None and mida_item.line_no < mida_items[best_idx].line_no:
                    should_update = True
                elif best_idx is None:
                    should_update = True

        if should_update:
            best_idx = idx
            best_score = score
            best_is_exact = is_exact

    # Fallback: if no item with sufficient balance found, try any matching item
    # (even if balance is insufficient - will generate warning)
    if best_idx is None:
        for idx, mida_item in enumerate(mida_items):
            if idx in exhausted_indices:
                continue

            norm_mida = normalize(mida_item.item_name)
            if not norm_mida:
                continue

            if norm_invoice == norm_mida:
                score = 1.0
                is_exact = True
            elif mode == MatchMode.fuzzy:
                score = calculate_similarity(norm_invoice, norm_mida)
                is_exact = False
                if score < threshold:
                    continue
            else:
                continue

            # Accept first match by line_no order (items are already in order)
            if best_idx is None or mida_item.line_no < mida_items[best_idx].line_no:
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

    Implements sequential deduction for duplicate MIDA items:
    - When a MIDA certificate has multiple items with the same name, deduct from
      the first one (by line_no) until its balance can't cover new invoices.
    - Then move to the next duplicate entry.
    - If an item's balance is too low to cover an invoice, skip to the next duplicate.

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

    # Track remaining quantities (will be modified as we match)
    remaining_qtys: dict[int, Decimal] = {
        idx: item.remaining_quantity for idx, item in enumerate(mida_items)
    }

    # Track exhausted items (balance too low to cover any reasonable invoice)
    # Items are marked exhausted when their balance reaches 0 or becomes insufficient
    exhausted_indices: set[int] = set()

    # Track which invoice items matched to which MIDA items (for duplicate warnings)
    # Key: mida_item index, Value: list of invoice line numbers that matched it
    mida_match_tracker: dict[int, list[int]] = {}

    # Track spillover events (when invoice switches from one duplicate to another)
    # Key: normalized item name, Value: list of (from_line_no, to_line_no, invoice_line) tuples
    spillover_tracker: dict[str, list[tuple[int, int, int]]] = {}

    # Group MIDA items by normalized name for tracking duplicates
    mida_items_by_name: dict[str, list[int]] = {}
    for idx, mida_item in enumerate(mida_items):
        norm_name = normalize(mida_item.item_name)
        if norm_name not in mida_items_by_name:
            mida_items_by_name[norm_name] = []
        mida_items_by_name[norm_name].append(idx)

    # Sort each group by line_no for sequential deduction
    for name in mida_items_by_name:
        mida_items_by_name[name].sort(key=lambda idx: mida_items[idx].line_no)

    for invoice_item in invoice_items:
        best_idx, score, is_exact = find_best_match(
            invoice_item=invoice_item,
            mida_items=mida_items,
            mode=mode,
            threshold=threshold,
            remaining_qtys=remaining_qtys,
            exhausted_indices=exhausted_indices,
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

        # Track this match for duplicate detection
        invoice_line = invoice_item.line_no or 0
        if best_idx not in mida_match_tracker:
            mida_match_tracker[best_idx] = []
        mida_match_tracker[best_idx].append(invoice_line)

        # Update remaining quantity for this MIDA item
        # Use effective quantity based on UOM
        if are_uoms_compatible(invoice_item.quantity_uom, mida_item.uom):
            consumed = invoice_item.effective_quantity
            new_remaining = max(Decimal(0), remaining_qty - consumed)
            remaining_qtys[best_idx] = new_remaining

            # Check if this item is now exhausted (balance is 0 or very low)
            # Mark as exhausted so next invoice with same name goes to next duplicate
            if new_remaining <= Decimal(0):
                exhausted_indices.add(best_idx)

                # Track spillover: find if there's a next duplicate in line
                norm_name = normalize(mida_item.item_name)
                if norm_name in mida_items_by_name:
                    name_group = mida_items_by_name[norm_name]
                    current_pos = name_group.index(best_idx) if best_idx in name_group else -1
                    if current_pos >= 0 and current_pos < len(name_group) - 1:
                        # There's a next duplicate
                        next_idx = name_group[current_pos + 1]
                        next_mida = mida_items[next_idx]
                        all_warnings.append(
                            MatchWarning(
                                invoice_item=f"Line {invoice_line}: {invoice_item.item_name[:40]}",
                                mida_item=f"Line {mida_item.line_no}: {mida_item.item_name[:40]}",
                                reason="MIDA item balance exhausted, switching to next duplicate",
                                severity=WarningSeverity.info,
                                details=f"MIDA line {mida_item.line_no} balance exhausted after this deduction. "
                                f"Future matches for '{mida_item.item_name[:30]}' will use MIDA line {next_mida.line_no}.",
                            )
                        )

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

    # Add informational warnings for MIDA items matched by multiple invoice items
    for mida_idx, invoice_lines in mida_match_tracker.items():
        if len(invoice_lines) > 1:
            mida_item = mida_items[mida_idx]
            mida_desc = f"Line {mida_item.line_no}: {mida_item.item_name[:40]}"
            line_list = ", ".join(f"#{ln}" for ln in invoice_lines)
            all_warnings.append(
                MatchWarning(
                    invoice_item=f"Invoice lines {line_list}",
                    mida_item=mida_desc,
                    reason="Multiple invoice items matched same MIDA line",
                    severity=WarningSeverity.info,
                    details=f"Invoice lines {line_list} all matched to MIDA line {mida_item.line_no}. "
                    f"Balance will be deducted for each item separately.",
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


def match_items_multi_certificate(
    invoice_items: list[InvoiceItem],
    mida_items_by_cert: dict[str, list[MidaItem]],
    mode: MatchMode = MatchMode.fuzzy,
    threshold: float = 0.75,
) -> MatchingResult:
    """
    Match invoice items against multiple MIDA certificates with name+model matching.

    Matching rules:
    1. Items WITHOUT model_no in the invoice CANNOT be matched (alert user)
    2. Match by item_name AND certificate's model_number matching invoice's model_no
    3. If same item appears in multiple certificates, pick:
       a. Certificate with nearest expiration date
       b. If dates are equal, pick certificate with highest remaining balance for that item
       c. If still tied, pick alphabetically by certificate_number (deterministic)
    4. Same MIDA item can match multiple invoice items (for duplicates)

    Args:
        invoice_items: List of invoice items to match
        mida_items_by_cert: Dict mapping certificate_id to list of MidaItem
        mode: Matching mode ('exact' or 'fuzzy')
        threshold: Minimum score for fuzzy matches (0.0-1.0)

    Returns:
        MatchingResult with matches, unmatched items, and warnings
    """
    matches: list[MatchResult] = []
    unmatched: list[InvoiceItem] = []
    all_warnings: list[MatchWarning] = []
    missing_model_no_count = 0
    
    # Track remaining quantities by (cert_id, item_idx) - will be updated as we match
    remaining_qtys: dict[tuple[str, int], Decimal] = {}
    for cert_id, mida_items in mida_items_by_cert.items():
        for idx, item in enumerate(mida_items):
            remaining_qtys[(cert_id, idx)] = item.remaining_quantity

    # Track exhausted items by (cert_id, item_idx)
    exhausted_keys: set[tuple[str, int]] = set()

    # Track which invoice items matched to which MIDA items (for duplicate warnings)
    # Key: (cert_id, item_idx), Value: list of invoice line numbers that matched it
    mida_match_tracker: dict[tuple[str, int], list[int]] = {}

    # Group MIDA items by (cert_id, normalized_name) for tracking duplicates within each certificate
    mida_items_by_cert_name: dict[tuple[str, str], list[int]] = {}
    for cert_id, mida_items in mida_items_by_cert.items():
        for idx, mida_item in enumerate(mida_items):
            norm_name = normalize(mida_item.item_name)
            key = (cert_id, norm_name)
            if key not in mida_items_by_cert_name:
                mida_items_by_cert_name[key] = []
            mida_items_by_cert_name[key].append(idx)
    # Sort each group by line_no for sequential deduction
    for key in mida_items_by_cert_name:
        cert_id = key[0]
        mida_items_by_cert_name[key].sort(key=lambda idx: mida_items_by_cert[cert_id][idx].line_no)

    for invoice_item in invoice_items:
        # Rule 1: Items without model_no cannot be matched
        if not invoice_item.model_no or not invoice_item.model_no.strip():
            missing_model_no_count += 1
            unmatched.append(invoice_item)
            matches.append(
                MatchResult(
                    invoice_item=invoice_item,
                    mida_item=None,
                    match_score=0.0,
                    is_exact_match=False,
                    remaining_qty=Decimal(0),
                    warnings=[
                        MatchWarning(
                            invoice_item=f"Line {invoice_item.line_no}: {invoice_item.item_name[:40]}",
                            mida_item="",
                            reason="Missing model number",
                            severity=WarningSeverity.warning,
                            details="Invoice item has no model number and cannot be matched to MIDA certificates",
                        )
                    ],
                )
            )
            continue
        
        norm_invoice_name = normalize(invoice_item.item_name)
        norm_invoice_model = normalize(invoice_item.model_no)
        # Use only first 3 characters of model number for matching
        # (if model has less than 3 characters, use all of them)
        norm_invoice_model_prefix = norm_invoice_model[:3] if norm_invoice_model else ""
        
        # Get invoice quantity for checking if MIDA item can cover it
        invoice_qty = invoice_item.effective_quantity

        # Find all potential matches across all certificates
        # Each match is: (cert_id, item_idx, mida_item, score, is_exact)
        potential_matches: list[tuple[str, int, MidaItem, float, bool]] = []
        # Also track fallback matches (insufficient balance but still matching)
        fallback_matches: list[tuple[str, int, MidaItem, float, bool]] = []
        
        for cert_id, mida_items in mida_items_by_cert.items():
            for idx, mida_item in enumerate(mida_items):
                # Skip exhausted items
                if (cert_id, idx) in exhausted_keys:
                    continue

                # Rule 2: Certificate model_number must match invoice model_no
                # Compare only first 3 characters of model numbers
                cert_model = mida_item.certificate_model_number or ""
                norm_cert_model = normalize(cert_model)
                norm_cert_model_prefix = norm_cert_model[:3] if norm_cert_model else ""
                
                if not norm_cert_model_prefix or norm_invoice_model_prefix != norm_cert_model_prefix:
                    continue  # Model number prefix doesn't match
                
                norm_mida_name = normalize(mida_item.item_name)
                
                if not norm_mida_name:
                    continue
                
                # Check for name match
                if norm_invoice_name == norm_mida_name:
                    score = 1.0
                    is_exact = True
                elif mode == MatchMode.fuzzy:
                    score = calculate_similarity(norm_invoice_name, norm_mida_name)
                    is_exact = False
                    if score < threshold:
                        continue  # Below threshold
                else:
                    continue  # Exact mode but not an exact match
                
                # Check if this item has sufficient balance (Option B: skip if can't cover full amount)
                item_remaining = remaining_qtys.get((cert_id, idx), Decimal(0))
                if item_remaining >= invoice_qty:
                    potential_matches.append((cert_id, idx, mida_item, score, is_exact))
                else:
                    # Track as fallback in case no item has sufficient balance
                    fallback_matches.append((cert_id, idx, mida_item, score, is_exact))
        
        # Use fallback matches if no item has sufficient balance
        if not potential_matches:
            if fallback_matches:
                potential_matches = fallback_matches
            else:
                # No match found at all
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
        
        # Rule 3: Apply tie-breaking for items matching in multiple certificates
        # Sort by: (score DESC, expiration_date ASC, line_no ASC for sequential deduction, cert_number ASC)
        def sort_key(match_tuple: tuple[str, int, MidaItem, float, bool]):
            cert_id, item_idx, mida_item, score, is_exact = match_tuple
            # Expiration date: None treated as far future (9999-12-31)
            exp_date = mida_item.certificate_end_date or date(9999, 12, 31)
            cert_num = mida_item.certificate_number or ""
            
            return (
                -score,  # Higher score first (negative for ascending sort)
                exp_date,  # Nearest expiration first
                mida_item.line_no,  # Lower line_no first (sequential deduction)
                cert_num,  # Alphabetical by cert number (deterministic tie-breaker)
            )
        
        potential_matches.sort(key=sort_key)
        best_cert_id, best_idx, best_mida_item, best_score, best_is_exact = potential_matches[0]
        
        # Get remaining quantity for the best match
        remaining_qty = remaining_qtys[(best_cert_id, best_idx)]
        
        # Check for quantity warnings
        warnings = check_quantity_warnings(invoice_item, best_mida_item, remaining_qty)
        all_warnings.extend(warnings)

        # Track this match for duplicate detection
        invoice_line = invoice_item.line_no or 0
        match_key = (best_cert_id, best_idx)
        if match_key not in mida_match_tracker:
            mida_match_tracker[match_key] = []
        mida_match_tracker[match_key].append(invoice_line)
        
        # Update remaining quantity
        if are_uoms_compatible(invoice_item.quantity_uom, best_mida_item.uom):
            consumed = invoice_item.effective_quantity
            new_remaining = max(Decimal(0), remaining_qty - consumed)
            remaining_qtys[(best_cert_id, best_idx)] = new_remaining

            # Check if this item is now exhausted
            if new_remaining <= Decimal(0):
                exhausted_keys.add((best_cert_id, best_idx))

                # Track spillover: find if there's a next duplicate in this certificate
                norm_name = normalize(best_mida_item.item_name)
                group_key = (best_cert_id, norm_name)
                if group_key in mida_items_by_cert_name:
                    name_group = mida_items_by_cert_name[group_key]
                    current_pos = name_group.index(best_idx) if best_idx in name_group else -1
                    if current_pos >= 0 and current_pos < len(name_group) - 1:
                        # There's a next duplicate in this certificate
                        next_idx = name_group[current_pos + 1]
                        next_mida = mida_items_by_cert[best_cert_id][next_idx]
                        cert_num = best_mida_item.certificate_number or best_cert_id
                        all_warnings.append(
                            MatchWarning(
                                invoice_item=f"Line {invoice_item.line_no}: {invoice_item.item_name[:40]}",
                                mida_item=f"Line {best_mida_item.line_no}: {best_mida_item.item_name[:40]}",
                                reason="MIDA item balance exhausted, switching to next duplicate",
                                severity=WarningSeverity.info,
                                details=f"MIDA line {best_mida_item.line_no} (Cert: {cert_num}) balance exhausted after this deduction. "
                                f"Future matches for '{best_mida_item.item_name[:30]}' will use MIDA line {next_mida.line_no}.",
                            )
                        )
        
        matches.append(
            MatchResult(
                invoice_item=invoice_item,
                mida_item=best_mida_item,
                match_score=best_score,
                is_exact_match=best_is_exact,
                remaining_qty=remaining_qtys[(best_cert_id, best_idx)],
                warnings=warnings,
                certificate_id=best_mida_item.certificate_id,
                certificate_number=best_mida_item.certificate_number,
            )
        )

    # Add informational warnings for MIDA items matched by multiple invoice items
    for (cert_id, mida_idx), invoice_lines in mida_match_tracker.items():
        if len(invoice_lines) > 1:
            # Find the mida item to get its details
            mida_item = mida_items_by_cert[cert_id][mida_idx]
            mida_desc = f"Line {mida_item.line_no}: {mida_item.item_name[:40]}"
            line_list = ", ".join(f"#{ln}" for ln in invoice_lines)
            cert_num = mida_item.certificate_number or cert_id
            all_warnings.append(
                MatchWarning(
                    invoice_item=f"Invoice lines {line_list}",
                    mida_item=mida_desc,
                    reason="Multiple invoice items matched same MIDA line",
                    severity=WarningSeverity.info,
                    details=f"Invoice lines {line_list} all matched to MIDA line {mida_item.line_no} "
                    f"(Certificate: {cert_num}). Balance will be deducted for each item separately.",
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
        missing_model_no_count=missing_model_no_count,
    )
