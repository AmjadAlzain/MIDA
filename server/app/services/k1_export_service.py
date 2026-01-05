"""
K1 Import XLS Export Service.

Generates K1 Import XLS files from invoice items using the K1 Import Template.
Follows the same pattern as Form-D-demo: writes to 'JobCargo' sheet with
template-based column mapping.

Supports 3 export types:
1. Form-D export: Import Duty exemption ON, SST per item's sst_exempted flag
2. MIDA export: Import Duty exemption ON, SST per item's sst_exempted flag
3. Duties Payable export: Import Duty exemption OFF (empty), SST per item's sst_exempted flag
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import xlrd
from xlutils.copy import copy as xlutils_copy

logger = logging.getLogger(__name__)

# Path to the K1 Import Template
TEMPLATE_PATH = Path(__file__).parent.parent.parent / "templates" / "K1_Import_Template.xls"

# Column name variants for matching
ALWAYS_BLANK_COLUMN_NAMES = [
    "ExciseDutyMethod",
    "ExciseDutyRateExemptedPercentage",
    "ExciseDutyRateExemptedSpecific",
    "VehicleType",
    "VehicleModel",
    "Brand",
    "Engine",
    "Chassis",
    "CC",
    "Year",
]

# Export types
EXPORT_TYPE_FORM_D = "form_d"
EXPORT_TYPE_MIDA = "mida"
EXPORT_TYPE_DUTIES_PAYABLE = "duties_payable"


def _normalize_header(value: object) -> str:
    """Normalize a header by removing whitespace, hyphens, and converting to lowercase."""
    if value is None:
        return ""
    return re.sub(r"[\s_\-]+", "", str(value).strip().lower())


def _digits_only(hs_code: str) -> str:
    """Extract only digits from HS code."""
    return re.sub(r"[^\d]", "", hs_code or "")


def _format_hs_code(hs_code: str) -> str:
    """Format HS code for K1 Import: digits only + '00' suffix."""
    digits = _digits_only(hs_code)
    if digits:
        return digits + "00"
    return ""


def _to_float(value: Any) -> float:
    """Convert value to float, handling Decimal and None."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _sanitize_cell(value: object) -> object:
    """Sanitize a cell's value by removing control characters."""
    if value is None:
        return ""
    if isinstance(value, str):
        # Remove bad control characters
        cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", value)
        # Truncate if too long for Excel cell
        if len(cleaned) > 32767:
            cleaned = cleaned[:32767]
        return cleaned
    return value


def _load_template_columns(template_path: Path) -> list[str]:
    """Load the header row from the 'JobCargo' sheet in an XLS template file."""
    book = xlrd.open_workbook(str(template_path))
    try:
        sheet = book.sheet_by_name("JobCargo")
    except xlrd.biffh.XLRDError:
        raise ValueError("Sheet 'JobCargo' not found in the template.")

    headers: list[str] = []
    for col_idx in range(sheet.ncols):
        value = sheet.cell_value(0, col_idx)
        if isinstance(value, str):
            value = value.strip().lstrip("'")
        headers.append("" if value is None else str(value))
    return headers


