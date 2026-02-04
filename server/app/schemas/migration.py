"""
Pydantic schemas for MIDA Balance Sheet Migration API.

These schemas define the request/response models for uploading historical
balance sheet data from XLSX files and reconciling with existing certificates.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ItemMatchStatus(str, Enum):
    """Status of item matching between XLSX and database."""
    MATCHED = "matched"
    NAME_MISMATCH = "name_mismatch"
    NOT_FOUND = "not_found"


class ConflictResolution(str, Enum):
    """User's choice for handling item name mismatches."""
    RENAME_DB = "rename_db"  # Update DB item name to match XLSX
    KEEP_DB_NAME = "keep_db_name"  # Keep DB name, apply XLSX data
    SKIP = "skip"  # Skip this item entirely


class ImportPort(str, Enum):
    """Available import ports/stations."""
    PORT_KLANG = "port_klang"
    KLIA = "klia"
    BUKIT_KAYU_HITAM = "bukit_kayu_hitam"


# =============================================================================
# Invoice Row Schema (from XLSX)
# =============================================================================

class MigrationInvoiceRow(BaseModel):
    """Single invoice row parsed from XLSX balance sheet."""
    
    import_date: date = Field(..., description="Date of the import")
    form_reg_no: str = Field(..., description="Declaration form registration number (NO DAFTAR BORANG IKRAR)")
    balance_before: Decimal = Field(..., description="Balance before this import (BAKI DI BAWA KEHADAPAN)")
    quantity_imported: Decimal = Field(..., description="Quantity imported (KUANTITI)")
    balance_after: Decimal = Field(..., description="Balance after this import (BAKI)")
    
    model_config = ConfigDict(str_strip_whitespace=True)


# =============================================================================
# Item Preview Schema
# =============================================================================

class MigrationItemPreview(BaseModel):
    """Preview of a single item from the XLSX, with matching status."""
    
    # XLSX data
    sheet_name: str = Field(..., description="Name of the sheet in XLSX")
    line_no: int = Field(..., description="Item line number parsed from XLSX")
    xlsx_item_name: str = Field(..., description="Item name from XLSX")
    xlsx_approved_qty: Decimal = Field(..., description="Approved quantity from XLSX header")
    invoice_count: int = Field(..., description="Number of invoice rows in this sheet")
    
    # Matching status
    status: ItemMatchStatus = Field(..., description="Match status against database")
    
    # Database item (if found)
    db_item_id: Optional[UUID] = Field(default=None, description="Database item ID if matched")
    db_item_name: Optional[str] = Field(default=None, description="Item name in database")
    db_approved_qty: Optional[Decimal] = Field(default=None, description="Approved quantity in database")
    
    # Duplicates detection
    duplicate_invoices: list[str] = Field(
        default_factory=list,
        description="List of invoice numbers that already exist in database"
    )
    
    # User resolution (populated in apply request)
    resolution: Optional[ConflictResolution] = Field(
        default=None,
        description="User's choice for handling mismatch (only for name_mismatch status)"
    )
    
    # Invoice data (included in preview response)
    invoices: list[MigrationInvoiceRow] = Field(
        default_factory=list,
        description="Invoice rows parsed from XLSX"
    )
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Preview Response
# =============================================================================

class MigrationPreviewResponse(BaseModel):
    """Response from migration preview endpoint."""
    
    # Certificate info extracted from XLSX
    xlsx_certificate_number: str = Field(..., description="Certificate number extracted from XLSX")
    xlsx_company_name: Optional[str] = Field(default=None, description="Company name extracted from XLSX")
    xlsx_exemption_date: Optional[str] = Field(default=None, description="Exemption date string from XLSX")
    xlsx_validity_period: Optional[str] = Field(default=None, description="Validity period string from XLSX")
    
    # Database certificate (if found)
    db_certificate_id: Optional[UUID] = Field(default=None, description="Database certificate ID if found")
    db_certificate_number: Optional[str] = Field(default=None, description="Certificate number in database")
    certificate_found: bool = Field(..., description="Whether certificate was found in database")
    
    # Port selected by user
    port: ImportPort = Field(..., description="Import port selected by user")
    
    # Items preview
    items: list[MigrationItemPreview] = Field(..., description="List of items with matching status")
    
    # Summary counts
    total_items: int = Field(..., description="Total number of items in XLSX")
    matched_count: int = Field(..., description="Number of items matched perfectly")
    mismatch_count: int = Field(..., description="Number of items with name mismatches")
    not_found_count: int = Field(..., description="Number of items not found in database")
    total_invoices: int = Field(..., description="Total invoice rows across all items")
    total_duplicates: int = Field(..., description="Total duplicate invoices found")
    
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Apply Request
# =============================================================================

class ItemResolution(BaseModel):
    """User's resolution for a single item."""
    
    line_no: int = Field(..., description="Item line number")
    resolution: ConflictResolution = Field(..., description="How to handle this item")
    
    model_config = ConfigDict(str_strip_whitespace=True)


class MigrationApplyRequest(BaseModel):
    """Request to apply migration with user resolutions."""
    
    certificate_id: UUID = Field(..., description="Database certificate ID")
    port: ImportPort = Field(..., description="Import port for all records")
    
    # Item resolutions (only needed for name_mismatch items)
    resolutions: list[ItemResolution] = Field(
        default_factory=list,
        description="User resolutions for items with name mismatches"
    )
    
    # The preview data (to avoid re-parsing file)
    items: list[MigrationItemPreview] = Field(
        ...,
        description="Items from preview response with invoices included"
    )
    
    model_config = ConfigDict(str_strip_whitespace=True)


# =============================================================================
# Apply Response
# =============================================================================

class MigrationApplyResult(BaseModel):
    """Result of applying migration for a single item."""
    
    line_no: int = Field(..., description="Item line number")
    item_name: str = Field(..., description="Item name (after any rename)")
    status: str = Field(..., description="Result status: success, skipped, error")
    records_created: int = Field(default=0, description="Number of import records created")
    duplicates_skipped: int = Field(default=0, description="Number of duplicate invoices skipped")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    name_updated: bool = Field(default=False, description="Whether item name was updated")
    
    model_config = ConfigDict(from_attributes=True)


class MigrationApplyResponse(BaseModel):
    """Response from migration apply endpoint."""
    
    success: bool = Field(..., description="Whether overall migration succeeded")
    
    # Results per item
    results: list[MigrationApplyResult] = Field(..., description="Results for each item")
    
    # Summary
    total_items_processed: int = Field(..., description="Total items processed")
    total_records_created: int = Field(..., description="Total import records created")
    total_duplicates_skipped: int = Field(..., description="Total duplicates skipped")
    items_skipped: int = Field(..., description="Items skipped by user choice")
    items_failed: int = Field(..., description="Items that failed")
    
    # Flagged duplicates for manual review
    flagged_duplicates: list[dict] = Field(
        default_factory=list,
        description="List of duplicate invoices for manual review"
    )
    
    model_config = ConfigDict(from_attributes=True)
