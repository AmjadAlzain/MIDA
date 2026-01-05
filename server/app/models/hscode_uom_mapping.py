"""HSCODE to UOM mapping model."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


def normalize_hscode(hs_code: str) -> str:
    """
    Normalize HSCODE by removing dots/periods.
    
    Example: "8471.30.10" -> "84713010"
             "8713010" -> "8713010"
             "79.100.100" -> "79100100"
    """
    if not hs_code:
        return ""
    return hs_code.replace(".", "").strip()


class HscodeUomMapping(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Mapping table for HSCODE to UOM.
    
    This table determines whether a matched MIDA item should use
    quantity (UNIT) or net weight (KGM) for balance deduction.
    """

    __tablename__ = "hscode_uom_mappings"

    # Normalized HSCODE (dots removed) - e.g., "84713010"
    hs_code: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True,
        comment="Normalized HSCODE (dots removed)"
    )
    
    # UOM type: "UNIT" or "KGM"
    uom: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="Unit of measure: UNIT or KGM"
    )

    __table_args__ = (
        Index("ix_hscode_uom_mappings_hs_code", "hs_code"),
        CheckConstraint(
            "uom IN ('UNIT', 'KGM')",
            name="ck_hscode_uom_mappings_uom_valid",
        ),
    )

    def __repr__(self) -> str:
        return f"<HscodeUomMapping(hs_code={self.hs_code}, uom={self.uom})>"