def generate_k1_xls(items: list[dict], country: str = "MY") -> bytes:
    """
    Generate K1 Import XLS from invoice items.

    Args:
        items: List of invoice item dictionaries with keys:
            - hs_code: HS tariff code
            - description: Item description
            - quantity: Invoice quantity
            - uom: Unit of measure
            - amount: Amount in USD (optional)
            - net_weight_kg: Net weight in KG (optional)
        country: Country of origin code (default: "MY")

    Returns:
        XLS file as bytes
    """
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template file not found at {TEMPLATE_PATH}")

    # Load template columns from JobCargo sheet
    template_columns = _load_template_columns(TEMPLATE_PATH)
    logger.info(f"Template columns: {template_columns}")

    # Build output DataFrame with mapped columns
    output = pd.DataFrame(index=range(len(items)))

    # Extract and transform item data
    hs_codes = [_format_hs_code(item.get("hs_code", "")) for item in items]
    descriptions = [str(item.get("description", "")) for item in items]
    uoms = [str(item.get("uom", "UNT")).upper() for item in items]
    quantities = [_to_float(item.get("quantity", 0)) for item in items]
    amounts = [_to_float(item.get("amount", 0)) for item in items]
    net_weights = [_to_float(item.get("net_weight_kg", 0)) for item in items]

    # Calculate statistical/declared quantities based on UOM
    stat_qtys = []
    for i, uom in enumerate(uoms):
        if uom == "KGM" and net_weights[i] > 0:
            stat_qtys.append(net_weights[i])
        else:
            stat_qtys.append(quantities[i])

    # Map to output columns
    output["CountryOfOrigin"] = country
    output["HSCode"] = hs_codes
    output["StatisticalUOM"] = uoms
    output["DeclaredUOM"] = uoms
    output["StatisticalQty"] = stat_qtys
    output["DeclaredQty"] = stat_qtys
    output["ItemAmount"] = amounts
    output["ItemDescription"] = descriptions
    output["ItemDescription2"] = quantities  # Store quantity in Description2 per Form-D pattern
    output["ItemDescription3"] = ""

    # Exemption settings
    output["ImportDutyMethod"] = "Exemption"
    output["ImportDutyRateExemptedPercentage"] = 100
    output["ImportDutyRateExemptedSpecific"] = ""

    output["SSTMethod"] = "Exemption"
    output["SSTRateExemptedPercentage"] = 100
    output["SSTRateExemptedSpecific"] = ""

    # Always blank columns
    output["ExciseDutyMethod"] = ""
    output["ExciseDutyRateExemptedPercentage"] = ""
    output["ExciseDutyRateExemptedSpecific"] = ""
    output["VehicleType"] = ""
    output["VehicleModel"] = ""
    output["Brand"] = ""
    output["Engine"] = ""
    output["Chassis"] = ""
    output["CC"] = ""
    output["Year"] = ""

    # Build normalized column map
    normalized_output_map = {
        _normalize_header(col): output[col] for col in output.columns
    }
    collapsed_output_map = {
        re.sub(r"[^a-z0-9]", "", key): value for key, value in normalized_output_map.items()
    }

    always_blank_normalized = {_normalize_header(n) for n in ALWAYS_BLANK_COLUMN_NAMES}
    always_blank_collapsed = {re.sub(r"[^a-z0-9]", "", n) for n in always_blank_normalized}

    # Track Method column occurrences (first two get "E", third is blank)
    method_occurrence = 0

    # Build final DataFrame matching template column order
    final_series: list[pd.Series] = []
    for template_column in template_columns:
        normalized_key = _normalize_header(template_column)
        collapsed_key = re.sub(r"[^a-z0-9]", "", normalized_key)

        if normalized_key == "method":
            method_occurrence += 1
            if method_occurrence in (1, 2):
                fill_value = "E"
            else:
                fill_value = ""
            series = pd.Series([fill_value] * len(output), index=output.index, dtype="object")
        elif normalized_key in always_blank_normalized or collapsed_key in always_blank_collapsed:
            series = pd.Series([""] * len(output), index=output.index, dtype="object")
        elif normalized_key in normalized_output_map:
            series = normalized_output_map[normalized_key]
        elif collapsed_key in collapsed_output_map:
            series = collapsed_output_map[collapsed_key]
        else:
            series = pd.Series([""] * len(output), index=output.index, dtype="object")

        final_series.append(series.rename(template_column))

    final_df = pd.concat(final_series, axis=1) if final_series else pd.DataFrame(index=output.index)

    # Write to XLS using template
    return _to_xls_bytes_with_template(final_df, TEMPLATE_PATH)


