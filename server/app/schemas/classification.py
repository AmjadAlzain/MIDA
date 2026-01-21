"""
Schemas for Invoice Classification API.

The classification endpoint handles:
1. Invoice file upload (Excel/CSV)
2. Company selection (mandatory)
3. Optional MIDA certificate selection for matching
4. Country, port, and date metadata

The response contains 3 classified item lists:
- Form-D items: Items with Form-D flag (and for HICOM, dual-flagged items)
- MIDA items: Items matched to MIDA certificates (and for Hong Leong, dual-flagged items)
- Duties Payable items: Items that are neither Form-D nor MIDA matched
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExportType(str, Enum):
    """Type of K1 export - determines duty/SST column handling."""

    form_d = "form_d"
    mida = "mida"
    duties_payable = "duties_payable"


class ItemTable(str, Enum):
    """Which table an item belongs to."""

    form_d = "form_d"
    mida = "mida"
    duties_payable = "duties_payable"


class ClassifiedItem(BaseModel):
    """
    An invoice item that has been classified into one of the 3 tables.
    
    Contains both the original invoice item data and classification metadata.
    """

    # Original invoice fields
    line_no: int = Field(..., description="Line number in the invoice")
    hs_code: str = Field(default="", description="HS tariff code from invoice")
    description: str = Field(..., description="Item description (Parts Name)")
    quantity: Decimal = Field(..., ge=0, description="Invoice quantity")
    uom: str = Field(default="", description="Unit of measure from HSCODE_UOM lookup (may be empty if not found)")
    amount: Optional[Decimal] = Field(default=None, description="Amount in USD")
    net_weight_kg: Optional[Decimal] = Field(default=None, description="Net weight in KG")
    parts_no: Optional[str] = Field(default=None, description="Parts number")
    invoice_no: Optional[str] = Field(default=None, description="Invoice number reference")
    model_no: Optional[str] = Field(default=None, description="Model number")
    
    # Form-D flag from invoice (original value)
    form_flag: str = Field(default="", description="Form flag from invoice (e.g., 'FORM-D' or '')")
    
    # MIDA matching fields (only populated if MIDA matched)
    mida_matched: bool = Field(default=False, description="Whether item was matched to MIDA certificate")
    mida_item_id: Optional[str] = Field(default=None, description="UUID of matched MIDA certificate item")
    mida_certificate_id: Optional[str] = Field(default=None, description="UUID of matched MIDA certificate")
    mida_certificate_number: Optional[str] = Field(default=None, description="Certificate number")
    mida_line_no: Optional[int] = Field(default=None, description="MIDA certificate line number")
    mida_hs_code: Optional[str] = Field(default=None, description="HS code from MIDA certificate")
    mida_item_name: Optional[str] = Field(default=None, description="Item name from MIDA certificate")
    remaining_qty: Optional[Decimal] = Field(default=None, description="Remaining quantity on MIDA certificate (Total)")
    remaining_uom: Optional[str] = Field(default=None, description="UOM for remaining quantity")
    
    # Port-specific remaining balances
    remaining_port_klang: Optional[Decimal] = Field(default=None, description="Remaining quantity for Port Klang")
    remaining_klia: Optional[Decimal] = Field(default=None, description="Remaining quantity for KLIA")
    remaining_bukit_kayu_hitam: Optional[Decimal] = Field(default=None, description="Remaining quantity for Bukit Kayu Hitam")
    port_specific_remaining: Optional[Decimal] = Field(default=None, description="Remaining quantity for the selected port")

    match_score: Optional[float] = Field(default=None, description="Match confidence score (0-1)")
    approved_qty: Optional[Decimal] = Field(default=None, description="Original approved quantity")
    hscode_uom: Optional[str] = Field(default=None, description="UOM from HSCODE mapping (UNIT or KGM)")
    deduction_quantity: Optional[Decimal] = Field(default=None, description="Quantity to deduct from balance")
    
    # Classification fields
    original_table: ItemTable = Field(..., description="Table item was originally assigned to based on rules")
    current_table: ItemTable = Field(..., description="Current table (may differ if manually moved)")
    
    # SST exemption status
    sst_exempted: bool = Field(..., description="Whether SST is exempted for this item")
    sst_exempted_default: bool = Field(..., description="Default SST exemption value based on company rules")
    
    # Manual modification flags
    manually_moved: bool = Field(default=False, description="Whether item was manually moved from original table")
    sst_manually_changed: bool = Field(default=False, description="Whether SST status was manually changed")

    model_config = ConfigDict(str_strip_whitespace=True)


class CompanyOut(BaseModel):
    """Company information for API response."""

    id: UUID
    name: str
    sst_default_behavior: str = Field(
        ..., description="SST default behavior: 'all_on' or 'mida_only'"
    )
    dual_flag_routing: str = Field(
        ..., description="Dual flag routing: 'form_d' or 'mida'"
    )

    model_config = ConfigDict(from_attributes=True)


class ClassifyResponse(BaseModel):
    """
    Response from the classify endpoint.
    
    Contains 3 lists of classified items plus metadata for the frontend.
    """

    # Company info
    company: CompanyOut
    
    # Metadata from form
    country: str = Field(..., description="Country of origin code")
    port: str = Field(..., description="Import port")
    import_date: Optional[date] = Field(default=None, description="Import date")
    
    # Classified item lists
    form_d_items: list[ClassifiedItem] = Field(
        default_factory=list, description="Items in Form-D table"
    )
    mida_items: list[ClassifiedItem] = Field(
        default_factory=list, description="Items in MIDA table"
    )
    duties_payable_items: list[ClassifiedItem] = Field(
        default_factory=list, description="Items in Duties Payable table"
    )
    
    # Summary statistics
    total_items: int = Field(default=0, description="Total number of items in invoice")
    form_d_count: int = Field(default=0, description="Number of Form-D items")
    mida_count: int = Field(default=0, description="Number of MIDA items")
    duties_payable_count: int = Field(default=0, description="Number of Duties Payable items")
    
    # Warnings from processing
    warnings: list[dict[str, Any]] = Field(
        default_factory=list, description="Warnings generated during classification"
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class K1ExportItem(BaseModel):
    """Item for K1 export with all necessary fields."""

    # Core fields for K1 template
    hs_code: str = Field(..., description="HS code (with '00' suffix appended)")
    description: str = Field(..., description="Item description (Parts Name)")
    description2: str = Field(default="", description="Secondary description (Quantity)")
    quantity: Decimal = Field(..., ge=0, description="Quantity for StatisticalQty/DeclaredQty")
    uom: str = Field(default="", description="UOM from HSCODE_UOM lookup (KGM or UNIT, may be empty)")
    amount: Optional[Decimal] = Field(default=None, description="Amount in USD")
    net_weight_kg: Optional[Decimal] = Field(default=None, description="Net weight in KG")
    
    # SST exemption status for this item
    sst_exempted: bool = Field(..., description="Whether SST is exempted for this item")

    model_config = ConfigDict(str_strip_whitespace=True)


class K1ExportRequest(BaseModel):
    """Request body for K1 XLS export."""

    items: list[K1ExportItem] = Field(..., min_length=1, description="List of items to export")
    export_type: ExportType = Field(..., description="Type of export (form_d, mida, duties_payable)")
    country: str = Field(default="MY", description="Country of origin code")

    model_config = ConfigDict(str_strip_whitespace=True)
