"""MIDA Certificate and Item models."""

from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
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


class CertificateStatus(str, enum.Enum):
    """Status of a MIDA certificate."""

    draft = "draft"
    confirmed = "confirmed"


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
        String(20), nullable=False, default=CertificateStatus.draft.value
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

    # Station split quantities
    port_klang_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )
    klia_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 3), nullable=True)
    bukit_kayu_hitam_qty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )

    # Relationships
    certificate: Mapped["MidaCertificate"] = relationship(
        "MidaCertificate", back_populates="items"
    )

    __table_args__ = (
        UniqueConstraint("certificate_id", "line_no", name="uq_cert_line"),
        Index("ix_mida_certificate_items_hs_code", "hs_code"),
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
    )
