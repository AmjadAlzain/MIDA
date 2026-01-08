"""
Invoice Classification Service.

This service handles the classification of invoice items into 3 categories:
1. Form-D items: Items with Form-D flag (and for HICOM, dual-flagged items)
2. MIDA items: Items matched to MIDA certificates (and for Hong Leong, dual-flagged items)
3. Duties Payable items: Items that are neither Form-D nor MIDA matched

Classification Rules:
--------------------
1. MIDA matching is performed on ALL items (both Form-D flagged and non-flagged)
2. Classification logic:
   - If Form-D flag AND NOT MIDA matched → Form-D table
   - If NOT Form-D flag AND MIDA matched → MIDA table
   - If Form-D flag AND MIDA matched:
     - If company is Hong Leong → MIDA table
     - If company is HICOM → Form-D table
   - If NOT Form-D flag AND NOT MIDA matched → Duties Payable table

SST Exemption Defaults:
-----------------------
- HICOM: SST exemption ON for all items in all tables
- Other companies (Hong Leong): SST exemption ON only for MIDA items, OFF for others
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from io import BytesIO
from typing import Optional

import pandas as pd

from app.models.company import Company
from app.models.mida_certificate import MidaCertificate
from app.schemas.classification import ClassifiedItem, ItemTable

logger = logging.getLogger(__name__)

# Column name variations for parsing invoice files
ITEM_NO_CANDIDATES = ["item", "item no", "itemno", "line", "line no", "lineno", "no", "#"]
INVOICE_NO_CANDIDATES = ["invoice no", "invoiceno", "invoice", "inv no", "invno"]
MODEL_NO_CANDIDATES = ["model no", "modelno", "model number", "modelnumber", "model code", "modelcode", "model"]
PARTS_NO_CANDIDATES = ["parts no", "partsno", "part no", "partno", "part number", "partnumber"]
HS_CODE_CANDIDATES = [
    "hs code", "hscode", "hs-code", "hs_code", "tariff code", "tariffcode",
    "commodity code", "commoditycode",
]
DESCRIPTION_CANDIDATES = [
    "parts name", "partsname", "part name", "partname",
    "description", "item description", "itemdescription",
    "product name", "productname", "item name", "itemname",
]
QUANTITY_CANDIDATES = ["quantity", "qty", "quentity", "amount qty"]
UOM_CANDIDATES = ["uom", "unit", "unit of measure", "unitofmeasure"]
AMOUNT_CANDIDATES = ["amount", "amount(usd)", "amount (usd)", "value", "total"]
NET_WEIGHT_CANDIDATES = [
    "net weight", "netweight", "net weight(kg)", "net weight (kg)",
    "weight", "weight(kg)", "weight (kg)",
]
FORM_FLAG_CANDIDATES = ["form flag", "formflag", "flag", "form", "form-d flag"]


def _normalize_header(value: object) -> str:
    """Normalize a column header for matching."""
    return re.sub(r"[\s_\-()]+", "", str(value or "").strip().lower())


def _find_column(columns: list[str], candidates: list[str]) -> Optional[str]:
    """Find the first matching column from candidates."""
    normalized_cols = {_normalize_header(c): c for c in columns}
    for candidate in candidates:
        norm_candidate = _normalize_header(candidate)
        if norm_candidate in normalized_cols:
            return normalized_cols[norm_candidate]
    return None


def parse_all_invoice_items(file_bytes: bytes) -> list[dict]:
    """
    Parse an invoice file and extract ALL items (including Form-D flagged items).
    
    This differs from the existing parse_invoice_file which can exclude Form-D items.
    
    Args:
        file_bytes: Raw bytes of the uploaded file
        
    Returns:
        List of item dictionaries with all invoice fields including form_flag
        
    Raises:
        ValueError: If file format is not supported or required columns are missing
    """
    buffer = BytesIO(file_bytes)
    buffer.seek(0)
    head = buffer.read(8)
    buffer.seek(0)

    # Detect file type by magic bytes
    is_xlsx = head.startswith(b"PK")
    is_xls = head.startswith(b"\xD0\xCF\x11\xE0")

    df = None
    last_error = None

    # Try XLSX first if detected
    if is_xlsx:
        try:
            df = pd.read_excel(buffer, engine="openpyxl")
        except Exception as e:
            last_error = e
            buffer.seek(0)

    # Try XLS if detected or XLSX failed
    if df is None and (is_xls or is_xlsx):
        try:
            df = pd.read_excel(buffer, engine="xlrd")
        except Exception as e:
            last_error = e
            buffer.seek(0)

    # Fallback: try openpyxl then xlrd for unknown formats
    if df is None and not is_xlsx and not is_xls:
        try:
            df = pd.read_excel(buffer, engine="openpyxl")
        except Exception:
            buffer.seek(0)
            try:
                df = pd.read_excel(buffer, engine="xlrd")
            except Exception as e:
                last_error = e

    if df is None:
        raise ValueError(f"Failed to parse invoice file. Make sure it's a valid Excel file (.xls or .xlsx): {last_error}")

    if df.empty:
        raise ValueError("Invoice file is empty")

    # Find columns
    columns = list(df.columns)
    item_no_col = _find_column(columns, ITEM_NO_CANDIDATES)
    invoice_no_col = _find_column(columns, INVOICE_NO_CANDIDATES)
    if invoice_no_col is None and len(columns) > 1:
        invoice_no_col = columns[1]
    parts_no_col = _find_column(columns, PARTS_NO_CANDIDATES)
    model_no_col = _find_column(columns, MODEL_NO_CANDIDATES)
    hs_col = _find_column(columns, HS_CODE_CANDIDATES)
    desc_col = _find_column(columns, DESCRIPTION_CANDIDATES)
    qty_col = _find_column(columns, QUANTITY_CANDIDATES)
    uom_col = _find_column(columns, UOM_CANDIDATES)
    amount_col = _find_column(columns, AMOUNT_CANDIDATES)
    weight_col = _find_column(columns, NET_WEIGHT_CANDIDATES)
    form_flag_col = _find_column(columns, FORM_FLAG_CANDIDATES)

    # Validate required columns
    if not desc_col:
        raise ValueError("Missing required column: Parts Name or Description")
    if not qty_col:
        raise ValueError("Missing required column: Quantity")

    items: list[dict] = []

    for idx, row in df.iterrows():
        description = str(row.get(desc_col, "") or "").strip()
        
        # Skip Total rows
        description_lower = description.lower().strip()
        if description_lower == "total" or description_lower.startswith("total:") or description_lower.startswith("grand total"):
            continue
        
        hs_code = str(row.get(hs_col, "") or "").strip() if hs_col else ""
        
        # Skip empty rows
        if not hs_code and not description:
            continue

        # Get line number
        try:
            if item_no_col:
                line_no = int(row.get(item_no_col, idx + 1) or idx + 1)
            else:
                line_no = int(idx) + 1
        except (ValueError, TypeError):
            line_no = int(idx) + 1

        # Get quantity
        try:
            quantity = Decimal(str(row.get(qty_col, 0) or 0))
        except Exception:
            quantity = Decimal(0)

        # UOM is left empty - will be populated from HSCODE_UOM lookup after MIDA matching
        uom = ""

        amount = None
        if amount_col:
            try:
                amount = Decimal(str(row.get(amount_col, 0) or 0))
            except Exception:
                pass

        net_weight = None
        if weight_col:
            try:
                net_weight = Decimal(str(row.get(weight_col, 0) or 0))
            except Exception:
                pass

        parts_no = ""
        if parts_no_col:
            parts_no = str(row.get(parts_no_col, "") or "").strip()

        invoice_no = ""
        if invoice_no_col:
            invoice_no = str(row.get(invoice_no_col, "") or "").strip()

        model_no = ""
        if model_no_col:
            model_no = str(row.get(model_no_col, "") or "").strip()

        # Get form flag - this is crucial for classification
        form_flag = ""
        if form_flag_col:
            form_flag = str(row.get(form_flag_col, "") or "").strip().upper()

        items.append({
            "line_no": line_no,
            "hs_code": hs_code,
            "description": description,
            "quantity": quantity,
            "uom": uom,
            "amount": amount,
            "net_weight_kg": net_weight,
            "parts_no": parts_no,
            "invoice_no": invoice_no,
            "model_no": model_no,
            "form_flag": form_flag,
        })

    if not items:
        raise ValueError("No valid items found in invoice file")

    return items


def classify_items(
    invoice_items: list[dict],
    company: Company,
    mida_matches: dict[int, dict],  # Map of line_no -> MIDA match info
) -> tuple[list[ClassifiedItem], list[ClassifiedItem], list[ClassifiedItem]]:
    """
    Classify invoice items into Form-D, MIDA, and Duties Payable categories.
    
    Args:
        invoice_items: List of parsed invoice items with form_flag field
        company: Company entity (determines routing and SST defaults)
        mida_matches: Dict mapping line_no to MIDA match info (from matching service)
        
    Returns:
        Tuple of (form_d_items, mida_items, duties_payable_items)
    """
    form_d_items: list[ClassifiedItem] = []
    mida_items: list[ClassifiedItem] = []
    duties_payable_items: list[ClassifiedItem] = []
    
    # Determine company-specific settings
    is_hicom = company.dual_flag_routing == "form_d"  # HICOM routes dual-flagged to Form-D
    sst_all_on = company.sst_default_behavior == "all_on"  # HICOM has SST on for all
    
    for item in invoice_items:
        line_no = item["line_no"]
        is_form_d = item.get("form_flag", "").upper() == "FORM-D"
        mida_match = mida_matches.get(line_no)
        is_mida_matched = mida_match is not None
        
        # Determine which table this item goes to
        if is_form_d and not is_mida_matched:
            # Form-D only → Form-D table
            target_table = ItemTable.form_d
        elif not is_form_d and is_mida_matched:
            # MIDA only → MIDA table
            target_table = ItemTable.mida
        elif is_form_d and is_mida_matched:
            # Dual-flagged: depends on company
            if is_hicom:
                target_table = ItemTable.form_d
            else:
                target_table = ItemTable.mida
        else:
            # Neither → Duties Payable
            target_table = ItemTable.duties_payable
        
        # Determine SST default based on company and table
        if sst_all_on:
            # HICOM: all SST exempted by default
            sst_default = True
        else:
            # Other companies: only MIDA items get SST exemption by default
            sst_default = target_table == ItemTable.mida
        
        # Build the classified item
        classified = ClassifiedItem(
            # Original invoice fields
            line_no=item["line_no"],
            hs_code=item["hs_code"],
            description=item["description"],
            quantity=item["quantity"],
            uom=item["uom"],
            amount=item.get("amount"),
            net_weight_kg=item.get("net_weight_kg"),
            parts_no=item.get("parts_no"),
            invoice_no=item.get("invoice_no"),
            model_no=item.get("model_no"),
            form_flag=item.get("form_flag", ""),
            # MIDA matching fields
            mida_matched=is_mida_matched,
            mida_item_id=mida_match.get("mida_item_id") if mida_match else None,
            mida_certificate_id=mida_match.get("mida_certificate_id") if mida_match else None,
            mida_certificate_number=mida_match.get("mida_certificate_number") if mida_match else None,
            mida_line_no=mida_match.get("mida_line_no") if mida_match else None,
            mida_hs_code=mida_match.get("mida_hs_code") if mida_match else None,
            mida_item_name=mida_match.get("mida_item_name") if mida_match else None,
            remaining_qty=mida_match.get("remaining_qty") if mida_match else None,
            remaining_uom=mida_match.get("remaining_uom") if mida_match else None,
            match_score=mida_match.get("match_score") if mida_match else None,
            approved_qty=mida_match.get("approved_qty") if mida_match else None,
            hscode_uom=mida_match.get("hscode_uom") if mida_match else None,
            deduction_quantity=mida_match.get("deduction_quantity") if mida_match else None,
            # Classification fields
            original_table=target_table,
            current_table=target_table,
            # SST status
            sst_exempted=sst_default,
            sst_exempted_default=sst_default,
            # Not modified yet
            manually_moved=False,
            sst_manually_changed=False,
        )
        
        # Add to appropriate list
        if target_table == ItemTable.form_d:
            form_d_items.append(classified)
        elif target_table == ItemTable.mida:
            mida_items.append(classified)
        else:
            duties_payable_items.append(classified)
    
    return form_d_items, mida_items, duties_payable_items
