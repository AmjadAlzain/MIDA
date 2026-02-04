"""
XLSX Export Service.

Generates XLSX files for:
- MIDA Certificate details with items and balances
- Item balance sheets with import history per port
- Bulk balance sheet exports (all items in a certificate)

Uses openpyxl for XLSX generation with styled headers and merged cells.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.models.mida_certificate import (
    ImportPort,
    MidaCertificate,
    MidaCertificateItem,
    MidaImportRecord,
)

logger = logging.getLogger(__name__)

# ============ MIDA Template Styling Constants ============
# Font: Times New Roman throughout
MIDA_TITLE_FONT = Font(name="Times New Roman", size=18)  # Row 1 title
MIDA_LABEL_FONT = Font(name="Times New Roman", size=24)  # Rows 4-10, 13-14 labels
MIDA_LABEL_BOLD_FONT = Font(name="Times New Roman", size=24, bold=True)  # Item name in row 8
MIDA_DATA_FONT = Font(name="Times New Roman", size=22)  # Data rows 15+

# Borders - Headers use medium, data uses thin
MIDA_HEADER_BORDER_TOP = Border(
    top=Side(style="medium"),
    left=Side(style="medium"),
    right=Side(style="medium"),
)
MIDA_HEADER_BORDER_BOTTOM = Border(
    left=Side(style="medium"),
    right=Side(style="medium"),
)
MIDA_DATA_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# Column widths matching template
MIDA_COLUMN_WIDTHS = [25.5, 40.5, 32.5, 26.5, 25.5, 26.5, 25.0]

# Row heights
MIDA_TITLE_ROW_HEIGHT = 36.0
MIDA_LABEL_ROW_HEIGHT = 30.6
MIDA_DATA_ROW_HEIGHT = 31.2

# Old styling constants (kept for backward compatibility with certificate export)
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, size=14, color="1F4E79")
SUBTITLE_FONT = Font(bold=True, size=11, color="333333")
LABEL_FONT = Font(bold=True, size=10, color="666666")
VALUE_FONT = Font(size=10, color="333333")
TABLE_HEADER_FILL = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
TABLE_HEADER_FONT = Font(bold=True, size=10, color="1F4E79")
THIN_BORDER = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)
PORT_DISPLAY_NAMES = {
    "port_klang": "Port Klang",
    "klia": "KLIA",
    "bukit_kayu_hitam": "Bukit Kayu Hitam",
}


def _format_decimal(value: Optional[Decimal]) -> str:
    """Format a decimal value for display."""
    if value is None:
        return "0"
    return f"{float(value):,.3f}".rstrip("0").rstrip(".")


def _format_date(value: Optional[date]) -> str:
    """Format a date value for display."""
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d")


def _format_date_malay(value: Optional[date]) -> str:
    """Format a date value for Malay display (DD/MM/YYYY)."""
    if value is None:
        return "-"
    return value.strftime("%d/%m/%Y")


def _set_column_widths(ws, widths: list[float]) -> None:
    """Set column widths for a worksheet."""
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def _set_mida_row_heights(ws, data_start_row: int = 15, data_count: int = 0) -> None:
    """Set row heights to match MIDA template."""
    ws.row_dimensions[1].height = MIDA_TITLE_ROW_HEIGHT
    for row in range(2, 15):
        ws.row_dimensions[row].height = MIDA_LABEL_ROW_HEIGHT
    for row in range(15, 15 + max(data_count, 1)):
        ws.row_dimensions[row].height = MIDA_DATA_ROW_HEIGHT


def _write_mida_balance_sheet(
    ws,
    certificate: MidaCertificate,
    item: MidaCertificateItem,
    records: list,
    port_approved: Decimal,
) -> None:
    """
    Write a MIDA-format balance sheet to a worksheet.
    Matches the exact formatting of the template.
    """
    # Set column widths
    _set_column_widths(ws, MIDA_COLUMN_WIDTHS)
    
    # Row 1: Title "BALANCE SHEET (KASTAM 1)" - merged C1:D1, centered
    ws.merge_cells(start_row=1, start_column=3, end_row=1, end_column=4)
    title_cell = ws.cell(row=1, column=3, value="BALANCE SHEET (KASTAM 1)")
    title_cell.font = MIDA_TITLE_FONT
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    
    # Row 4: Company name
    ws.cell(row=4, column=1, value=f"NO FAIL / NAMA PENGIMPORT : {certificate.company_name}").font = MIDA_LABEL_FONT
    
    # Row 5: Certificate number
    ws.cell(row=5, column=1, value=f"NO SURAT PENGECUALIAN PERBENDAHARAAN : {certificate.certificate_number}").font = MIDA_LABEL_FONT
    
    # Row 6: Exemption date
    exemption_date_str = _format_date_malay(certificate.exemption_start_date)
    ws.cell(row=6, column=1, value=f"TARIKH SURAT PENGECUALIAN : {exemption_date_str}").font = MIDA_LABEL_FONT
    
    # Row 7: Validity period
    start_date_str = _format_date_malay(certificate.exemption_start_date)
    end_date_str = _format_date_malay(certificate.exemption_end_date)
    ws.cell(row=7, column=1, value=f"TEMPOH PENGECUALIAN :  {start_date_str} HINGGA {end_date_str}").font = MIDA_LABEL_FONT
    
    # Row 8: Item label and name (label in A, bold item name in C)
    ws.cell(row=8, column=1, value="JENIS BARANG / NO ITEM : ").font = MIDA_LABEL_FONT
    item_name_with_line = f"{item.item_name} ({item.line_no})"
    ws.cell(row=8, column=3, value=item_name_with_line).font = MIDA_LABEL_BOLD_FONT
    
    # Row 9: Approved quantity (label in A, value in C)
    ws.cell(row=9, column=1, value="KUANTIIT DI LULUSKAN : ").font = MIDA_LABEL_FONT
    qty_str = f"{_format_decimal(port_approved)} {item.uom or 'UNT'} "
    ws.cell(row=9, column=3, value=qty_str).font = MIDA_LABEL_FONT
    
    # Row 10: Exemption type
    ws.cell(row=10, column=1, value="PENGECULIAN * SEPENUHNYA / SEPARA : ").font = MIDA_LABEL_FONT
    
    # Row 13-14: Table headers (2 rows) with medium borders
    uom = (item.uom or "pcs").lower()
    
    # Row 13 headers (top part)
    headers_row13 = ["TARIKH ", "NO DAFTAR ", "BAKI DI BAWA", "KUANTITI", "BAKI", "T/TANGAN ", "T/TANGAN "]
    for col, header in enumerate(headers_row13, start=1):
        cell = ws.cell(row=13, column=col, value=header)
        cell.font = MIDA_LABEL_FONT
        cell.border = MIDA_HEADER_BORDER_TOP
        if col == 4:  # KUANTITI centered
            cell.alignment = Alignment(horizontal="center")
    
    # Row 14 headers (bottom part)
    headers_row14 = ["IMPORT", "BORANG IKRAR", "KEHADAPAN", uom, f"({uom})", "PIK", "PNK"]
    for col, header in enumerate(headers_row14, start=1):
        cell = ws.cell(row=14, column=col, value=header)
        cell.font = MIDA_LABEL_FONT
        cell.border = MIDA_HEADER_BORDER_BOTTOM
        if col in [4, 5]:  # UOM columns centered
            cell.alignment = Alignment(horizontal="center")
    
    # Row 15+: Data rows with thin borders, center aligned
    data_row = 15
    if records:
        for record in sorted(records, key=lambda r: (r.import_date, r.created_at)):
            # Date (DD/MM/YYYY format)
            date_str = record.import_date.strftime("%d/%m/%Y") if record.import_date else "-"
            date_cell = ws.cell(row=data_row, column=1, value=date_str)
            date_cell.font = MIDA_DATA_FONT
            date_cell.border = MIDA_DATA_BORDER
            date_cell.alignment = Alignment(horizontal="center")
            
            # Declaration Form Reg No
            reg_cell = ws.cell(row=data_row, column=2, value=record.declaration_form_reg_no or "-")
            reg_cell.font = MIDA_DATA_FONT
            reg_cell.border = MIDA_DATA_BORDER
            reg_cell.alignment = Alignment(horizontal="center")
            
            # Balance Before
            before_cell = ws.cell(row=data_row, column=3, value=float(record.balance_before))
            before_cell.font = MIDA_DATA_FONT
            before_cell.border = MIDA_DATA_BORDER
            before_cell.alignment = Alignment(horizontal="center")
            before_cell.number_format = '#,##0.00'
            
            # Quantity Imported
            qty_cell = ws.cell(row=data_row, column=4, value=float(record.quantity_imported))
            qty_cell.font = MIDA_DATA_FONT
            qty_cell.border = MIDA_DATA_BORDER
            qty_cell.alignment = Alignment(horizontal="center")
            qty_cell.number_format = '#,##0.00'
            
            # Balance After
            after_cell = ws.cell(row=data_row, column=5, value=float(record.balance_after))
            after_cell.font = MIDA_DATA_FONT
            after_cell.border = MIDA_DATA_BORDER
            after_cell.alignment = Alignment(horizontal="center")
            after_cell.number_format = '#,##0.00'
            
            # T/TANGAN PIK (empty)
            pik_cell = ws.cell(row=data_row, column=6, value="")
            pik_cell.font = MIDA_DATA_FONT
            pik_cell.border = MIDA_DATA_BORDER
            
            # T/TANGAN PNK (empty)
            pnk_cell = ws.cell(row=data_row, column=7, value="")
            pnk_cell.font = MIDA_DATA_FONT
            pnk_cell.border = MIDA_DATA_BORDER
            
            data_row += 1
    
    # Set row heights
    _set_mida_row_heights(ws, data_start_row=15, data_count=len(records))


def _write_header_row(
    ws, row: int, headers: list[str], start_col: int = 1
) -> None:
    """Write a styled table header row."""
    for col, header in enumerate(headers, start=start_col):
        cell = ws.cell(row=row, column=col, value=header)
        cell.fill = TABLE_HEADER_FILL
        cell.font = TABLE_HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER


def _write_info_row(
    ws, row: int, label: str, value: Any, label_col: int = 1, value_col: int = 2
) -> int:
    """Write a label-value info row with styling. Returns next row."""
    label_cell = ws.cell(row=row, column=label_col, value=label)
    label_cell.font = LABEL_FONT
    label_cell.alignment = Alignment(horizontal="right", vertical="center")
    
    value_cell = ws.cell(row=row, column=value_col, value=value)
    value_cell.font = VALUE_FONT
    value_cell.alignment = Alignment(horizontal="left", vertical="center")
    
    return row + 1


def _write_certificate_header(
    ws, certificate: MidaCertificate, start_row: int = 1
) -> int:
    """
    Write certificate information header with merged cells and styling.
    Returns the next available row.
    """
    row = start_row
    
    # Title
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    title_cell = ws.cell(row=row, column=1, value="MIDA Certificate Details")
    title_cell.font = TITLE_FONT
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    row += 2
    
    # Certificate info rows
    row = _write_info_row(ws, row, "Certificate Number:", certificate.certificate_number)
    row = _write_info_row(ws, row, "Company Name:", certificate.company_name)
    row = _write_info_row(ws, row, "Model Number:", certificate.model_number)
    row = _write_info_row(ws, row, "Status:", certificate.status.upper())
    row = _write_info_row(
        ws, row, "Exemption Period:",
        f"{_format_date(certificate.exemption_start_date)} to {_format_date(certificate.exemption_end_date)}"
    )
    
    return row + 1


def _write_item_header(
    ws,
    item: MidaCertificateItem,
    certificate: MidaCertificate,
    start_row: int = 1,
    include_certificate: bool = True,
    custom_title: str = None,
) -> int:
    """
    Write item information header with merged cells and styling.
    Returns the next available row.
    """
    row = start_row
    
    # Title
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    title_text = custom_title if custom_title else f"Balance Sheet - Item #{item.line_no}"
    title_cell = ws.cell(row=row, column=1, value=title_text)
    title_cell.font = TITLE_FONT
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    row += 2
    
    if include_certificate:
        # Certificate info
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        cert_cell = ws.cell(row=row, column=1, value="Certificate Information")
        cert_cell.font = SUBTITLE_FONT
        row += 1
        
        row = _write_info_row(ws, row, "Certificate Number:", certificate.certificate_number)
        row = _write_info_row(ws, row, "Company Name:", certificate.company_name)
        row = _write_info_row(ws, row, "Model Number:", certificate.model_number or "-")
        row = _write_info_row(
            ws, row, "Validity Period:",
            f"{_format_date(certificate.exemption_start_date)} to {_format_date(certificate.exemption_end_date)}"
        )
        row += 1
    
    # Item info
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    item_cell = ws.cell(row=row, column=1, value="Item Information")
    item_cell.font = SUBTITLE_FONT
    row += 1
    
    row = _write_info_row(ws, row, "Line #:", item.line_no)
    row = _write_info_row(ws, row, "HS Code:", item.hs_code)
    row = _write_info_row(ws, row, "Item Name:", item.item_name)
    row = _write_info_row(ws, row, "UOM:", item.uom)
    row += 1
    
    # Quantities
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    qty_cell = ws.cell(row=row, column=1, value="Quantity Summary")
    qty_cell.font = SUBTITLE_FONT
    row += 1
    
    row = _write_info_row(ws, row, "Total Approved:", _format_decimal(item.approved_quantity))
    row = _write_info_row(ws, row, "Total Remaining:", _format_decimal(item.remaining_quantity))
    row += 1
    
    # Port breakdown
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    port_cell = ws.cell(row=row, column=1, value="Port Allocation (Approved / Remaining)")
    port_cell.font = SUBTITLE_FONT
    row += 1
    
    row = _write_info_row(
        ws, row, "Port Klang:",
        f"{_format_decimal(item.port_klang_qty)} / {_format_decimal(item.remaining_port_klang)}"
    )
    row = _write_info_row(
        ws, row, "KLIA:",
        f"{_format_decimal(item.klia_qty)} / {_format_decimal(item.remaining_klia)}"
    )
    row = _write_info_row(
        ws, row, "Bukit Kayu Hitam:",
        f"{_format_decimal(item.bukit_kayu_hitam_qty)} / {_format_decimal(item.remaining_bukit_kayu_hitam)}"
    )
    
    return row + 1


def generate_certificate_xlsx(
    certificate: MidaCertificate,
) -> bytes:
    """
    Generate an XLSX file for a MIDA certificate with all items and their balances.
    
    Format:
    - Certificate header info at top (merged cells, styled)
    - Table with all items showing approved/remaining quantities per port
    
    Args:
        certificate: The MIDA certificate with items loaded
        
    Returns:
        XLSX file as bytes
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Certificate"
    
    # Write certificate header
    row = _write_certificate_header(ws, certificate)
    row += 1
    
    # Write items table title
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=12)
    items_title = ws.cell(row=row, column=1, value="Certificate Items")
    items_title.font = SUBTITLE_FONT
    row += 1
    
    # Write items table header
    headers = [
        "Line #", "HS Code", "Item Name", "UOM",
        "Approved Qty", "Remaining Qty",
        "PK Approved", "PK Remaining",
        "KLIA Approved", "KLIA Remaining",
        "BKH Approved", "BKH Remaining",
    ]
    _write_header_row(ws, row, headers)
    row += 1
    
    # Write items
    for item in certificate.items:
        ws.cell(row=row, column=1, value=item.line_no).border = THIN_BORDER
        ws.cell(row=row, column=2, value=item.hs_code).border = THIN_BORDER
        ws.cell(row=row, column=3, value=item.item_name).border = THIN_BORDER
        ws.cell(row=row, column=4, value=item.uom).border = THIN_BORDER
        ws.cell(row=row, column=5, value=float(item.approved_quantity or 0)).border = THIN_BORDER
        ws.cell(row=row, column=6, value=float(item.remaining_quantity or 0)).border = THIN_BORDER
        ws.cell(row=row, column=7, value=float(item.port_klang_qty or 0)).border = THIN_BORDER
        ws.cell(row=row, column=8, value=float(item.remaining_port_klang or 0)).border = THIN_BORDER
        ws.cell(row=row, column=9, value=float(item.klia_qty or 0)).border = THIN_BORDER
        ws.cell(row=row, column=10, value=float(item.remaining_klia or 0)).border = THIN_BORDER
        ws.cell(row=row, column=11, value=float(item.bukit_kayu_hitam_qty or 0)).border = THIN_BORDER
        ws.cell(row=row, column=12, value=float(item.remaining_bukit_kayu_hitam or 0)).border = THIN_BORDER
        
        # Number formatting for quantity columns
        for col in range(5, 13):
            ws.cell(row=row, column=col).number_format = '#,##0.000'
        
        row += 1
    
    # Set column widths
    _set_column_widths(ws, [8, 15, 40, 10, 14, 14, 14, 14, 14, 14, 14, 14])
    
    # Output
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def generate_item_balance_sheet_xlsx(
    item: MidaCertificateItem,
    certificate: MidaCertificate,
    port: Optional[str] = None,
    import_records: Optional[list] = None,
) -> bytes:
    """
    Generate an XLSX file for an item's balance sheet (import history).
    
    If port is None, generates a workbook with 3 sheets (one per port).
    If port is specified, generates a single sheet for that port.
    
    Format matches the MIDA balance sheet template exactly.
    
    Args:
        item: The certificate item
        certificate: The parent certificate
        port: Optional port filter (None = all ports as separate sheets)
        import_records: List of import records (if None, uses item.import_records)
        
    Returns:
        XLSX file as bytes
    """
    # Use provided import_records or fall back to item.import_records
    all_records = import_records if import_records is not None else list(item.import_records or [])
    
    wb = Workbook()
    
    # Remove default sheet
    wb.remove(wb.active)
    
    ports_to_export = [port] if port else ["port_klang", "klia", "bukit_kayu_hitam"]
    
    for port_key in ports_to_export:
        # Filter records for this port
        records = [r for r in all_records if r.port == port_key]
        
        # Create sheet
        port_display = PORT_DISPLAY_NAMES.get(port_key, port_key)
        ws = wb.create_sheet(title=port_display)
        
        # Get the port-specific approved quantity
        if port_key == "port_klang":
            port_approved = item.port_klang_qty or item.approved_quantity or 0
        elif port_key == "klia":
            port_approved = item.klia_qty or item.approved_quantity or 0
        elif port_key == "bukit_kayu_hitam":
            port_approved = item.bukit_kayu_hitam_qty or item.approved_quantity or 0
        else:
            port_approved = item.approved_quantity or 0
        
        # Write MIDA-format balance sheet using the helper
        _write_mida_balance_sheet(ws, certificate, item, records, port_approved)
    
    # Output
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def generate_all_items_balance_sheets_xlsx(
    certificate: MidaCertificate,
    port: str,
    import_records_by_item: Optional[dict] = None,
) -> bytes:
    """
    Generate an XLSX file with balance sheets for ALL items in a certificate,
    for a specific port. Each item gets its own sheet.
    
    Format matches the MIDA balance sheet template exactly:
    - Font: Times New Roman
    - Row 1: Title "BALANCE SHEET (KASTAM 1)" (size 18, centered in C1:D1)
    - Row 4-10: Labels (size 24)
    - Row 8 col C: Item name (size 24, bold)
    - Rows 13-14: Two-row headers with medium borders
    - Row 15+: Data with thin borders, size 22, centered
    
    Args:
        certificate: The certificate with items loaded
        port: The port to export (port_klang, klia, bukit_kayu_hitam)
        import_records_by_item: Dict mapping item_id to list of import records
        
    Returns:
        XLSX file as bytes
    """
    wb = Workbook()
    
    # Remove default sheet
    wb.remove(wb.active)
    
    for item in certificate.items:
        # Get records for this item from the dict, or fall back to item.import_records
        item_records = []
        if import_records_by_item is not None:
            item_records = import_records_by_item.get(item.id, [])
        else:
            item_records = list(item.import_records or [])
        
        # Filter records for this port
        records = [r for r in item_records if r.port == port]
        
        # Create sheet with format "ItemName (line_no)" - truncate item name to fit Excel's 31 char limit
        line_suffix = f" ({item.line_no})"
        max_name_length = 31 - len(line_suffix)
        # Sanitize item name - remove characters not allowed in Excel sheet names
        sanitized_name = item.item_name
        for char in ['/', '\\', '*', '?', ':', '[', ']']:
            sanitized_name = sanitized_name.replace(char, ',')
        truncated_name = sanitized_name[:max_name_length] if len(sanitized_name) > max_name_length else sanitized_name
        sheet_name = f"{truncated_name}{line_suffix}"
        ws = wb.create_sheet(title=sheet_name)
        
        # Get the port-specific approved quantity
        if port == "port_klang":
            port_approved = item.port_klang_qty or item.approved_quantity or 0
        elif port == "klia":
            port_approved = item.klia_qty or item.approved_quantity or 0
        elif port == "bukit_kayu_hitam":
            port_approved = item.bukit_kayu_hitam_qty or item.approved_quantity or 0
        else:
            port_approved = item.approved_quantity or 0
        
        # Write MIDA-format balance sheet using the helper
        _write_mida_balance_sheet(ws, certificate, item, records, port_approved)
    
    # Output
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
