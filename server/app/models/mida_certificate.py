"""MIDA Certificate and Item models."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from typing import List


class CertificateStatus(str, enum.Enum):
    """Status of a MIDA certificate."""

    active = "active"
    expired = "expired"


class QuantityStatus(str, enum.Enum):
    """Status of remaining quantity for an item."""

    NORMAL = "normal"          # Above warning threshold
    WARNING = "warning"        # At or below threshold but > 0
    DEPLETED = "depleted"      # Exactly 0
    OVERDRAWN = "overdrawn"    # Negative (if allowed)


class ImportPort(str, enum.Enum):
    """Available import ports/stations."""

    PORT_KLANG = "port_klang"
    KLIA = "klia"
    BUKIT_KAYU_HITAM = "bukit_kayu_hitam"


class MidaCertificate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """MIDA Customs Exemption Certificate header."""

    __tablename__ = "mida_certificates"

    certificate_number: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    company_name: Mapped[str] = mapped_column(String(500), nullable=False)
    exemption_start_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    exemption_end_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CertificateStatus.active.value
    )
    source_filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    raw_ocr_json: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )

    # Relationships
    items: Mapped[list["MidaCertificateItem"]] = relationship(
        "MidaCertificateItem",
        back_populates="certificate",
        cascade="all, delete-orphan",
        order_by="MidaCertificateItem.line_no",
    )

    __table_args__ = (
        Index("ix_mida_certificates_certificate_number", "certificate_number"),
        Index("ix_mida_certificates_status", "status"),
        CheckConstraint(
            "status IN ('draft', 'confirmed')",
            name="ck_mida_certificates_status",
        ),
    )


class MidaCertificateItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Line item within a MIDA certificate."""

    __tablename__ = "mida_certificate_items"

    certificate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mida_certificates.id", ondelete="CASCADE"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(nullable=False)
    hs_code: Mapped[str] = mapped_column(String(20), nullable=False)
    item_name: Mapped[str] = mapped_column(Text, nullable=False)
    approved_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    uom: Mapped[str] = mapped_column(String(50), nullable=False)

    # Station split quantities (original approved amounts)
    port_klang_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    klia_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 3), nullable=True)
    bukit_kayu_hitam_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )

    # Remaining quantities (decremented on each import)
    remaining_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    remaining_port_klang: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    remaining_klia: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    remaining_bukit_kayu_hitam: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )

    # Warning threshold and status tracking
    warning_threshold: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True, default=None,
        comment="Quantity level below which warnings are triggered"
    )
    quantity_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=QuantityStatus.NORMAL.value,
        comment="Current status: normal, warning, depleted, overdrawn"
    )

    # Relationships
    certificate: Mapped["MidaCertificate"] = relationship(
        "MidaCertificate", back_populates="items"
    )
    import_records: Mapped["List[MidaImportRecord]"] = relationship(
        "MidaImportRecord",
        back_populates="certificate_item",
        cascade="all, delete-orphan",
        order_by="MidaImportRecord.created_at",
    )

    __table_args__ = (
        UniqueConstraint("certificate_id", "line_no", name="uq_cert_line"),
        Index("ix_mida_certificate_items_hs_code", "hs_code"),
        Index("ix_mida_certificate_items_quantity_status", "quantity_status"),
        CheckConstraint("line_no > 0", name="ck_line_no_positive"),
        CheckConstraint(
            "approved_quantity IS NULL OR approved_quantity >= 0",
            name="ck_approved_quantity_non_negative",
        ),
        CheckConstraint(
            "port_klang_qty IS NULL OR port_klang_qty >= 0",
            name="ck_port_klang_qty_non_negative",
        ),
        CheckConstraint(
            "klia_qty IS NULL OR klia_qty >= 0",
            name="ck_klia_qty_non_negative",
        ),
        CheckConstraint(
            "bukit_kayu_hitam_qty IS NULL OR bukit_kayu_hitam_qty >= 0",
            name="ck_bukit_kayu_hitam_qty_non_negative",
        ),
        CheckConstraint(
            "quantity_status IN ('normal', 'warning', 'depleted', 'overdrawn')",
            name="ck_quantity_status_valid",
        ),
        CheckConstraint(
            "warning_threshold IS NULL OR warning_threshold >= 0",
            name="ck_warning_threshold_non_negative",
        ),
    )


class MidaImportRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Master import tracking record.
    
    Each row represents a single import transaction for a specific item
    at a specific port. Balance fields track the running balance for
    this item at this port.
    """

    __tablename__ = "mida_import_records"

    # Link to the certificate item
    certificate_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mida_certificate_items.id", ondelete="CASCADE"), nullable=False
    )

    # Import details
    import_date: Mapped[date] = mapped_column(Date, nullable=False)
    declaration_form_reg_no: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Declaration Form Registration Number"
    )
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_line: Mapped[Optional[int]] = mapped_column(nullable=True)
    quantity_imported: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    port: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="Import port: port_klang, klia, bukit_kayu_hitam"
    )

    # Balance tracking for this item at this port
    balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)

    # Optional notes/remarks
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    certificate_item: Mapped["MidaCertificateItem"] = relationship(
        "MidaCertificateItem", back_populates="import_records"
    )

    __table_args__ = (
        Index("ix_mida_import_records_certificate_item_id", "certificate_item_id"),
        Index("ix_mida_import_records_port", "port"),
        Index("ix_mida_import_records_import_date", "import_date"),
        Index("ix_mida_import_records_invoice_number", "invoice_number"),
        Index(
            "ix_mida_import_records_item_port_date",
            "certificate_item_id", "port", "import_date"
        ),
        CheckConstraint(
            "port IN ('port_klang', 'klia', 'bukit_kayu_hitam')",
            name="ck_import_port_valid",
        ),
        CheckConstraint(
            "quantity_imported > 0",
            name="ck_quantity_imported_positive",
        ),
    )
