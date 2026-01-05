"""
Request/Response schemas for the MIDA converter endpoint.

The converter endpoint handles:
1. Invoice file upload (Excel/CSV)
2. Optional MIDA certificate matching mode

Flow for MIDA matching mode:
1. Parse uploaded invoice file
2. Extract invoice items (non-flagged items only)
3. Lookup the specified MIDA certificate by certificate_number
4. Match invoice items against MIDA certificate items using fuzzy/exact matching
5. Return matched items with remaining quantities and any warnings

This allows users to verify that their invoice items are covered by
their MIDA exemption certificate before submitting customs declarations.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MatchMode(str, Enum):
    """Mode for matching invoice items to MIDA certificate items."""

    exact = "exact"
    fuzzy = "fuzzy"


class WarningSeverity(str, Enum):
    """Severity level for conversion warnings."""

    info = "info"
    warning = "warning"
    error = "error"


class ConversionWarning(BaseModel):
    """A warning generated during the conversion process."""

    invoice_item: str = Field(..., description="Description of the invoice item that triggered the warning")
    reason: str = Field(..., description="Reason for the warning")
    severity: WarningSeverity = Field(
        default=WarningSeverity.warning, description="Severity level of the warning"
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class InvoiceItemBase(BaseModel):
    """Base schema for invoice items extracted from uploaded file."""

    line_no: int = Field(..., description="Line number in the invoice (from Item column)")
    hs_code: str = Field(default="", description="HS tariff code")
    description: str = Field(..., description="Item description (from Parts Name column)")
    quantity: Decimal = Field(..., ge=0, description="Invoice quantity")
    uom: str = Field(default="UNT", description="Unit of measure")
    amount: Optional[Decimal] = Field(default=None, description="Amount in USD")
    net_weight_kg: Optional[Decimal] = Field(default=None, description="Net weight in KG")
    parts_no: Optional[str] = Field(default=None, description="Parts number")
    invoice_no: Optional[str] = Field(default=None, description="Invoice number reference")
    model_no: Optional[str] = Field(default=None, description="Model number (for MIDA matching)")

    model_config = ConfigDict(str_strip_whitespace=True)


class MidaMatchedItem(InvoiceItemBase):
    """
    Invoice item that has been matched to a MIDA certificate line.

    Extends InvoiceItemBase with MIDA-specific matching information.
    """

    mida_item_id: Optional[str] = Field(default=None, description="UUID of the matched MIDA certificate item")
    mida_certificate_id: Optional[str] = Field(default=None, description="UUID of the matched MIDA certificate")
    mida_certificate_number: Optional[str] = Field(default=None, description="Certificate number of the matched MIDA certificate")
    mida_line_no: int = Field(..., description="Matching MIDA certificate line number")
    mida_hs_code: str = Field(..., description="HS code from MIDA certificate")
    mida_item_name: str = Field(..., description="Item name from MIDA certificate")
    remaining_qty: Decimal = Field(..., description="Remaining quantity on MIDA certificate")
    remaining_uom: str = Field(..., description="Unit of measure for remaining quantity")
    match_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Match confidence score (1.0 = exact match)"
    )
    approved_qty: Decimal = Field(..., description="Original approved quantity on MIDA certificate")
    
    # HSCODE-based UOM for balance deduction
    hscode_uom: Optional[str] = Field(
        default=None,
        description="UOM determined by HSCODE mapping table (UNIT or KGM). "
                    "If UNIT, use quantity for balance deduction. "
                    "If KGM, use net_weight_kg for balance deduction."
    )
    deduction_quantity: Optional[Decimal] = Field(
        default=None,
        description="The quantity to deduct from balance, calculated based on hscode_uom. "
                    "For UNIT: uses invoice quantity. For KGM: uses net_weight_kg."
    )


class ConvertRequest(BaseModel):
    """
    Request parameters for the convert endpoint.

    Note: The file is uploaded as multipart form data, not in the JSON body.
    This schema represents the additional parameters.
    """

    mida_certificate_number: str = Field(
        ...,
        min_length=1,
        description="MIDA certificate number for matching (required for MIDA mode)"
    )
    match_mode: MatchMode = Field(
        default=MatchMode.fuzzy,
        description="Matching mode: 'exact' or 'fuzzy'"
    )
    match_threshold: float = Field(
        default=0.88,
        ge=0.0,
        le=1.0,
        description="Minimum match score for fuzzy matching (0.0-1.0)"
    )

    @field_validator("mida_certificate_number")
    @classmethod
    def certificate_number_not_empty(cls, v: str) -> str:
        """Validate that certificate number is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("mida_certificate_number cannot be empty")
        return v.strip()


class ConvertResponse(BaseModel):
    """
    Response from the convert endpoint.

    Supports two modes:
    - Normal mode: Returns all_invoice_items without MIDA matching
    - MIDA mode: Returns mida_matched_items with MIDA certificate details

    Contains:
    - The MIDA certificate number used for matching (empty string if normal mode)
    - List of matched items with MIDA certificate details (MIDA mode)
    - List of all invoice items (normal mode)
    - Any warnings (e.g., quantity limits, unmatched items)
    - Summary statistics
    """

    # MIDA matching mode fields
    mida_certificate_number: str = Field(
        ..., description="The MIDA certificate number used for matching (empty if normal mode)"
    )
    mida_matched_items: list[MidaMatchedItem] = Field(
        default_factory=list,
        description="Invoice items matched to MIDA certificate lines (MIDA mode)"
    )
    warnings: list[ConversionWarning] = Field(
        default_factory=list,
        description="Warnings generated during processing"
    )

    # Normal mode fields
    all_invoice_items: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Filtered invoice items (non-FORM-D only, normal mode)"
    )
    full_invoice_items: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="All invoice items including FORM-D flagged items and Total row"
    )

    # Summary statistics
    total_invoice_items: int = Field(
        default=0, description="Total number of items in the uploaded invoice (including FORM-D)"
    )
    filtered_item_count: int = Field(
        default=0, description="Number of items after filtering (non-FORM-D only)"
    )
    form_d_item_count: int = Field(
        default=0, description="Number of FORM-D items excluded from filtered view"
    )
    matched_item_count: int = Field(
        default=0, description="Number of items successfully matched to MIDA"
    )
    unmatched_item_count: int = Field(
        default=0, description="Number of items that could not be matched"
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class ConvertErrorDetail(BaseModel):
    """Detailed error information for failed conversions."""

    error: str = Field(..., description="Error type identifier")
    detail: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(default=None, description="Field that caused the error")


class MidaExportItem(BaseModel):
    """Item for MIDA K1 export - uses MIDA certificate HS code instead of invoice HS code."""

    hs_code: str = Field(..., description="HS code from MIDA certificate")
    description: str = Field(..., description="Item description")
    quantity: Decimal = Field(..., ge=0, description="Invoice quantity")
    uom: str = Field(default="UNT", description="Unit of measure")
    amount: Optional[Decimal] = Field(default=None, description="Amount in USD")
    net_weight_kg: Optional[Decimal] = Field(default=None, description="Net weight in KG")

    model_config = ConfigDict(str_strip_whitespace=True)


class MidaExportRequest(BaseModel):
    """Request body for MIDA K1 XLS export."""

    items: list[MidaExportItem] = Field(..., min_length=1, description="List of items to export")
    country: str = Field(default="MY", description="Country of origin code")

    model_config = ConfigDict(str_strip_whitespace=True)
