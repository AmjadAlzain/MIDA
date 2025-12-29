"""
Pydantic schemas for MIDA Import Tracking API.

These schemas define the request/response models for import record operations,
balance queries, and warning status tracking.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImportPort(str, Enum):
    """Available import ports/stations."""
    PORT_KLANG = "port_klang"
    KLIA = "klia"
    BUKIT_KAYU_HITAM = "bukit_kayu_hitam"


class QuantityStatus(str, Enum):
    """Status of remaining quantity for an item."""
    NORMAL = "normal"
    WARNING = "warning"
    DEPLETED = "depleted"
    OVERDRAWN = "overdrawn"


# =============================================================================
# Import Record Schemas
# =============================================================================

class ImportRecordCreate(BaseModel):
    """Request schema for creating an import record."""

    certificate_item_id: UUID = Field(
        ..., description="UUID of the certificate item being imported"
    )
    import_date: date = Field(
        ..., description="Date of the import"
    )
    invoice_number: str = Field(
        ..., min_length=1, max_length=100, description="Invoice number"
    )
    invoice_line: Optional[int] = Field(
        default=None, ge=1, description="Line number within the invoice"
    )
    quantity_imported: Decimal = Field(
        ..., gt=0, description="Quantity imported (must be positive)"
    )
    port: ImportPort = Field(
        ..., description="Port where the import occurred"
    )
    remarks: Optional[str] = Field(
        default=None, max_length=1000, description="Optional remarks/notes"
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class ImportRecordBulkCreate(BaseModel):
    """Request schema for creating multiple import records at once."""

    records: list[ImportRecordCreate] = Field(
        ..., min_length=1, description="List of import records to create"
    )


class ImportRecordRead(BaseModel):
    """Response schema for an import record."""

    id: UUID
    certificate_item_id: UUID
    import_date: date
    invoice_number: str
    invoice_line: Optional[int] = None
    quantity_imported: Decimal
    port: str
    balance_before: Decimal
    balance_after: Decimal
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ImportRecordWithContext(ImportRecordRead):
    """Import record with certificate and item context."""

    certificate_number: str
    company_name: str
    item_hs_code: str
    item_name: str
    item_uom: str


# =============================================================================
# Item Balance Schemas
# =============================================================================

class ItemBalanceRead(BaseModel):
    """Response schema for an item's current balance status."""

    item_id: UUID
    certificate_id: UUID
    certificate_number: str
    company_name: str
    line_no: int
    hs_code: str
    item_name: str
    uom: str
    
    # Approved quantities
    approved_quantity: Optional[Decimal] = None
    port_klang_qty: Optional[Decimal] = None
    klia_qty: Optional[Decimal] = None
    bukit_kayu_hitam_qty: Optional[Decimal] = None
    
    # Remaining quantities
    remaining_quantity: Optional[Decimal] = None
    remaining_port_klang: Optional[Decimal] = None
    remaining_klia: Optional[Decimal] = None
    remaining_bukit_kayu_hitam: Optional[Decimal] = None
    
    # Calculated fields
    remaining_percentage: Optional[Decimal] = None
    total_imports: int = 0
    total_imported: Optional[Decimal] = None
    
    # Status tracking
    warning_threshold: Optional[Decimal] = None
    quantity_status: str

    model_config = ConfigDict(from_attributes=True)


class ItemBalanceUpdate(BaseModel):
    """Request schema for updating an item's warning threshold."""

    warning_threshold: Optional[Decimal] = Field(
        default=None, ge=0, description="Custom warning threshold for this item"
    )

    model_config = ConfigDict(str_strip_whitespace=True)


# =============================================================================
# Warning/Status Schemas
# =============================================================================

