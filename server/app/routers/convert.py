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
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.mida_certificate_service import get_certificate_by_number as get_cert_from_db
from app.schemas.convert import (
    ConversionWarning,
    ConvertResponse,
    InvoiceItemBase,
    MatchMode,
    MidaExportRequest,
    MidaMatchedItem,
    WarningSeverity,
)
from app.services.mida_matching_service import parse_invoice_file, ParsedInvoice, InvoiceTotals
from app.services.mida_matcher import (
    InvoiceItem as MatcherInvoiceItem,
    MidaItem as MatcherMidaItem,
    MatchMode as MatcherMatchMode,
    WarningSeverity as MatcherWarningSeverity,
    match_items,
)
from app.services.k1_export_service import generate_k1_xls

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
    db_items: list,
) -> list[MatcherMidaItem]:
    """Convert database MidaCertificateItem objects to MatcherMidaItem objects."""
    return [
        MatcherMidaItem(
            line_no=item.line_no,
            item_name=item.item_name,
            hs_code=item.hs_code,
            approved_quantity=item.approved_quantity or Decimal(0),
            uom=item.uom,
            item_id=str(item.id),  # Pass the certificate item ID as string
        )
        for item in db_items
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
    db: Session = Depends(get_db),
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
    # Always filter out FORM-D flagged items - we only want items with empty form flags
    # These are the items that need MIDA certificate matching or review
    try:
        exclude_form_d_items = True  # Always exclude FORM-D items, keep only empty form flag items
        parsed_invoice = parse_invoice_file(data, exclude_form_d_items=exclude_form_d_items)
        invoice_items = parsed_invoice.items
        
        # Also parse without filtering to get ALL items for toggle view
        parsed_full = parse_invoice_file(data, exclude_form_d_items=False)
        full_items = parsed_full.items
        # Use totals from full parse for validation (calculated from ALL items, not filtered)
        totals = parsed_full.totals
        logger.info(f"Parsed {len(invoice_items)} filtered items and {len(full_items)} full items")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION",
                "detail": str(exc),
                "field": "file",
            },
        ) from exc

    # Generate warnings for total discrepancies if a Total row was detected
    validation_warnings: list[ConversionWarning] = []
    if totals.has_total_row:
        # Check quantity discrepancy
        if totals.detected_quantity is not None and totals.detected_quantity > 0:
            diff = abs(totals.calculated_quantity - totals.detected_quantity)
            if diff > Decimal("0.01"):
                validation_warnings.append(ConversionWarning(
                    invoice_item="Total Row Validation",
                    reason=f"Quantity mismatch: calculated sum of filtered items is {totals.calculated_quantity}, but Total row shows {totals.detected_quantity} (difference: {diff}). Note: This may be expected if some items were filtered out (e.g., FORM-D items).",
                    severity=WarningSeverity.info,
                ))
        
        # Check amount discrepancy
        if totals.detected_amount is not None and totals.detected_amount > 0:
            diff = abs(totals.calculated_amount - totals.detected_amount)
            if diff > Decimal("0.01"):
                validation_warnings.append(ConversionWarning(
                    invoice_item="Total Row Validation",
                    reason=f"Amount mismatch: calculated sum of filtered items is {totals.calculated_amount:.2f}, but Total row shows {totals.detected_amount:.2f} (difference: {diff:.2f}). Note: This may be expected if some items were filtered out (e.g., FORM-D items).",
                    severity=WarningSeverity.info,
                ))
        
        # Check net weight discrepancy
        if totals.detected_net_weight is not None and totals.detected_net_weight > 0:
            diff = abs(totals.calculated_net_weight - totals.detected_net_weight)
            if diff > Decimal("0.01"):
                validation_warnings.append(ConversionWarning(
                    invoice_item="Total Row Validation",
                    reason=f"Net weight mismatch: calculated sum of filtered items is {totals.calculated_net_weight:.2f} kg, but Total row shows {totals.detected_net_weight:.2f} kg (difference: {diff:.2f} kg). Note: This may be expected if some items were filtered out (e.g., FORM-D items).",
                    severity=WarningSeverity.info,
                ))

    # ====================
    # NORMAL MODE (no MIDA certificate number)
    # ====================
    if not mida_certificate_number or not mida_certificate_number.strip():
        # Create a set of filtered item line numbers for quick lookup
        filtered_line_nos = {item.line_no for item in invoice_items}
        
        # Build full items list including FORM-D items
        full_items_list = [
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
                "form_flag": "" if item.line_no in filtered_line_nos else "FORM-D",
                "is_total_row": False,
            }
            for item in full_items
        ]
        
        # Add Total row at the end if detected
        if totals.has_total_row:
            full_items_list.append({
                "line_no": None,
                "parts_no": "",
                "invoice_no": "",
                "hs_code": "",
                "description": "Total",
                "quantity": float(totals.detected_quantity) if totals.detected_quantity else 0,
                "uom": "",
                "amount": float(totals.detected_amount) if totals.detected_amount else None,
                "net_weight_kg": float(totals.detected_net_weight) if totals.detected_net_weight else None,
                "form_flag": "",
                "is_total_row": True,
            })
        
        # Return all invoice items without MIDA matching
        return ConvertResponse(
            mida_certificate_number="",
            mida_matched_items=[],
            warnings=validation_warnings,
            total_invoice_items=len(full_items),
            filtered_item_count=len(invoice_items),
            form_d_item_count=len(full_items) - len(invoice_items),
            matched_item_count=0,
            unmatched_item_count=len(invoice_items),
            # Filtered items (non-FORM-D only)
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
            # Full items list including FORM-D and Total row
            full_invoice_items=full_items_list,
        )

    # ====================
    # MIDA MODE (with certificate number)
    # ====================
    certificate_number = mida_certificate_number.strip()

    # Fetch certificate directly from database (avoids self-calling API timeout)
    certificate = get_cert_from_db(db, certificate_number)
    if certificate is None:
        # Return 422 with "Invalid MIDA certificate number" message
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION",
                "detail": "Invalid MIDA certificate number",
                "field": "mida_certificate_number",
            },
        )

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
                        mida_item_id=match.mida_item.item_id,
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


