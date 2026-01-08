"""HSCODE Master model for Part Name to HSCODE/UOM lookup."""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class HscodeMaster(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Master table mapping Part Names to HSCODE and UOM.
    
    Used as a fallback lookup when invoice items don't have an HSCODE
    after MIDA matching - matches by Part Name to assign HSCODE and UOM.
    
    Data sourced from MIDA HSCODE Master Excel file.
    """

    __tablename__ = "hscode_master"

    # Part name from MIDA (e.g., "BOLT FLG", "AIR FILTER ASSY.")
    part_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="MIDA part name for matching"
    )
    
    # Normalized 8-digit HSCODE (e.g., "73181590")
    hs_code: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="8-digit HSCODE"
    )
    
    # UOM type: "UNIT" or "KGM"
    uom: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="Unit of measure: UNIT or KGM"
    )

    __table_args__ = (
        Index("ix_hscode_master_part_name", "part_name"),
        Index("ix_hscode_master_hs_code", "hs_code"),
    )

    def __repr__(self) -> str:
        return f"<HscodeMaster(part_name='{self.part_name}', hs_code='{self.hs_code}', uom='{self.uom}')>"
