"""Company model for the invoice converter."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Company entity for managing SST exemption defaults and categorization rules.
    
    The company determines:
    1. Default SST exemption status for items in each table
    2. How dual-flagged items (Form-D AND MIDA matched) are categorized
    
    Company-specific rules:
    - HICOM: 
        - All SST defaults ON across all tables
        - Dual-flagged items go to Form-D table
    - Hong Leong:
        - SST default ON only for MIDA table, OFF for Form-D and Duties Payable
        - Dual-flagged items go to MIDA table
    """

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    
    # SST default behavior code:
    # "all_on" - SST exemption default ON for all tables (like HICOM)
    # "mida_only" - SST exemption default ON only for MIDA table (like Hong Leong)
    sst_default_behavior: Mapped[str] = mapped_column(
        String(50), nullable=False, default="mida_only"
    )
    
    # Dual-flag routing: where to route items that are both Form-D flagged AND MIDA matched
    # "form_d" - Route to Form-D table (like HICOM)
    # "mida" - Route to MIDA table (like Hong Leong)
    dual_flag_routing: Mapped[str] = mapped_column(
        String(50), nullable=False, default="mida"
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}')>"