@router.post(
    "/convert/export",
    summary="Export invoice items to K1 Import XLS",
    description="""
Upload an invoice file and export non-FORM-D items to K1 Import XLS format.

The exported XLS file uses the K1 Import Template with:
- Import Duty Method: Exemption (100%)
- SST Method: Exemption (100%)
- Country of Origin: configurable (default: MY)

Only items WITHOUT FORM-D flag are included in the export.
""",
    responses={
        200: {"description": "K1 Import XLS file"},
        422: {"description": "Validation error (invalid file, etc.)"},
        500: {"description": "Internal server error"},
    },
)
async def export_k1_xls(
    file: UploadFile = File(..., description="Invoice file (Excel or CSV)"),
    country: str = Form(default="MY", description="Country of origin code"),
) -> StreamingResponse:
    """
    Export invoice items to K1 Import XLS format.

    This endpoint processes an uploaded invoice (Excel/CSV), extracts non-FORM-D items,
    and generates a K1 Import XLS file for customs declaration.

    Args:
        file: The uploaded invoice file (Excel or CSV format)
        country: Country of origin code (default: MY)

    Returns:
        StreamingResponse with K1 Import XLS file

    Raises:
        HTTPException 422: If file is invalid
        HTTPException 500: If unexpected error occurs
    """
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

    # Parse invoice file (exclude FORM-D items)
    try:
        parsed_invoice = parse_invoice_file(data, exclude_form_d_items=True)
        invoice_items = parsed_invoice.items
        logger.info(f"Parsed {len(invoice_items)} non-FORM-D items for K1 export")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION",
                "detail": str(exc),
                "field": "file",
            },
        ) from exc

    if not invoice_items:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION",
                "detail": "No non-FORM-D items found in invoice",
                "field": "file",
            },
        )

    # Convert items to dict list for K1 export
    items_for_export = [
        {
            "hs_code": item.hs_code,
            "description": item.description,
            "quantity": item.quantity,
            "uom": item.uom,
            "amount": item.amount,
            "net_weight_kg": item.net_weight_kg,
        }
        for item in invoice_items
    ]

    try:
        # Generate K1 XLS
        xls_bytes = generate_k1_xls(items_for_export, country=country)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"mida-k1-import-{timestamp}.xls"

        return StreamingResponse(
            BytesIO(xls_bytes),
            media_type="application/vnd.ms-excel",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except Exception as exc:
        logger.error("K1 export failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="K1 export failed due to an unexpected error.",
        ) from exc


@router.post(
    "/convert/export-mida",
    summary="Export MIDA matched items to K1 Import XLS",
    description="""
Export MIDA matched items to K1 Import XLS format.

**Key Difference from /convert/export:**
This endpoint uses HS codes from the MIDA certificate, not from the invoice.
This is required for MIDA exemption declarations where the HS code must
match the certificate.

The exported XLS file uses the K1 Import Template with:
- Import Duty Method: Exemption (100%)
- SST Method: Exemption (100%)
- Country of Origin: configurable (default: MY)
- HS Code: From MIDA certificate (not invoice)
""",
    responses={
        200: {"description": "K1 Import XLS file with MIDA HS codes"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
async def export_mida_k1_xls(
    request: MidaExportRequest,
) -> StreamingResponse:
    """
    Export MIDA matched items to K1 Import XLS format.

    This endpoint accepts matched items with MIDA HS codes and generates
    a K1 Import XLS file for customs declaration.

    Args:
        request: MidaExportRequest with items and country

    Returns:
        StreamingResponse with K1 Import XLS file

    Raises:
        HTTPException 422: If request is invalid
        HTTPException 500: If unexpected error occurs
    """
    # Convert items to dict list for K1 export
    items_for_export = [
        {
            "hs_code": item.hs_code,
            "description": item.description,
            "quantity": item.quantity,
            "uom": item.uom,
            "amount": item.amount,
            "net_weight_kg": item.net_weight_kg,
        }
        for item in request.items
    ]

    try:
        # Generate K1 XLS
        xls_bytes = generate_k1_xls(items_for_export, country=request.country)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"mida-k1-import-{timestamp}.xls"

        return StreamingResponse(
            BytesIO(xls_bytes),
            media_type="application/vnd.ms-excel",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except Exception as exc:
        logger.error("MIDA K1 export failed: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail="MIDA K1 export failed due to an unexpected error.",
        ) from exc