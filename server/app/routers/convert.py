"""
MIDA Converter Router.

This router provides the /api/convert endpoint for matching invoice items
against MIDA certificate items.

Supports Two Modes:
-------------------
1. Normal Mode (mida_certificate_number not provided):
   - Parses invoice file
   - Returns all invoice items without MIDA matching

2. MIDA Mode (mida_certificate_number provided):
   - Parses invoice file to extract all items (non-flagged items)
   - Calls MIDA API to fetch the certificate (no direct DB access)
   - Matches invoice items against MIDA certificate items
   - Returns only matched items with MIDA details and warnings

MIDA Matching Flow:
-------------------
1. User uploads an invoice file (Excel/CSV) and provides a MIDA certificate number
2. System parses the invoice to extract all items (non-flagged items)
3. System calls MIDA API to fetch the certificate (no direct DB access for portability)
4. Each invoice item is matched against MIDA certificate items:
   - By normalized description (primary matching)
   - Optional fuzzy matching with configurable threshold
5. System computes remaining quantities and generates warnings for:
   - Items with insufficient remaining quota
   - Items that couldn't be matched
   - UOM mismatches
   - Items near their MIDA limit (>=90%)
6. Response includes matched items with MIDA details and all warnings

Error Handling:
---------------
- 422 Unprocessable Entity if:
  - mida_certificate_number is empty or whitespace-only (when explicitly required)
  - MIDA certificate not found (Invalid MIDA certificate number)
  - Required file is not provided
  - File format is not supported

Architecture Note:
------------------
This converter service does NOT connect directly to MIDA's database.
Instead, it calls the MIDA API via the mida_client for portability.
IT can deploy these services separately.
"""

from __future__ import annotations