def _to_xls_bytes_with_template(final_df: pd.DataFrame, template_path: Path) -> bytes:
    """Convert a DataFrame to XLS bytes using a template, writing to JobCargo sheet."""
    book_reader = xlrd.open_workbook(str(template_path), formatting_info=True)
    book_writer = xlutils_copy(book_reader)

    # Find JobCargo sheet
    sheet_names = book_reader.sheet_names()
    if "JobCargo" not in sheet_names:
        raise ValueError("Sheet 'JobCargo' not found in the template.")
    
    sheet_index = sheet_names.index("JobCargo")
    sheet_writer = book_writer.get_sheet(sheet_index)

    # Write data rows (starting at row 1, row 0 is header)
    data_to_write = final_df.values.tolist()
    for r_idx, row_data in enumerate(data_to_write, start=1):
        for c_idx, value in enumerate(row_data):
            sanitized_value = _sanitize_cell(value)
            sheet_writer.write(r_idx, c_idx, sanitized_value)

    # Save to bytes
    buffer = BytesIO()
    book_writer.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def generate_k1_xls_with_options(
    items: list[dict],
    export_type: str,
    country: str = "MY",
) -> bytes:
    """
    Generate K1 Import XLS with configurable duty/SST exemption settings.
    
    This is the main export function for the 3-tab classification feature.
    
    Args:
        items: List of item dictionaries with keys:
            - hs_code: HS tariff code
            - description: Item description (Parts Name)
            - description2: Secondary description (Quantity) - optional
            - quantity: Invoice quantity
            - uom: Unit of measure
            - amount: Amount in USD (optional)
            - net_weight_kg: Net weight in KG (optional)
            - sst_exempted: Boolean indicating if SST is exempted for this item
        export_type: One of 'form_d', 'mida', or 'duties_payable'
        country: Country of origin code (default: "MY")
        
    Returns:
        XLS file as bytes
        
    Export Type Settings:
        - form_d: ImportDutyMethod = "Exemption", Method = "E", percentage = 100
        - mida: ImportDutyMethod = "Exemption", Method = "E", percentage = 100
        - duties_payable: ImportDutyMethod = empty, Method = empty, percentage = empty
        
    SST columns are set per item based on sst_exempted field:
        - If sst_exempted=True: SSTMethod = "Exemption", Method = "E", percentage = 100
        - If sst_exempted=False: SSTMethod = empty, Method = empty, percentage = empty
    """
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template file not found at {TEMPLATE_PATH}")

    # Load template columns from JobCargo sheet
    template_columns = _load_template_columns(TEMPLATE_PATH)
    logger.info(f"Template columns for {export_type} export: {template_columns}")

    # Build output DataFrame with mapped columns
    n_items = len(items)
    output = pd.DataFrame(index=range(n_items))

    # Extract and transform item data
    hs_codes = [_format_hs_code(item.get("hs_code", "")) for item in items]
    descriptions = [str(item.get("description", "")) for item in items]
    descriptions2 = [str(item.get("description2", item.get("quantity", ""))) for item in items]
    uoms = [str(item.get("uom", "UNT")).upper() for item in items]
    quantities = [_to_float(item.get("quantity", 0)) for item in items]
    amounts = [_to_float(item.get("amount", 0)) for item in items]
    net_weights = [_to_float(item.get("net_weight_kg", 0)) for item in items]
    sst_exemptions = [item.get("sst_exempted", False) for item in items]

    # Normalize UOMs to KGM or UNT
    normalized_uoms = []
    for uom in uoms:
        if uom in ("KGM", "KG", "KGS", "KILOGRAM", "KILOGRAMS"):
            normalized_uoms.append("KGM")
        else:
            normalized_uoms.append("UNT")
    uoms = normalized_uoms

    # Calculate statistical/declared quantities based on UOM
    stat_qtys = []
    for i, uom in enumerate(uoms):
        if uom == "KGM" and net_weights[i] > 0:
            stat_qtys.append(net_weights[i])
        else:
            stat_qtys.append(quantities[i])

    # Core columns (same for all export types)
    output["CountryOfOrigin"] = country
    output["HSCode"] = hs_codes
    output["StatisticalQty"] = stat_qtys
    output["StatisticalUOM"] = uoms
    output["DeclaredQty"] = stat_qtys
    output["DeclaredUOM"] = uoms
    output["ItemAmount"] = amounts
    output["ItemDescription"] = descriptions
    output["ItemDescription2"] = descriptions2
    output["ItemDescription3"] = ""
    
    # Import Duty columns depend on export type
    if export_type in (EXPORT_TYPE_FORM_D, EXPORT_TYPE_MIDA):
        # Form-D and MIDA: Import Duty exemption ON
        output["ImportDutyMethod"] = "Exemption"
        output["ImportDutyRateExemptedPercentage"] = 100
    else:
        # Duties Payable: Import Duty exemption OFF (empty)
        output["ImportDutyMethod"] = ""
        output["ImportDutyRateExemptedPercentage"] = ""
    
    output["ImportDutyRateExemptedSpecific"] = ""
    
    # SST columns - per item based on sst_exempted flag
    sst_methods = ["Exemption" if sst else "" for sst in sst_exemptions]
    sst_percentages = [100 if sst else "" for sst in sst_exemptions]
    
    output["SSTMethod"] = sst_methods
    output["SSTRateExemptedPercentage"] = sst_percentages
    output["SSTRateExemptedSpecific"] = ""

    # Always blank columns
    output["ExciseDutyMethod"] = ""
    output["ExciseDutyRateExemptedPercentage"] = ""
    output["ExciseDutyRateExemptedSpecific"] = ""
    output["VehicleType"] = ""
    output["VehicleModel"] = ""
    output["Brand"] = ""
    output["Engine"] = ""
    output["Chassis"] = ""
    output["CC"] = ""
    output["Year"] = ""

    # Build normalized column map
    normalized_output_map = {
        _normalize_header(col): output[col] for col in output.columns
    }
    collapsed_output_map = {
        re.sub(r"[^a-z0-9]", "", key): value for key, value in normalized_output_map.items()
    }

    always_blank_normalized = {_normalize_header(n) for n in ALWAYS_BLANK_COLUMN_NAMES}
    always_blank_collapsed = {re.sub(r"[^a-z0-9]", "", n) for n in always_blank_normalized}

    # Track Method column occurrences
    # For Form-D/MIDA: first Method gets "E", second Method gets SST-based values, third is blank
    # For Duties Payable: first Method is blank (no import duty), second Method gets SST-based values, third is blank
    method_occurrence = 0

    # Build final DataFrame matching template column order
    final_series: list[pd.Series] = []
    for template_column in template_columns:
        normalized_key = _normalize_header(template_column)
        collapsed_key = re.sub(r"[^a-z0-9]", "", normalized_key)

        if normalized_key == "method":
            method_occurrence += 1
            if method_occurrence == 1:
                # First Method column = ImportDuty Method
                if export_type in (EXPORT_TYPE_FORM_D, EXPORT_TYPE_MIDA):
                    fill_values = ["E"] * n_items
                else:
                    fill_values = [""] * n_items
            elif method_occurrence == 2:
                # Second Method column = SST Method (per item)
                fill_values = ["E" if sst else "" for sst in sst_exemptions]
            else:
                # Third and beyond = blank
                fill_values = [""] * n_items
            series = pd.Series(fill_values, index=output.index, dtype="object")
        elif normalized_key in always_blank_normalized or collapsed_key in always_blank_collapsed:
            series = pd.Series([""] * n_items, index=output.index, dtype="object")
        elif normalized_key in normalized_output_map:
            series = normalized_output_map[normalized_key]
        elif collapsed_key in collapsed_output_map:
            series = collapsed_output_map[collapsed_key]
        else:
            series = pd.Series([""] * n_items, index=output.index, dtype="object")

        final_series.append(series.rename(template_column))

    final_df = pd.concat(final_series, axis=1) if final_series else pd.DataFrame(index=output.index)

    # Write to XLS using template
    return _to_xls_bytes_with_template(final_df, TEMPLATE_PATH)