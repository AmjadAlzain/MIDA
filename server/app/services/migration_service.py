"""
Migration Service for MIDA Balance Sheet Import.

Handles parsing XLSX balance sheet files in the company's template format,
validating against existing database records, and creating synthetic import records.

Template Format (per sheet = one item):
- Row 5, Col A: "NO SURAT PENGECUALIAN PERBENDAHARAAN : CDE2/2024/00755"
- Row 8, Col C: "BOLT,FLG. (1)" - item name with line number in parentheses
- Row 9, Col C: 1484.4 - approved quantity
- Row 13-14: Table headers (TARIKH IMPORT, NO DAFTAR BORANG IKRAR, etc.)
- Row 15+: Invoice data rows
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Optional
from uuid import UUID

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session

from app.models.mida_certificate import (
    MidaCertificate,
    MidaCertificateItem,
    MidaImportRecord,
    ImportPort,
)
from app.repositories import mida_import_repo, mida_certificate_repo
from app.schemas.migration import (
    ImportPort as SchemaImportPort,
    ItemMatchStatus,
    ConflictResolution,
    MigrationInvoiceRow,
    MigrationItemPreview,
    MigrationPreviewResponse,
    MigrationApplyRequest,
    MigrationApplyResult,
    MigrationApplyResponse,
    ItemResolution,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class MigrationError(Exception):
    """Base exception for migration operations."""
    pass


class InvalidFileError(MigrationError):
    """Raised when the uploaded file is invalid or cannot be parsed."""
    pass


class CertificateNotFoundError(MigrationError):
    """Raised when the certificate from XLSX is not found in database."""
    pass


# =============================================================================
# XLSX Parsing Helpers
# =============================================================================

def _parse_date(value) -> Optional[date]:
    """
    Parse date from various formats.
    
    Handles:
    - datetime objects (from Excel)
    - "DD.MM.YYYY" strings
    - "DD/MM/YYYY" strings
    - "DD.MM,YYYY" strings (typo with comma instead of period)
    """
    if value is None:
        return None
    
    if isinstance(value, datetime):
        return value.date()
    
    if isinstance(value, date):
        return value
    
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        
        # Fix common typo: comma instead of period (e.g., "06.08,2024" -> "06.08.2024")
        value = value.replace(",", ".")
        
        # Try DD.MM.YYYY
        for fmt in ["%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        
        logger.warning(f"Could not parse date: {value}")
    
    return None


def _parse_decimal(value) -> Optional[Decimal]:
    """
    Parse a decimal value from cell.
    
    Handles values with unit suffixes like:
    - "21828 KGS"
    - "26460.00 KGM"
    - "126000 UNT"
    - "198450.00KGM" (no space before unit)
    """
    if value is None:
        return None
    
    try:
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            # Remove commas and whitespace
            cleaned = value.replace(",", "").strip()
            if cleaned:
                # Strip unit suffixes (KGS, KGM, UNT, etc.) - common units found in balance sheets
                # Match: optional decimal number followed by optional unit letters
                unit_pattern = re.match(r'^([\d.]+)\s*[A-Za-z]*\s*$', cleaned)
                if unit_pattern:
                    cleaned = unit_pattern.group(1)
                return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        logger.warning(f"Could not parse decimal: {value}")
    
    return None


def _extract_certificate_number(row5_value: str) -> Optional[str]:
    """
    Extract certificate number from row 5.
    
    Format: "NO SURAT PENGECUALIAN PERBENDAHARAAN : CDE2/2024/00755"
    """
    if not row5_value or not isinstance(row5_value, str):
        return None
    
    # Look for the part after the colon
    if ":" in row5_value:
        return row5_value.split(":", 1)[1].strip()
    
    return row5_value.strip()


def _extract_company_name(row4_value: str) -> Optional[str]:
    """
    Extract company name from row 4.
    
    Format: "NO FAIL / NAMA PENGIMPORT : HONG LEONG YAMAHA MOTOR"
    """
    if not row4_value or not isinstance(row4_value, str):
        return None
    
    if ":" in row4_value:
        return row4_value.split(":", 1)[1].strip()
    
    return row4_value.strip()


def _extract_item_info(value: str) -> tuple[str, Optional[int]]:
    """
    Extract item name and line number from row 8 or sheet name.
    
    Format: "BOLT,FLG. (1)" or "FUEL PUMP COMP. (30)"
    Returns: (item_name, line_no)
    """
    if not value or not isinstance(value, str):
        return ("", None)
    
    value = value.strip()
    
    # Match pattern: name (number)
    match = re.match(r"^(.+?)\s*\((\d+)\)\s*$", value)
    if match:
        item_name = match.group(1).strip()
        line_no = int(match.group(2))
        return (item_name, line_no)
    
    # No line number found, return as-is
    return (value, None)


def _parse_sheet(ws: Worksheet) -> dict:
    """
    Parse a single sheet from the XLSX.
    
    Returns dict with:
    - certificate_number: str
    - company_name: str
    - item_name: str
    - line_no: int
    - approved_qty: Decimal
    - invoices: list of invoice dicts
    """
    result = {
        "certificate_number": None,
        "company_name": None,
        "exemption_date": None,
        "validity_period": None,
        "item_name": None,
        "line_no": None,
        "approved_qty": None,
        "invoices": [],
    }
    
    # Row 4: Company name
    row4_val = ws.cell(row=4, column=1).value
    if row4_val:
        result["company_name"] = _extract_company_name(str(row4_val))
    
    # Row 5: Certificate number
    row5_val = ws.cell(row=5, column=1).value
    if row5_val:
        result["certificate_number"] = _extract_certificate_number(str(row5_val))
    
    # Row 6: Exemption date
    row6_val = ws.cell(row=6, column=1).value
    if row6_val and isinstance(row6_val, str):
        result["exemption_date"] = row6_val.split(":", 1)[-1].strip() if ":" in row6_val else row6_val.strip()
    
    # Row 7: Validity period
    row7_val = ws.cell(row=7, column=1).value
    if row7_val and isinstance(row7_val, str):
        result["validity_period"] = row7_val.split(":", 1)[-1].strip() if ":" in row7_val else row7_val.strip()
    
    # Row 8: Item name and line number (Column C)
    row8_val = ws.cell(row=8, column=3).value
    if row8_val:
        item_name, line_no = _extract_item_info(str(row8_val))
        result["item_name"] = item_name
        result["line_no"] = line_no
    
    # Also try to extract from sheet name as fallback
    if result["line_no"] is None:
        sheet_name = ws.title
        if sheet_name:
            _, line_no = _extract_item_info(sheet_name)
            if line_no is not None:
                result["line_no"] = line_no
                if not result["item_name"]:
                    result["item_name"], _ = _extract_item_info(sheet_name)
    
    # Row 9: Approved quantity (Column C)
    row9_val = ws.cell(row=9, column=3).value
    result["approved_qty"] = _parse_decimal(row9_val)
    
    # Parse invoice rows starting from row 15
    # Columns: A=Date, B=Form Reg No, C=Balance Before, D=Quantity, E=Balance After
    row_idx = 15
    while True:
        date_val = ws.cell(row=row_idx, column=1).value
        form_reg_no = ws.cell(row=row_idx, column=2).value
        balance_before = ws.cell(row=row_idx, column=3).value
        quantity = ws.cell(row=row_idx, column=4).value
        balance_after = ws.cell(row=row_idx, column=5).value
        
        # Stop if we hit an empty row (no date and no form reg no)
        if date_val is None and form_reg_no is None:
            break
        
        # Skip rows without essential data
        if form_reg_no is None:
            row_idx += 1
            continue
        
        parsed_date = _parse_date(date_val)
        parsed_qty = _parse_decimal(quantity)
        parsed_before = _parse_decimal(balance_before)
        parsed_after = _parse_decimal(balance_after)
        
        if parsed_date and parsed_qty is not None:
            result["invoices"].append({
                "import_date": parsed_date,
                "form_reg_no": str(form_reg_no).strip(),
                "balance_before": parsed_before or Decimal("0"),
                "quantity_imported": parsed_qty,
                "balance_after": parsed_after or Decimal("0"),
            })
        
        row_idx += 1
        
        # Safety limit to prevent infinite loops
        if row_idx > 10000:
            logger.warning(f"Sheet {ws.title}: Hit row limit at 10000")
            break
    
    return result


def parse_xlsx_file(file_content: bytes) -> list[dict]:
    """
    Parse entire XLSX file and return list of sheet data.
    
    Args:
        file_content: Raw bytes of the XLSX file
        
    Returns:
        List of parsed sheet dictionaries
    """
    try:
        wb = load_workbook(BytesIO(file_content), data_only=True, read_only=True)
    except Exception as e:
        raise InvalidFileError(f"Failed to open XLSX file: {e}")
    
    sheets_data = []
    
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        try:
            sheet_data = _parse_sheet(ws)
            sheet_data["sheet_name"] = sheet_name
            sheets_data.append(sheet_data)
        except Exception as e:
            logger.warning(f"Failed to parse sheet '{sheet_name}': {e}")
            # Continue with other sheets
    
    wb.close()
    
    if not sheets_data:
        raise InvalidFileError("No valid sheets found in XLSX file")
    
    return sheets_data


# =============================================================================
# Preview Logic
# =============================================================================

def preview_migration(
    db: Session,
    file_content: bytes,
    port: SchemaImportPort,
    preselected_certificate: str | None = None,
    use_certificate: str | None = None,
) -> MigrationPreviewResponse:
    """
    Preview migration from XLSX file.
    
    Parses the file, matches items against database, and returns
    detailed preview with match status and duplicate detection.
    """
    # Parse the XLSX file
    sheets_data = parse_xlsx_file(file_content)
    
    # Get certificate info from first sheet
    first_sheet = sheets_data[0]
    xlsx_cert_number = first_sheet.get("certificate_number")
    xlsx_company_name = first_sheet.get("company_name")
    xlsx_exemption_date = first_sheet.get("exemption_date")
    xlsx_validity_period = first_sheet.get("validity_period")
    
    if not xlsx_cert_number:
        raise InvalidFileError("Could not extract certificate number from XLSX")
    
    # Determine which certificate to use for item matching
    # If use_certificate is specified, use that; otherwise use the XLSX cert number
    cert_for_matching = use_certificate or xlsx_cert_number
    db_certificate = mida_certificate_repo.get_certificate_by_number(db, cert_for_matching)
    
    # Check if preselected certificate differs from XLSX certificate
    preselected_cert_id = None
    certificate_mismatch = False
    if preselected_certificate and not use_certificate:
        # Only check for mismatch if we're not already forcing a certificate
        # Normalize both for comparison (handle URL encoding, case, etc.)
        presel_normalized = preselected_certificate.strip().upper()
        xlsx_normalized = xlsx_cert_number.strip().upper()
        
        if presel_normalized != xlsx_normalized:
            certificate_mismatch = True
            # Try to find the preselected certificate in DB
            presel_cert = mida_certificate_repo.get_certificate_by_number(db, preselected_certificate)
            if presel_cert:
                preselected_cert_id = presel_cert.id
    
    # Build items preview
    items_preview = []
    total_invoices = 0
    total_duplicates = 0
    matched_count = 0
    mismatch_count = 0
    not_found_count = 0
    
    # When use_certificate is specified, we skip detailed matching validation
    # and just force-import all items to the target certificate by line number
    skip_validation = use_certificate is not None
    
    # If skipping validation, pre-load items once as a dict for O(1) lookup
    db_items_by_line = {}
    if db_certificate and skip_validation:
        for item in db_certificate.items:
            db_items_by_line[item.line_no] = item
    
    for sheet_data in sheets_data:
        line_no = sheet_data.get("line_no")
        xlsx_item_name = sheet_data.get("item_name") or ""
        xlsx_approved_qty = sheet_data.get("approved_qty") or Decimal("0")
        invoices = sheet_data.get("invoices", [])
        
        total_invoices += len(invoices)
        
        # Initialize preview item
        preview_item = MigrationItemPreview(
            sheet_name=sheet_data.get("sheet_name", "Unknown"),
            line_no=line_no or 0,
            xlsx_item_name=xlsx_item_name,
            xlsx_approved_qty=xlsx_approved_qty,
            invoice_count=len(invoices),
            status=ItemMatchStatus.NOT_FOUND,
            duplicate_invoices=[],
            invoices=[
                MigrationInvoiceRow(
                    import_date=inv["import_date"],
                    form_reg_no=inv["form_reg_no"],
                    balance_before=inv["balance_before"],
                    quantity_imported=inv["quantity_imported"],
                    balance_after=inv["balance_after"],
                )
                for inv in invoices
            ],
        )
        
        # Try to find matching item in database
        if db_certificate and line_no is not None:
            # Use pre-loaded dict when skip_validation, otherwise iterate
            if skip_validation:
                db_item = db_items_by_line.get(line_no)
            else:
                db_item = None
                for item in db_certificate.items:
                    if item.line_no == line_no:
                        db_item = item
                        break
            
            if db_item:
                preview_item.db_item_id = db_item.id
                preview_item.db_item_name = db_item.item_name
                preview_item.db_approved_qty = db_item.approved_quantity
                
                # When skip_validation, always mark as matched (force import mode)
                if skip_validation:
                    preview_item.status = ItemMatchStatus.MATCHED
                    matched_count += 1
                else:
                    # Check if names match (case-insensitive, whitespace-normalized)
                    xlsx_name_normalized = " ".join(xlsx_item_name.upper().split())
                    db_name_normalized = " ".join((db_item.item_name or "").upper().split())
                    
                    if xlsx_name_normalized == db_name_normalized:
                        preview_item.status = ItemMatchStatus.MATCHED
                        matched_count += 1
                    else:
                        preview_item.status = ItemMatchStatus.NAME_MISMATCH
                        mismatch_count += 1
                
                # Note: Duplicate detection disabled - all invoices will be imported
                # since there's no reliable way to identify true duplicates
            else:
                not_found_count += 1
        else:
            not_found_count += 1
        
        items_preview.append(preview_item)
    
    return MigrationPreviewResponse(
        xlsx_certificate_number=xlsx_cert_number,
        xlsx_company_name=xlsx_company_name,
        xlsx_exemption_date=xlsx_exemption_date,
        xlsx_validity_period=xlsx_validity_period,
        db_certificate_id=db_certificate.id if db_certificate else None,
        db_certificate_number=db_certificate.certificate_number if db_certificate else None,
        certificate_found=db_certificate is not None,
        preselected_certificate=preselected_certificate if certificate_mismatch else None,
        preselected_certificate_id=preselected_cert_id,
        certificate_mismatch=certificate_mismatch,
        port=port,
        items=items_preview,
        total_items=len(items_preview),
        matched_count=matched_count,
        mismatch_count=mismatch_count,
        not_found_count=not_found_count,
        total_invoices=total_invoices,
        total_duplicates=total_duplicates,
    )


def _normalize_quantity(qty) -> str:
    """Normalize a quantity to a consistent string format for comparison."""
    if qty is None:
        return "0"
    # Convert to Decimal, normalize to remove trailing zeros, then to string
    from decimal import Decimal as D, InvalidOperation
    try:
        d = D(str(qty)).normalize()
        # Handle case where normalize() returns something like "1E+2" for 100
        if 'E' in str(d) or 'e' in str(d):
            return str(float(qty))
        return str(d)
    except (InvalidOperation, ValueError):
        return str(qty)


def _get_existing_import_keys(
    db: Session,
    item_id: UUID,
    port: str,
) -> set[tuple]:
    """
    Get set of existing import record keys for an item at a port.
    
    Each key is a tuple of (invoice_number, import_date, normalized_quantity) to uniquely
    identify an import record. This allows multiple line items from the same
    invoice with different quantities to be imported correctly.
    """
    from sqlalchemy import select
    
    stmt = (
        select(
            MidaImportRecord.declaration_form_reg_no,
            MidaImportRecord.import_date,
            MidaImportRecord.quantity_imported,
        )
        .where(MidaImportRecord.certificate_item_id == item_id)
        .where(MidaImportRecord.port == port)
        .where(MidaImportRecord.declaration_form_reg_no.isnot(None))
    )
    
    result = db.execute(stmt).all()
    # Create keys with normalized quantity for reliable comparison
    return {
        (row[0], row[1].isoformat() if row[1] else None, _normalize_quantity(row[2]))
        for row in result
    }


# =============================================================================
# Apply Logic
# =============================================================================

def apply_migration(
    db: Session,
    request: MigrationApplyRequest,
) -> MigrationApplyResponse:
    """
    Apply migration based on preview data and user resolutions.
    
    Creates synthetic import records for each invoice row,
    handling name mismatches according to user choices.
    """
    # Get certificate
    certificate = db.get(MidaCertificate, request.certificate_id)
    if not certificate:
        raise CertificateNotFoundError(f"Certificate {request.certificate_id} not found")
    
    # Build resolution lookup
    resolutions_map = {r.line_no: r.resolution for r in request.resolutions}
    
    results = []
    total_records_created = 0
    items_skipped = 0
    items_failed = 0
    
    port_value = request.port.value
    
    for item_preview in request.items:
        line_no = item_preview.line_no
        
        # Determine resolution for this item
        resolution = resolutions_map.get(line_no)
        
        # Handle based on status
        if item_preview.status == ItemMatchStatus.NOT_FOUND:
            results.append(MigrationApplyResult(
                line_no=line_no,
                item_name=item_preview.xlsx_item_name,
                status="skipped",
                error_message="Item not found in database",
            ))
            items_skipped += 1
            continue
        
        if item_preview.status == ItemMatchStatus.NAME_MISMATCH:
            if resolution is None or resolution == ConflictResolution.SKIP:
                results.append(MigrationApplyResult(
                    line_no=line_no,
                    item_name=item_preview.xlsx_item_name,
                    status="skipped",
                    error_message="Skipped by user choice" if resolution else "No resolution provided",
                ))
                items_skipped += 1
                continue
        
        # Get the database item
        db_item = db.get(MidaCertificateItem, item_preview.db_item_id)
        if not db_item:
            results.append(MigrationApplyResult(
                line_no=line_no,
                item_name=item_preview.xlsx_item_name,
                status="error",
                error_message="Database item no longer exists",
            ))
            items_failed += 1
            continue
        
        # Handle name rename if requested
        name_updated = False
        if resolution == ConflictResolution.RENAME_DB:
            db_item.item_name = item_preview.xlsx_item_name
            name_updated = True
        
        # Create import records for each invoice (no duplicate detection)
        records_created = 0
        
        for invoice in item_preview.invoices:
            # Create import record
            try:
                import_record = MidaImportRecord(
                    certificate_item_id=db_item.id,
                    import_date=invoice.import_date,
                    declaration_form_reg_no=invoice.form_reg_no,
                    quantity_imported=invoice.quantity_imported,
                    port=port_value,
                    balance_before=Decimal("0"),  # Will be recalculated
                    balance_after=Decimal("0"),   # Will be recalculated
                    remarks="Migrated from balance sheet",
                )
                db.add(import_record)
                records_created += 1
            except Exception as e:
                logger.error(f"Failed to create import record: {e}")
                items_failed += 1
        
        # Flush to get IDs, then recalculate balances
        if records_created > 0:
            db.flush()
            
            # Recalculate balances for this item/port
            mida_import_repo.recalculate_item_port_balances(db, db_item.id, port_value)
            mida_import_repo.recalculate_item_remaining_quantities(db, db_item.id)
        
        total_records_created += records_created
        
        results.append(MigrationApplyResult(
            line_no=line_no,
            item_name=db_item.item_name,
            status="success",
            records_created=records_created,
            duplicates_skipped=0,
            name_updated=name_updated,
        ))
    
    # Commit all changes
    db.commit()
    
    return MigrationApplyResponse(
        success=items_failed == 0,
        results=results,
        total_items_processed=len(request.items),
        total_records_created=total_records_created,
        total_duplicates_skipped=0,
        items_skipped=items_skipped,
        items_failed=items_failed,
        flagged_duplicates=[],
    )
