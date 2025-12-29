"""
Pydantic schemas for MIDA Certificate API.

These schemas define the request/response models for certificate CRUD operations.
They provide validation and serialization for the API layer.

OCR Parse Response Mapping:
--------------------------
The OCR parse endpoint (/api/mida/certificate/parse) returns:
{
    "certificate_number": str,
    "company_name": str,
    "exemption_start_date": str (YYYY-MM-DD) or null,
    "exemption_end_date": str (YYYY-MM-DD) or null,
    "items": [
        {
            "line_no": int,
            "hs_code": str,
            "item_name": str,
            "approved_quantity": float or null,
            "uom": str,
            "port_klang_qty": float or null,
            "klia_qty": float or null,
            "bukit_kayu_hitam_qty": float or null
        },
        ...
    ],
    "warnings": [...]
}

To save a parsed certificate as draft, map directly to CertificateDraftCreateRequest:
{
    "header": {
        "certificate_number": <from parse>,
        "company_name": <from parse>,
        "exemption_start_date": <from parse>,
        "exemption_end_date": <from parse>,
        "source_filename": <original filename>
    },
    "items": <items array from parse>,
    "raw_ocr_json": <full parse response if you want to store it>
}
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CertificateItemIn(BaseModel):
    """Input schema for a certificate line item."""

    line_no: int = Field(..., gt=0, description="Line number (must be positive)")
    hs_code: str = Field(..., min_length=1, description="HS tariff code")
    item_name: str = Field(..., min_length=1, description="Item description")
    approved_quantity: Optional[Decimal] = Field(
        default=None, ge=0, description="Approved quantity (must be >= 0 if provided)"
    )
    uom: str = Field(..., min_length=1, description="Unit of measure")

    # Optional station split quantities
    port_klang_qty: Optional[Decimal] = Field(
        default=None, ge=0, description="Port Klang station quantity"
    )
    klia_qty: Optional[Decimal] = Field(
        default=None, ge=0, description="KLIA station quantity"
    )
    bukit_kayu_hitam_qty: Optional[Decimal] = Field(
        default=None, ge=0, description="Bukit Kayu Hitam station quantity"
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class CertificateHeaderIn(BaseModel):
    """Input schema for certificate header fields."""

    certificate_number: str = Field(
        ..., min_length=1, description="Certificate number (required, non-empty)"
    )
    company_name: str = Field(
        ..., min_length=1, description="Company name (required, non-empty)"
    )
    exemption_start_date: Optional[date] = Field(
        default=None, description="Exemption period start date"
    )
    exemption_end_date: Optional[date] = Field(
        default=None, description="Exemption period end date"
    )
    source_filename: Optional[str] = Field(
        default=None, max_length=500, description="Original source filename"
    )

    model_config = ConfigDict(str_strip_whitespace=True)


class CertificateDraftCreateRequest(BaseModel):
    """
    Request schema for creating a new certificate.

    If a certificate with the same certificate_number already exists,
    returns 409 Conflict - duplicates are not allowed.

    New certificates are created with:
    - 'active' status if exemption_end_date is None or >= today
    - 'expired' status if exemption_end_date < today
    """

    header: CertificateHeaderIn
    items: list[CertificateItemIn] = Field(
        ..., min_length=1, description="List of items (at least one required)"
    )
    raw_ocr_json: Optional[dict[str, Any]] = Field(
        default=None, description="Raw OCR response for audit/debugging"
    )

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list[CertificateItemIn]) -> list[CertificateItemIn]:
        """Validate that items list is not empty."""
        if not v:
            raise ValueError("items list cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_unique_line_numbers(self) -> "CertificateDraftCreateRequest":
        """Validate that line numbers are unique within the items list."""
        line_nos = [item.line_no for item in self.items]
        if len(line_nos) != len(set(line_nos)):
            raise ValueError("Duplicate line_no values found in items")
        return self


class CertificateDraftUpdateRequest(BaseModel):
    """
    Request schema for updating an existing draft certificate by ID.

    Only draft certificates can be updated. Confirmed certificates are read-only.
    All items are replaced (delete existing, insert new).
    """

    header: CertificateHeaderIn
    items: list[CertificateItemIn] = Field(
        ..., min_length=1, description="List of items (at least one required)"
    )

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list[CertificateItemIn]) -> list[CertificateItemIn]:
        """Validate that items list is not empty."""
        if not v:
            raise ValueError("items list cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_unique_line_numbers(self) -> "CertificateDraftUpdateRequest":
        """Validate that line numbers are unique within the items list."""
        line_nos = [item.line_no for item in self.items]
        if len(line_nos) != len(set(line_nos)):
            raise ValueError("Duplicate line_no values found in items")
        return self


class CertificateItemRead(BaseModel):
    """Response schema for a certificate line item."""

    id: UUID
    line_no: int
    hs_code: str
    item_name: str
    approved_quantity: Optional[Decimal] = None
    uom: str
    port_klang_qty: Optional[Decimal] = None
    klia_qty: Optional[Decimal] = None
    bukit_kayu_hitam_qty: Optional[Decimal] = None
    
    # Remaining quantities
    remaining_quantity: Optional[Decimal] = None
    remaining_port_klang: Optional[Decimal] = None
    remaining_klia: Optional[Decimal] = None
    remaining_bukit_kayu_hitam: Optional[Decimal] = None
    
    # Warning/status tracking
    warning_threshold: Optional[Decimal] = None
    quantity_status: str = "normal"
    
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CertificateRead(BaseModel):
    """Response schema for a certificate with items."""

    id: UUID
    certificate_number: str
    company_name: str
    exemption_start_date: Optional[date] = None
    exemption_end_date: Optional[date] = None
    status: str
    source_filename: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: list[CertificateItemRead] = Field(default_factory=list)

    # Note: raw_ocr_json is intentionally excluded from read response
    # to avoid leaking potentially sensitive OCR data

    model_config = ConfigDict(from_attributes=True)


class CertificateListResponse(BaseModel):
    """Response schema for paginated certificate list."""

    items: list[CertificateRead]
    total: int
    limit: int
    offset: int