class ItemWarning(BaseModel):
    """Response schema for an item with warning/depleted/overdrawn status."""

    item_id: UUID
    certificate_id: UUID
    certificate_number: str
    company_name: str
    line_no: int
    hs_code: str
    item_name: str
    uom: str
    
    approved_quantity: Optional[Decimal] = None
    remaining_quantity: Optional[Decimal] = None
    
    # Port-specific remaining
    remaining_port_klang: Optional[Decimal] = None
    remaining_klia: Optional[Decimal] = None
    remaining_bukit_kayu_hitam: Optional[Decimal] = None
    
    warning_threshold: Optional[Decimal] = None
    quantity_status: str
    severity_order: int  # 1=overdrawn, 2=depleted, 3=warning

    model_config = ConfigDict(from_attributes=True)


class WarningStatusResponse(BaseModel):
    """Response schema for items with warnings."""

    items: list[ItemWarning]
    total_warnings: int
    total_depleted: int
    total_overdrawn: int


# =============================================================================
# Import History Schemas
# =============================================================================

class ImportHistoryQuery(BaseModel):
    """Query parameters for import history."""

    item_id: Optional[UUID] = Field(
        default=None, description="Filter by specific item"
    )
    port: Optional[ImportPort] = Field(
        default=None, description="Filter by specific port"
    )
    certificate_id: Optional[UUID] = Field(
        default=None, description="Filter by certificate"
    )
    invoice_number: Optional[str] = Field(
        default=None, description="Filter by invoice number"
    )
    start_date: Optional[date] = Field(
        default=None, description="Filter imports from this date"
    )
    end_date: Optional[date] = Field(
        default=None, description="Filter imports until this date"
    )


class ImportHistoryResponse(BaseModel):
    """Response schema for import history query."""

    imports: list[ImportRecordWithContext]
    total: int
    limit: int
    offset: int


# =============================================================================
# Port Summary Schemas
# =============================================================================

class PortSummary(BaseModel):
    """Summary of imports for a specific port."""

    port: str
    total_records: int
    total_quantity_imported: Decimal
    unique_items: int
    unique_certificates: int
    recent_imports: list[ImportRecordWithContext]


class PortSummaryResponse(BaseModel):
    """Response schema for all port summaries."""

    port_klang: PortSummary
    klia: PortSummary
    bukit_kayu_hitam: PortSummary
    overall_total_imports: int


# =============================================================================
# Settings Schemas
# =============================================================================

class SettingRead(BaseModel):
    """Response schema for a setting."""

    setting_key: str
    setting_value: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SettingUpdate(BaseModel):
    """Request schema for updating a setting."""

    setting_value: str = Field(
        ..., min_length=1, description="New value for the setting"
    )

    @field_validator("setting_value")
    @classmethod
    def validate_numeric_if_threshold(cls, v: str) -> str:
        """Validate that threshold values are numeric."""
        try:
            float(v)
        except ValueError:
            raise ValueError("Setting value must be a valid number")
        return v


class DefaultThresholdUpdate(BaseModel):
    """Request schema for updating the default warning threshold."""

    default_threshold: Decimal = Field(
        ..., ge=0, description="Default warning threshold for all items"
    )


# =============================================================================
# Import Preview/Validation Schemas
# =============================================================================

class ImportPreview(BaseModel):
    """Preview of what will happen when an import is recorded."""

    certificate_item_id: UUID
    certificate_number: str
    item_name: str
    hs_code: str
    port: str
    quantity_to_import: Decimal
    current_balance: Decimal
    balance_after_import: Decimal
    new_status: str
    will_trigger_warning: bool
    will_deplete: bool
    will_overdraw: bool
    warning_message: Optional[str] = None


class ImportPreviewResponse(BaseModel):
    """Response schema for import preview."""

    previews: list[ImportPreview]
    has_warnings: bool
    has_depletions: bool
    has_overdrawns: bool
    total_items: int


# =============================================================================
# List Response Schemas
# =============================================================================

class ItemBalanceListResponse(BaseModel):
    """Response schema for paginated item balance list."""

    items: list[ItemBalanceRead]
    total: int
    limit: int
    offset: int


class ImportRecordListResponse(BaseModel):
    """Response schema for paginated import record list."""

    records: list[ImportRecordRead]
    total: int
    limit: int
    offset: int