import logging
import traceback
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.clients.mida_client import (
    get_certificate_by_number as fetch_certificate_from_api,
    MidaCertificateNotFoundError,
    MidaApiError,
    MidaClientConfigError,
    MidaCertificateItem as ApiMidaItem,
)
from app.schemas.convert import (
    ConversionWarning,
    ConvertResponse,
    InvoiceItemBase,
    MatchMode,
    MidaMatchedItem,
    WarningSeverity,
)
from app.services.mida_matching_service import parse_invoice_file
from app.services.mida_matcher import (
    InvoiceItem as MatcherInvoiceItem,
    MidaItem as MatcherMidaItem,
    MatchMode as MatcherMatchMode,
    WarningSeverity as MatcherWarningSeverity,
    match_items,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _convert_to_matcher_invoice_items(
    invoice_items: list[InvoiceItemBase],
) -> list[MatcherInvoiceItem]:
    """Convert InvoiceItemBase objects to MatcherInvoiceItem objects."""
    return [
        MatcherInvoiceItem(
            line_no=item.line_no,
            item_name=item.description,  # Use description as item_name for matching
            quantity=item.quantity,
            quantity_uom=item.uom,
            net_weight=item.net_weight_kg,
            amount_usd=item.amount,
        )
        for item in invoice_items
    ]


def _convert_to_matcher_mida_items(
    api_items: list[ApiMidaItem],
) -> list[MatcherMidaItem]:
    """Convert API MidaCertificateItem objects to MatcherMidaItem objects."""
    return [
        MatcherMidaItem(
            line_no=item.line_no,
            item_name=item.item_name,
            hs_code=item.hs_code,
            approved_quantity=item.approved_quantity or Decimal(0),
            uom=item.uom,
        )
        for item in api_items
    ]


def _convert_schema_match_mode(mode: MatchMode) -> MatcherMatchMode:
    """Convert schema MatchMode to matcher MatchMode."""
    return MatcherMatchMode.exact if mode == MatchMode.exact else MatcherMatchMode.fuzzy


def _convert_matcher_severity(severity: MatcherWarningSeverity) -> WarningSeverity:
    """Convert matcher WarningSeverity to schema WarningSeverity."""
    mapping = {
        MatcherWarningSeverity.info: WarningSeverity.info,
        MatcherWarningSeverity.warning: WarningSeverity.warning,
        MatcherWarningSeverity.error: WarningSeverity.error,
    }
    return mapping.get(severity, WarningSeverity.warning)


@router.post(
    "/convert",
    response_model=ConvertResponse,
    summary="Convert invoice with optional MIDA certificate matching",
    description="""
Upload an invoice file and optionally match items against a MIDA certificate.

**Normal Mode (mida_certificate_number not provided):**
- Parse uploaded invoice file (Excel/CSV)
- Return all invoice items without MIDA matching

**MIDA Mode (mida_certificate_number provided):**
1. Parse uploaded invoice file (Excel/CSV)
2. Extract all invoice items (non-flagged items)
3. Lookup MIDA certificate by number
4. Match invoice items to certificate items
5. Return matched items with remaining quantities and warnings

**Returns 422 if:**
- mida_certificate_number is empty (when provided)
- MIDA certificate not found (Invalid MIDA certificate number)
- File is not provided or invalid format
- Required columns are missing from invoice
""",
    responses={
        200: {"description": "Successfully processed invoice"},
        422: {"description": "Validation error (empty certificate number, certificate not found, invalid file, etc.)"},
        500: {"description": "Internal server error"},
    },
)
async def convert_with_mida(
    file: UploadFile = File(..., description="Invoice file (Excel or CSV)"),
    mida_certificate_number: Optional[str] = Form(
        default=None,
        description="MIDA certificate number for matching (optional - when provided, enables MIDA mode)",
    ),
    match_mode: str = Form(
        default="fuzzy",
        description="Matching mode: 'exact' or 'fuzzy'",
    ),
    match_threshold: float = Form(
        default=0.88,
        ge=0.0,
        le=1.0,
        description="Minimum match score for fuzzy matching (0.0-1.0)",
    ),
) -> ConvertResponse:
    """
    Convert an invoice file with optional MIDA certificate matching.

    This endpoint processes an uploaded invoice (Excel/CSV), extracts items,
    and optionally matches them against the specified MIDA certificate.

    Args:
        file: The uploaded invoice file (Excel or CSV format)
        mida_certificate_number: The MIDA certificate number to match against (optional)
        match_mode: 'exact' for exact matching, 'fuzzy' for similarity-based
        match_threshold: Minimum similarity score for fuzzy matches (default 0.88)

    Returns:
        ConvertResponse with matched items and warnings

    Raises:
        HTTPException 422: If certificate number is invalid or certificate not found
        HTTPException 500: If unexpected error occurs
    """
    # Validate match_mode
    try:
        mode = MatchMode(match_mode.lower())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION",
                "detail": f"Invalid match_mode: '{match_mode}'. Must be 'exact' or 'fuzzy'",
                "field": "match_mode",
            },
        )

    # Read and validate file
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION",
                "detail": "Uploaded file is empty",
                "field": "file",
            },
        )

    # Parse invoice file
    # In MIDA mode, filter out FORM-D flagged items (only get MIDA-eligible items)
    # In normal mode, get all items
    try:
        filter_non_flagged = bool(mida_certificate_number and mida_certificate_number.strip())
        invoice_items = parse_invoice_file(data, filter_non_flagged=filter_non_flagged)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION",
                "detail": str(exc),
                "field": "file",
            },
        ) from exc

    # ====================
    # NORMAL MODE (no MIDA certificate number)
    # ====================
    if not mida_certificate_number or not mida_certificate_number.strip():
        # Return all invoice items without MIDA matching
        return ConvertResponse(
            mida_certificate_number="",
            mida_matched_items=[],
            warnings=[],
            total_invoice_items=len(invoice_items),
            matched_item_count=0,
            unmatched_item_count=len(invoice_items),
            # Include all invoice items as "all_invoice_items" for normal mode
            all_invoice_items=[
                {
                    "line_no": item.line_no,
                    "parts_no": item.parts_no or "",
                    "invoice_no": item.invoice_no or "",
                    "hs_code": item.hs_code,
                    "description": item.description,
                    "quantity": float(item.quantity),
                    "uom": item.uom,
                    "amount": float(item.amount) if item.amount else None,
                    "net_weight_kg": float(item.net_weight_kg) if item.net_weight_kg else None,
                }
                for item in invoice_items
            ],
        )

    # ====================
    # MIDA MODE (with certificate number)
    # ====================
    certificate_number = mida_certificate_number.strip()

    # Fetch certificate from MIDA API (no direct DB access for portability)
    try:
        certificate = fetch_certificate_from_api(certificate_number)
    except MidaCertificateNotFoundError:
        # Return 422 with "Invalid MIDA certificate number" message
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION",
                "detail": "Invalid MIDA certificate number",
                "field": "mida_certificate_number",
            },
        )
    except MidaClientConfigError as exc:
        logger.error("MIDA client not configured: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="MIDA API client not configured. Set MIDA_API_BASE_URL.",
        ) from exc
    except MidaApiError as exc:
        logger.error("MIDA API error: %s (status=%s)", exc.message, exc.status_code)
        raise HTTPException(
            status_code=502,
            detail=f"MIDA API error: {exc.message}",
        ) from exc

    try:
        # Check if certificate has items
        if not certificate.items:
            return ConvertResponse(
                mida_certificate_number=certificate_number,
                mida_matched_items=[],
                warnings=[
                    ConversionWarning(
                        invoice_item="<all>",
                        reason=f"MIDA certificate '{certificate_number}' has no items",
                        severity=WarningSeverity.error,
                    )
                ],
                total_invoice_items=len(invoice_items),
                matched_item_count=0,
                unmatched_item_count=len(invoice_items),
            )

        # Convert to matcher-compatible types
        matcher_invoice_items = _convert_to_matcher_invoice_items(invoice_items)
        matcher_mida_items = _convert_to_matcher_mida_items(certificate.items)
        matcher_mode = _convert_schema_match_mode(mode)

        # Perform matching using the new mida_matcher module
        matching_result = match_items(
            invoice_items=matcher_invoice_items,
            mida_items=matcher_mida_items,
            mode=matcher_mode,
            threshold=match_threshold,
        )

        # Build mida_matched_items output
        mida_matched_items: list[MidaMatchedItem] = []
        for match in matching_result.matches:
            if match.matched and match.mida_item is not None:
                # Find original invoice item for full details
                orig_item = invoice_items[match.invoice_item.line_no - 1]  # 0-based index

                mida_matched_items.append(
                    MidaMatchedItem(
                        # Original invoice fields
                        line_no=orig_item.line_no,
                        hs_code=orig_item.hs_code,
                        description=orig_item.description,
                        quantity=orig_item.quantity,
                        uom=orig_item.uom,
                        amount=orig_item.amount,
                        net_weight_kg=orig_item.net_weight_kg,
                        # MIDA matching fields
                        mida_line_no=match.mida_item.line_no,
                        mida_hs_code=match.mida_item.hs_code,
                        mida_item_name=match.mida_item.item_name,
                        remaining_qty=match.remaining_qty,
                        remaining_uom=match.mida_item.uom,
                        match_score=round(match.match_score, 4),
                        approved_qty=match.mida_item.approved_quantity,
                    )
                )

        # Convert matcher warnings to schema warnings
        warnings: list[ConversionWarning] = []
        for warning in matching_result.warnings:
            warnings.append(
                ConversionWarning(
                    invoice_item=warning.invoice_item,
                    reason=warning.reason,
                    severity=_convert_matcher_severity(warning.severity),
                )
            )

        # Add warnings for unmatched items
        for match in matching_result.matches:
            if not match.matched:
                orig_item = invoice_items[match.invoice_item.line_no - 1]
                warnings.append(
                    ConversionWarning(
                        invoice_item=f"Line {orig_item.line_no}: {orig_item.description[:50]}",
                        reason="No matching MIDA certificate item found",
                        severity=WarningSeverity.warning,
                    )
                )

        return ConvertResponse(
            mida_certificate_number=certificate_number,
            mida_matched_items=mida_matched_items,
            warnings=warnings,
            total_invoice_items=len(invoice_items),
            matched_item_count=len(mida_matched_items),
            unmatched_item_count=len(invoice_items) - len(mida_matched_items),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error during conversion: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="Conversion failed due to an unexpected error.",
        ) from exc
