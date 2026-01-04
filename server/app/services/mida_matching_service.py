"""
MIDA Matching Service.

This service handles the core logic for matching invoice items to MIDA certificate items.

Workflow (non-flagged → match to MIDA → output):
-------------------------------------------------
1. Parse the uploaded invoice file (Excel/CSV)
2. Extract all invoice items (we use non-flagged items, unlike Form-D which filters by "Form D" flag)
3. Lookup the MIDA certificate by certificate_number from the database
4. For each invoice item:
   a. Find matching MIDA certificate line(s) based on HS code and/or description
   b. Use fuzzy or exact matching based on match_mode
   c. Check if remaining quantity on certificate is sufficient
   d. Generate warnings for:
      - Insufficient remaining quantity
      - No matching MIDA line found
      - Multiple possible matches (ambiguous)
5. Return matched items with MIDA line details and remaining quantities

Matching Strategy:
------------------
- Exact mode: HS codes must match exactly (normalized to remove formatting)
- Fuzzy mode: Uses difflib SequenceMatcher for description similarity
  - First attempts HS code match (normalized)
  - If multiple HS code matches, uses description similarity to pick best
  - Falls back to description-only matching if no HS code match
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from io import BytesIO
from typing import Optional

import pandas as pd

from app.models.mida_certificate import MidaCertificate, MidaCertificateItem
from app.schemas.convert import (
    ConversionWarning,
    InvoiceItemBase,
    MatchMode,
    MidaMatchedItem,
    WarningSeverity,
)


@dataclass
class MatchResult:
    """Result of matching an invoice item to MIDA certificate items."""

    invoice_item: InvoiceItemBase
    mida_item: Optional[MidaCertificateItem]
    match_score: float
    warning: Optional[ConversionWarning] = None


@dataclass
class InvoiceTotals:
    """Totals detected from invoice file (from Total row) and calculated from items."""
    
    # Detected totals from the "Total" row in the invoice (None if no Total row found)
    detected_quantity: Optional[Decimal] = None
    detected_amount: Optional[Decimal] = None
    detected_net_weight: Optional[Decimal] = None
    
    # Calculated totals from summing all parsed items
    calculated_quantity: Decimal = Decimal(0)
    calculated_amount: Decimal = Decimal(0)
    calculated_net_weight: Decimal = Decimal(0)
    
    # Whether a Total row was found
    has_total_row: bool = False


@dataclass
class ParsedInvoice:
    """Result of parsing an invoice file, including items and totals."""
    
    items: list[InvoiceItemBase]
    totals: InvoiceTotals


# Column name variations for parsing invoice files
# Based on actual invoice format: Item, Invoice No, Product Title, Model Code, Spec Code,
# Parts No, Parts Name, Net Weight(Kg), Gross Weight(Kg), Quantity, Amount(USD), Form Flag, HS Code

ITEM_NO_CANDIDATES = ["item", "item no", "itemno", "line", "line no", "lineno", "no", "#"]
INVOICE_NO_CANDIDATES = ["invoice no", "invoiceno", "invoice", "inv no", "invno"]
PRODUCT_TITLE_CANDIDATES = ["product title", "producttitle", "product"]
MODEL_CODE_CANDIDATES = ["model code", "modelcode", "model"]
MODEL_NO_CANDIDATES = ["model no", "modelno", "model number", "modelnumber", "model code", "modelcode", "model"]
SPEC_CODE_CANDIDATES = ["spec code", "speccode", "spec"]
PARTS_NO_CANDIDATES = ["parts no", "partsno", "part no", "partno", "part number", "partnumber"]
HS_CODE_CANDIDATES = [
    "hs code", "hscode", "hs-code", "hs_code", "tariff code", "tariffcode",
    "commodity code", "commoditycode",
]
DESCRIPTION_CANDIDATES = [
    "parts name", "partsname", "part name", "partname",
    "description", "item description", "itemdescription",
    "product name", "productname", "item name", "itemname",
]
QUANTITY_CANDIDATES = ["quantity", "qty", "quentity", "amount qty"]
UOM_CANDIDATES = ["uom", "unit", "unit of measure", "unitofmeasure"]
AMOUNT_CANDIDATES = ["amount", "amount(usd)", "amount (usd)", "value", "total"]
NET_WEIGHT_CANDIDATES = [
    "net weight", "netweight", "net weight(kg)", "net weight (kg)",
    "weight", "weight(kg)", "weight (kg)",
]
GROSS_WEIGHT_CANDIDATES = [
    "gross weight", "grossweight", "gross weight(kg)", "gross weight (kg)",
]
FORM_FLAG_CANDIDATES = ["form flag", "formflag", "flag", "form", "form-d flag"]


def _normalize_header(value: object) -> str:
    """Normalize a column header for matching."""
    return re.sub(r"[\s_\-()]+", "", str(value or "").strip().lower())


def _normalize_hs_code(value: object) -> str:
    """
    Normalize an HS code by extracting only digits.

    Handles various formats:
    - "1234.56.78" -> "12345678"
    - "1234 56 78" -> "12345678"
    - "1234-56-78" -> "12345678"
    """
    return re.sub(r"\D", "", str(value or ""))


def _find_column(columns: list[str], candidates: list[str]) -> Optional[str]:
    """Find the first matching column from candidates."""
    normalized_cols = {_normalize_header(c): c for c in columns}
    for candidate in candidates:
        norm_candidate = _normalize_header(candidate)
        if norm_candidate in normalized_cols:
            return normalized_cols[norm_candidate]
    return None


def _calculate_similarity(text1: str, text2: str) -> float:
    """Calculate similarity score between two strings using SequenceMatcher."""
    if not text1 or not text2:
        return 0.0
    # Normalize both strings for comparison
    norm1 = text1.lower().strip()
    norm2 = text2.lower().strip()
    return SequenceMatcher(None, norm1, norm2).ratio()


def parse_invoice_file(
    file_bytes: bytes,
    exclude_form_d_items: bool = True,
) -> ParsedInvoice:
    """
    Parse an invoice file (Excel or CSV) and extract items.

    Expected invoice format columns:
    - Item: Line number
    - Invoice No: Invoice reference
    - Product Title: Product category
    - Model Code, Spec Code: Product codes
    - Parts No: Part number
    - Parts Name: Item description (used for matching)
    - Net Weight(Kg): Net weight
    - Gross Weight(Kg): Gross weight
    - Quantity: Item quantity
    - Amount(USD): Amount in USD
    - Form Flag: "FORM-D" for Form-D items, empty for MIDA items
    - HS Code: Tariff code

    Args:
        file_bytes: Raw bytes of the uploaded file
        exclude_form_d_items: If True, exclude items with "FORM-D" flag and only
                              return items with empty form flags. Default True.

    Returns:
        List of InvoiceItemBase objects

    Raises:
        ValueError: If the file format is not supported or required columns are missing
    """
    buffer = BytesIO(file_bytes)
    buffer.seek(0)
    head = buffer.read(8)
    buffer.seek(0)

    # Detect file type by magic bytes
    # XLSX/XLSM: starts with PK (ZIP archive)
    # XLS: starts with 0xD0 0xCF 0x11 0xE0 (OLE compound document)
    is_xlsx = head.startswith(b"PK")
    is_xls = head.startswith(b"\xD0\xCF\x11\xE0")

    df = None
    last_error = None

    # Try XLSX first if detected
    if is_xlsx:
        try:
            df = pd.read_excel(buffer, engine="openpyxl")
        except Exception as e:
            last_error = e
            buffer.seek(0)

    # Try XLS if detected or XLSX failed
    if df is None and (is_xls or is_xlsx):
        try:
            df = pd.read_excel(buffer, engine="xlrd")
        except Exception as e:
            last_error = e
            buffer.seek(0)

    # Fallback: try openpyxl then xlrd for unknown formats
    if df is None and not is_xlsx and not is_xls:
        try:
            df = pd.read_excel(buffer, engine="openpyxl")
        except Exception:
            buffer.seek(0)
            try:
                df = pd.read_excel(buffer, engine="xlrd")
            except Exception as e:
                last_error = e

    if df is None:
        raise ValueError(f"Failed to parse invoice file. Make sure it's a valid Excel file (.xls or .xlsx): {last_error}")

    if df.empty:
        raise ValueError("Invoice file is empty")

    # Find columns
    columns = list(df.columns)
    item_no_col = _find_column(columns, ITEM_NO_CANDIDATES)
    invoice_no_col = _find_column(columns, INVOICE_NO_CANDIDATES)
    parts_no_col = _find_column(columns, PARTS_NO_CANDIDATES)
    model_no_col = _find_column(columns, MODEL_NO_CANDIDATES)
    hs_col = _find_column(columns, HS_CODE_CANDIDATES)
    desc_col = _find_column(columns, DESCRIPTION_CANDIDATES)
    qty_col = _find_column(columns, QUANTITY_CANDIDATES)
    uom_col = _find_column(columns, UOM_CANDIDATES)
    amount_col = _find_column(columns, AMOUNT_CANDIDATES)
    weight_col = _find_column(columns, NET_WEIGHT_CANDIDATES)
    form_flag_col = _find_column(columns, FORM_FLAG_CANDIDATES)

    # Validate required columns
    if not desc_col:
        raise ValueError("Missing required column: Parts Name or Description")
    if not qty_col:
        raise ValueError("Missing required column: Quantity")

    items: list[InvoiceItemBase] = []
    totals = InvoiceTotals()

    for idx, row in df.iterrows():
        # First, get description to check for Total row
        description = str(row.get(desc_col, "") or "").strip()
        
        # Detect "Total" row FIRST - skip it entirely, it's not a data entry
        # Total rows should not be considered when looking for items with empty form flags
        description_lower = description.lower().strip()
        if description_lower == "total" or description_lower.startswith("total:") or description_lower.startswith("grand total"):
            totals.has_total_row = True
            try:
                totals.detected_quantity = Decimal(str(row.get(qty_col, 0) or 0))
            except Exception:
                pass
            if amount_col:
                try:
                    totals.detected_amount = Decimal(str(row.get(amount_col, 0) or 0))
                except Exception:
                    pass
            if weight_col:
                try:
                    totals.detected_net_weight = Decimal(str(row.get(weight_col, 0) or 0))
                except Exception:
                    pass
            continue  # Don't process Total row as an item - skip entirely
        
        # Get form flag to filter FORM-D items
        form_flag = ""
        if form_flag_col:
            form_flag = str(row.get(form_flag_col, "") or "").strip().upper()
        
        # Skip FORM-D flagged items if filtering is enabled
        # We only want items with empty form flags (non-FORM-D items)
        if exclude_form_d_items and form_flag == "FORM-D":
            continue

        hs_code = str(row.get(hs_col, "") or "").strip() if hs_col else ""
        
        # Skip empty rows
        if not hs_code and not description:
            continue

        # Get line number from Item column or use row index
        try:
            if item_no_col:
                line_no = int(row.get(item_no_col, idx + 1) or idx + 1)
            else:
                line_no = int(idx) + 1
        except (ValueError, TypeError):
            line_no = int(idx) + 1

        try:
            quantity = Decimal(str(row.get(qty_col, 0) or 0))
        except Exception:
            quantity = Decimal(0)

        uom = str(row.get(uom_col, "UNT") or "UNT").strip() if uom_col else "UNT"

        amount = None
        if amount_col:
            try:
                amount = Decimal(str(row.get(amount_col, 0) or 0))
            except Exception:
                pass

        net_weight = None
        if weight_col:
            try:
                net_weight = Decimal(str(row.get(weight_col, 0) or 0))
            except Exception:
                pass

        # Get parts number if available
        parts_no = ""
        if parts_no_col:
            parts_no = str(row.get(parts_no_col, "") or "").strip()

        # Get invoice number if available
        invoice_no = ""
        if invoice_no_col:
            invoice_no = str(row.get(invoice_no_col, "") or "").strip()

        # Get model number if available
        model_no = ""
        if model_no_col:
            model_no = str(row.get(model_no_col, "") or "").strip()

        items.append(
            InvoiceItemBase(
                line_no=line_no,
                hs_code=hs_code,
                description=description,
                quantity=quantity,
                uom=uom,
                amount=amount,
                net_weight_kg=net_weight,
                parts_no=parts_no,
                invoice_no=invoice_no,
                model_no=model_no,
            )
        )

    if not items:
        if exclude_form_d_items:
            raise ValueError("No items with empty form flag found (all items have FORM-D flag or rows are empty)")
        raise ValueError("No valid items found in invoice file")

    # Calculate totals from parsed items for validation
    totals.calculated_quantity = sum((item.quantity for item in items), Decimal(0))
    totals.calculated_amount = sum((item.amount or Decimal(0) for item in items), Decimal(0))
    totals.calculated_net_weight = sum((item.net_weight_kg or Decimal(0) for item in items), Decimal(0))

    return ParsedInvoice(items=items, totals=totals)


def match_invoice_to_mida(
    invoice_items: list[InvoiceItemBase],
    certificate: MidaCertificate,
    match_mode: MatchMode = MatchMode.fuzzy,
    match_threshold: float = 0.88,
) -> tuple[list[MidaMatchedItem], list[ConversionWarning]]:
    """
    Match invoice items to MIDA certificate items.

    Args:
        invoice_items: List of invoice items to match
        certificate: MIDA certificate with items
        match_mode: 'exact' or 'fuzzy' matching
        match_threshold: Minimum similarity score for fuzzy matching (0.0-1.0)

    Returns:
        Tuple of (matched_items, warnings)
    """
    matched_items: list[MidaMatchedItem] = []
    warnings: list[ConversionWarning] = []

    if not certificate.items:
        warnings.append(
            ConversionWarning(
                invoice_item="<all>",
                reason=f"MIDA certificate '{certificate.certificate_number}' has no items",
                severity=WarningSeverity.error,
            )
        )
        return matched_items, warnings

    # Build lookup structures for MIDA items
    # Key: normalized HS code, Value: list of MIDA items
    mida_by_hs: dict[str, list[MidaCertificateItem]] = {}
    for item in certificate.items:
        norm_hs = _normalize_hs_code(item.hs_code)
        if norm_hs not in mida_by_hs:
            mida_by_hs[norm_hs] = []
        mida_by_hs[norm_hs].append(item)

    # Track consumed quantities for each MIDA item
    # This is a simple simulation - in production you'd track actual used quantities
    consumed_qty: dict[int, Decimal] = {}  # mida_line_no -> consumed qty

    for inv_item in invoice_items:
        norm_inv_hs = _normalize_hs_code(inv_item.hs_code)
        best_match: Optional[MidaCertificateItem] = None
        best_score: float = 0.0

        # Step 1: Try HS code matching
        if norm_inv_hs in mida_by_hs:
            candidates = mida_by_hs[norm_inv_hs]
            if len(candidates) == 1:
                best_match = candidates[0]
                best_score = 1.0  # Exact HS code match
            else:
                # Multiple candidates - use description similarity
                for mida_item in candidates:
                    score = _calculate_similarity(inv_item.description, mida_item.item_name)
                    if score > best_score:
                        best_score = score
                        best_match = mida_item
        else:
            # Step 2: Try prefix matching for HS codes
            for prefix_len in range(len(norm_inv_hs), 3, -1):
                prefix = norm_inv_hs[:prefix_len]
                for norm_hs, candidates in mida_by_hs.items():
                    if norm_hs.startswith(prefix):
                        for mida_item in candidates:
                            # HS prefix match + description similarity
                            hs_score = prefix_len / max(len(norm_inv_hs), len(norm_hs))
                            desc_score = _calculate_similarity(
                                inv_item.description, mida_item.item_name
                            )
                            # Weighted combination: HS code is more important
                            combined_score = (hs_score * 0.6) + (desc_score * 0.4)
                            if combined_score > best_score:
                                best_score = combined_score
                                best_match = mida_item
                if best_match:
                    break

        # Step 3: If no HS match and fuzzy mode, try description-only
        if not best_match and match_mode == MatchMode.fuzzy:
            for mida_item in certificate.items:
                score = _calculate_similarity(inv_item.description, mida_item.item_name)
                if score > best_score and score >= match_threshold:
                    best_score = score
                    best_match = mida_item

        # Validate match threshold
        if match_mode == MatchMode.exact and best_score < 1.0:
            best_match = None
        elif match_mode == MatchMode.fuzzy and best_score < match_threshold:
            best_match = None

        if not best_match:
            warnings.append(
                ConversionWarning(
                    invoice_item=f"Line {inv_item.line_no}: {inv_item.description[:50]}",
                    reason="No matching MIDA certificate item found",
                    severity=WarningSeverity.warning,
                )
            )
            continue

        # Calculate remaining quantity
        approved = best_match.approved_quantity or Decimal(0)
        already_consumed = consumed_qty.get(best_match.line_no, Decimal(0))
        remaining = approved - already_consumed

        # Check if quantity is sufficient
        if inv_item.quantity > remaining:
            warnings.append(
                ConversionWarning(
                    invoice_item=f"Line {inv_item.line_no}: {inv_item.description[:50]}",
                    reason=f"Insufficient remaining qty: requested {inv_item.quantity}, remaining {remaining} (approved: {approved})",
                    severity=WarningSeverity.error,
                )
            )
            # Still include the match, but with warning

        # Update consumed quantity
        consumed_qty[best_match.line_no] = already_consumed + inv_item.quantity

        # Calculate new remaining after this consumption
        new_remaining = approved - consumed_qty[best_match.line_no]
        if new_remaining < Decimal(0):
            new_remaining = Decimal(0)

        matched_items.append(
            MidaMatchedItem(
                line_no=inv_item.line_no,
                hs_code=inv_item.hs_code,
                description=inv_item.description,
                quantity=inv_item.quantity,
                uom=inv_item.uom,
                amount=inv_item.amount,
                net_weight_kg=inv_item.net_weight_kg,
                mida_line_no=best_match.line_no,
                mida_hs_code=best_match.hs_code,
                mida_item_name=best_match.item_name,
                remaining_qty=new_remaining,
                remaining_uom=best_match.uom,
                match_score=round(best_score, 4),
                approved_qty=approved,
            )
        )

        # Warn if limit reached
        if new_remaining <= Decimal(0) and inv_item.quantity > Decimal(0):
            warnings.append(
                ConversionWarning(
                    invoice_item=f"Line {inv_item.line_no}: {inv_item.description[:50]}",
                    reason=f"MIDA limit reached for line {best_match.line_no} after this item",
                    severity=WarningSeverity.info,
                )
            )

    return matched_items, warnings


def match_invoice_to_mida_from_api(
    invoice_items: list[InvoiceItemBase],
    certificate: "MidaCertificateResponse",
    match_mode: MatchMode = MatchMode.fuzzy,
    match_threshold: float = 0.88,
) -> tuple[list[MidaMatchedItem], list[ConversionWarning]]:
    """
    Match invoice items to MIDA certificate items from API response.

    This function works with MidaCertificateResponse from the MIDA API client,
    allowing the converter service to operate without direct database access.

    Args:
        invoice_items: List of invoice items to match
        certificate: MidaCertificateResponse from MIDA API client
        match_mode: 'exact' or 'fuzzy' matching
        match_threshold: Minimum similarity score for fuzzy matching (0.0-1.0)

    Returns:
        Tuple of (matched_items, warnings)
    """
    # Import here to avoid circular imports
    from app.clients.mida_client import MidaCertificateResponse, MidaCertificateItem as ApiItem

    matched_items: list[MidaMatchedItem] = []
    warnings: list[ConversionWarning] = []

    if not certificate.items:
        warnings.append(
            ConversionWarning(
                invoice_item="<all>",
                reason=f"MIDA certificate '{certificate.header.certificate_number}' has no items",
                severity=WarningSeverity.error,
            )
        )
        return matched_items, warnings

    # Build lookup structures for MIDA items
    # Key: normalized HS code, Value: list of MIDA items
    mida_by_hs: dict[str, list[ApiItem]] = {}
    for item in certificate.items:
        norm_hs = _normalize_hs_code(item.hs_code)
        if norm_hs not in mida_by_hs:
            mida_by_hs[norm_hs] = []
        mida_by_hs[norm_hs].append(item)

    # Track consumed quantities for each MIDA item
    consumed_qty: dict[int, Decimal] = {}  # mida_line_no -> consumed qty

    for inv_item in invoice_items:
        norm_inv_hs = _normalize_hs_code(inv_item.hs_code)
        best_match: Optional[ApiItem] = None
        best_score: float = 0.0

        # Step 1: Try HS code matching
        if norm_inv_hs in mida_by_hs:
            candidates = mida_by_hs[norm_inv_hs]
            if len(candidates) == 1:
                best_match = candidates[0]
                best_score = 1.0  # Exact HS code match
            else:
                # Multiple candidates - use description similarity
                for mida_item in candidates:
                    score = _calculate_similarity(inv_item.description, mida_item.item_name)
                    if score > best_score:
                        best_score = score
                        best_match = mida_item
        else:
            # Step 2: Try prefix matching for HS codes
            for prefix_len in range(len(norm_inv_hs), 3, -1):
                prefix = norm_inv_hs[:prefix_len]
                for norm_hs, candidates in mida_by_hs.items():
                    if norm_hs.startswith(prefix):
                        for mida_item in candidates:
                            # HS prefix match + description similarity
                            hs_score = prefix_len / max(len(norm_inv_hs), len(norm_hs))
                            desc_score = _calculate_similarity(
                                inv_item.description, mida_item.item_name
                            )
                            # Weighted combination: HS code is more important
                            combined_score = (hs_score * 0.6) + (desc_score * 0.4)
                            if combined_score > best_score:
                                best_score = combined_score
                                best_match = mida_item
                if best_match:
                    break

        # Step 3: If no HS match and fuzzy mode, try description-only
        if not best_match and match_mode == MatchMode.fuzzy:
            for mida_item in certificate.items:
                score = _calculate_similarity(inv_item.description, mida_item.item_name)
                if score > best_score and score >= match_threshold:
                    best_score = score
                    best_match = mida_item

        # Validate match threshold
        if match_mode == MatchMode.exact and best_score < 1.0:
            best_match = None
        elif match_mode == MatchMode.fuzzy and best_score < match_threshold:
            best_match = None

        if not best_match:
            warnings.append(
                ConversionWarning(
                    invoice_item=f"Line {inv_item.line_no}: {inv_item.description[:50]}",
                    reason="No matching MIDA certificate item found",
                    severity=WarningSeverity.warning,
                )
            )
            continue

        # Calculate remaining quantity
        approved = best_match.approved_quantity or Decimal(0)
        already_consumed = consumed_qty.get(best_match.line_no, Decimal(0))
        remaining = approved - already_consumed

        # Check if quantity is sufficient
        if inv_item.quantity > remaining:
            warnings.append(
                ConversionWarning(
                    invoice_item=f"Line {inv_item.line_no}: {inv_item.description[:50]}",
                    reason=f"Insufficient remaining qty: requested {inv_item.quantity}, remaining {remaining} (approved: {approved})",
                    severity=WarningSeverity.error,
                )
            )
            # Still include the match, but with warning

        # Update consumed quantity
        consumed_qty[best_match.line_no] = already_consumed + inv_item.quantity

        # Calculate new remaining after this consumption
        new_remaining = approved - consumed_qty[best_match.line_no]
        if new_remaining < Decimal(0):
            new_remaining = Decimal(0)

        matched_items.append(
            MidaMatchedItem(
                line_no=inv_item.line_no,
                hs_code=inv_item.hs_code,
                description=inv_item.description,
                quantity=inv_item.quantity,
                uom=inv_item.uom,
                amount=inv_item.amount,
                net_weight_kg=inv_item.net_weight_kg,
                mida_line_no=best_match.line_no,
                mida_hs_code=best_match.hs_code,
                mida_item_name=best_match.item_name,
                remaining_qty=new_remaining,
                remaining_uom=best_match.uom,
                match_score=round(best_score, 4),
                approved_qty=approved,
            )
        )

        # Warn if limit reached
        if new_remaining <= Decimal(0) and inv_item.quantity > Decimal(0):
            warnings.append(
                ConversionWarning(
                    invoice_item=f"Line {inv_item.line_no}: {inv_item.description[:50]}",
                    reason=f"MIDA limit reached for line {best_match.line_no} after this item",
                    severity=WarningSeverity.info,
                )
            )

    return matched_items, warnings
