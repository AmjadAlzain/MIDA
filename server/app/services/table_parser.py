import re
from typing import Any, List, Dict, Optional

def _table_to_matrix(table: Any) -> List[List[str]]:
    # Find dimensions
    max_row = 0
    max_col = 0
    for cell in table.cells:
        r = getattr(cell, "row_index", 0)
        c = getattr(cell, "column_index", 0)
        max_row = max(max_row, r)
        max_col = max(max_col, c)

    matrix = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]

    for cell in table.cells:
        r = getattr(cell, "row_index", 0)
        c = getattr(cell, "column_index", 0)
        content = getattr(cell, "content", "").strip()
        matrix[r][c] = content
    
    return matrix

def _calculate_row_score(row_text: str) -> float:
    text = row_text.upper()
    score = 0.0
    
    # 1. HS Code
    # ("kod"+"hs") or just "hs"
    if "KOD HS" in text or "HS CODE" in text:
        score += 3
    elif re.search(r"\bHS\b", text):
        score += 1
        
    # 2. Quantity
    # ("kuantiti"+"diluluskan") or ("approved"+"quantity")
    if "KUANTITI DILULUSKAN" in text or "APPROVED QUANTITY" in text:
        score += 3
    elif "KUANTITI" in text or "QUANTITY" in text:
        score += 1
        
    # 3. Item Name
    # ("nama"+"dagangan") or ("name"+"goods")
    if "NAMA DAGANGAN" in text or "NAME OF GOODS" in text:
        score += 3
    elif "NAMA" in text or "DAGANGAN" in text or "DESCRIPTION" in text:
        score += 1
        
    return score


def _normalize_uom(uom_text: str) -> str:
    """Normalize UOM: kg variants -> KGM, unit variants -> UNIT."""
    uom_upper = uom_text.upper().strip()
    if uom_upper in ("KG", "K.G", "KGS", "KGM"):
        return "KGM"
    if uom_upper in ("U", "UNIT", "UNITS", "PCS", "PC"):
        return "UNIT"
    return uom_upper


def _parse_qty_and_uom(qty_text: str, uom_text: str) -> tuple:
    """
    Parse quantity and UOM from cell texts.
    Handles cases where UOM is embedded in qty cell (e.g., "1,234.00 kg").
    Returns (float_qty, normalized_uom).
    """
    qty_str = qty_text.strip()
    uom_str = uom_text.strip()
    
    # Check if qty cell contains UOM suffix
    uom_pattern = re.compile(r"\b(kg|k\.g|kgs|kgm|unit|units|u|pcs|pc)\b", re.IGNORECASE)
    uom_match = uom_pattern.search(qty_str)
    if uom_match and not uom_str:
        uom_str = uom_match.group(1)
        # Remove UOM from qty string
        qty_str = uom_pattern.sub("", qty_str).strip()
    
    # Parse quantity
    try:
        cleaned = qty_str.replace(",", "").strip()
        qty_float = float(cleaned) if cleaned else 0.0
    except ValueError:
        qty_float = 0.0
    
    return qty_float, _normalize_uom(uom_str)


def _get_table_page_number(table: Any) -> Optional[int]:
    """Get page number from table's bounding regions if available."""
    try:
        regions = getattr(table, "bounding_regions", None) or []
        if regions:
            return getattr(regions[0], "page_number", None)
    except Exception:
        pass
    return None


def _find_station_subheader_row(matrix: List[List[str]], start_row: int) -> Optional[int]:
    """
    Find the row containing station sub-headers (PORT KLANG, KLIA, BUKIT KAYU HITAM).
    Search within a few rows after start_row.
    Returns row index or None.
    """
    for r_idx in range(start_row, min(start_row + 4, len(matrix))):
        row_text = " ".join(matrix[r_idx]).upper()
        # Station sub-header row should have at least PORT KLANG
        if "PORT KLANG" in row_text or "PELABUHAN KLANG" in row_text:
            return r_idx
    return None


def _extract_amended_number(text: str) -> Optional[float]:
    """
    Extract a number from text that may contain amendment artifacts.
    Amended cells often have patterns like:
    - "239073.760 <<<<< 239,871.00" (crossed out with arrows pointing to new value)
    - "239,8738 JABATAK 239,871 200 15g" (stamp text mixed with numbers)
    
    Strategy: Find all numeric tokens and prefer:
    1. The last clean comma-formatted number (likely the amended/new value)
    2. Otherwise the largest value
    """
    if not text:
        return None
    
    # Remove common stamp/noise text
    cleaned = re.sub(r'[<>]{2,}', ' ', text)  # Remove arrow markers like <<<<<
    cleaned = re.sub(r'\b[A-Z]{3,}\b', ' ', cleaned)  # Remove all-caps words (stamp text)
    
    # Find all numeric tokens (with commas and decimals)
    numeric_pattern = re.compile(r'[\d,]+(?:\.\d+)?')
    tokens = numeric_pattern.findall(cleaned)
    
    if not tokens:
        return None
    
    # Parse all tokens
    parsed = []
    for t in tokens:
        try:
            val = float(t.replace(',', ''))
            if val > 0:
                parsed.append((t, val))
        except ValueError:
            pass
    
    if not parsed:
        return None
    
    # Prefer comma-formatted tokens (more likely to be intentional values)
    comma_tokens = [(t, v) for t, v in parsed if ',' in t]
    if comma_tokens:
        # Return the last comma-formatted value (likely the amended value)
        return comma_tokens[-1][1]
    
    # No comma tokens - return the largest value
    return max(v for _, v in parsed)


def _parse_single_table(table: Any, table_idx: int, fallback_col_map: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Parse a single table and return items + debug info.
    If fallback_col_map is provided, use it when no header row is found (continuation table).
    Returns: {"items": [...], "header_row_idx": int, "score": float, "col_map": {...}}
    """
    matrix = _table_to_matrix(table)
    
    # Find best header row in first 8 rows (extended from 5)
    best_header_idx = -1
    best_score = 0.0
    
    for r_idx in range(min(8, len(matrix))):
        row_text = " ".join(matrix[r_idx])
        score = _calculate_row_score(row_text)
        if score > best_score:
            best_score = score
            best_header_idx = r_idx
    
    # Determine column mapping
    col_map = None
    data_start_row = 0
    station_subheader_idx = None
    
    if best_score >= 2 and best_header_idx >= 0:
        # Has a proper header row
        header_row = matrix[best_header_idx]
        col_map = {
            "line_no": -1,
            "hs_code": -1,
            "item_name": -1,
            "qty": -1,
            "uom": -1,
            "port_klang": -1,
            "klia": -1,
            "bukit_kayu_hitam": -1
        }

        for c_idx, text in enumerate(header_row):
            t = text.upper()
            if "BIL" in t or "NO." in t:
                col_map["line_no"] = c_idx
            elif "KOD HS" in t or "HS CODE" in t or re.search(r"\bHS\b", t):
                col_map["hs_code"] = c_idx
            elif "NAMA" in t or "DAGANGAN" in t or "GOODS" in t or "DESCRIPTION" in t:
                col_map["item_name"] = c_idx
            elif "KUANTITI" in t or "QUANTITY" in t:
                col_map["qty"] = c_idx
            elif "UNIT" in t or "UOM" in t:
                col_map["uom"] = c_idx
            elif "PORT KLANG" in t or "PELABUHAN KLANG" in t:
                col_map["port_klang"] = c_idx
            elif "KLIA" in t:
                col_map["klia"] = c_idx
            elif "BUKIT KAYU HITAM" in t:
                col_map["bukit_kayu_hitam"] = c_idx
        
        data_start_row = best_header_idx + 1
        
        # If station columns not found in main header, look for sub-header row
        if col_map["port_klang"] == -1:
            station_subheader_idx = _find_station_subheader_row(matrix, best_header_idx + 1)
            if station_subheader_idx is not None:
                subheader_row = matrix[station_subheader_idx]
                for c_idx, text in enumerate(subheader_row):
                    t = text.upper().strip()
                    if "PORT KLANG" in t or "PELABUHAN KLANG" in t:
                        col_map["port_klang"] = c_idx
                    elif t == "KLIA" or "KLIA" in t:
                        col_map["klia"] = c_idx
                    elif "BUKIT KAYU HITAM" in t:
                        col_map["bukit_kayu_hitam"] = c_idx
                # Data starts after the station sub-header
                data_start_row = station_subheader_idx + 1
    elif fallback_col_map:
        # No header but we have a fallback column map - this is a continuation table
        col_map = fallback_col_map.copy()
        data_start_row = 0  # Start from row 0 since no header
        best_score = 0.5  # Mark as continuation table
    else:
        # No header and no fallback - check if table contains HS codes (data table)
        hs_pattern = re.compile(r"\d{4}\.\d{2}\.\d{4}")
        has_hs_codes = False
        for row in matrix:
            for cell in row:
                if hs_pattern.search(cell):
                    has_hs_codes = True
                    break
            if has_hs_codes:
                break
        
        if not has_hs_codes:
            return {"items": [], "header_row_idx": -1, "score": best_score, "col_map": {}}
        
        # Has HS codes but no header - use default column positions
        col_map = {
            "line_no": 0,
            "hs_code": 1,
            "item_name": 2,
            "qty": 3,
            "uom": -1,
            "port_klang": -1,
            "klia": -1,
            "bukit_kayu_hitam": -1
        }
        data_start_row = 0
        best_score = 0.5  # Mark as inferred table

    items = []
    
    # Patterns to detect declaration/signature rows (not valid items)
    declaration_patterns = [
        r'Nama\s*/\s*Name',
        r'Jawatan\s*/\s*Designation',
        r'Tarikh\s*/\s*Date',
        r'PERAKUAN\s+SYARIKAT',
        r"COMPANY'?S?\s+DECLARATION",
    ]
    declaration_re = re.compile('|'.join(declaration_patterns), re.IGNORECASE)
    
    # Helper functions defined once
    def get_col(row, idx):
        return row[idx] if idx != -1 and 0 <= idx < len(row) else ""
    
    def clean_ocr_artifacts(text: str) -> str:
        """Remove Azure Document Intelligence OCR artifacts like :unselected:, :selected:"""
        return re.sub(r':(?:un)?selected:', '', text, flags=re.IGNORECASE).strip()
    
    def parse_station_value(row, idx):
        val_str = get_col(row, idx)
        val_str = re.sub(r':(?:un)?selected:', '', val_str, flags=re.IGNORECASE)
        # Try extracting from amended text first
        amended_val = _extract_amended_number(val_str)
        if amended_val is not None:
            return amended_val
        # Fallback to simple parsing
        val_str = val_str.replace(",", "").strip()
        try:
            return float(val_str) if val_str else None
        except ValueError:
            return None
    
    # Iterate rows and handle continuation rows
    for r in range(data_start_row, len(matrix)):
        row = matrix[r]
        if not "".join(row).strip():
            continue
        
        # Skip declaration/signature rows
        row_text = " ".join(row)
        if declaration_re.search(row_text):
            continue

        line_no = get_col(row, col_map["line_no"])
        hs_code = clean_ocr_artifacts(get_col(row, col_map["hs_code"]))
        item_name = clean_ocr_artifacts(get_col(row, col_map["item_name"]))
        qty_text = clean_ocr_artifacts(get_col(row, col_map["qty"]))
        uom_text = get_col(row, col_map["uom"])
        
        # Fallback if specific columns not mapped
        if col_map["hs_code"] == -1 and col_map["item_name"] == -1:
            if len(row) > 1: hs_code = row[1]
            if len(row) > 2: item_name = row[2]
            if len(row) > 3: qty_text = row[3]

        # Check if this is a continuation row (no line_no but has data)
        line_no_stripped = line_no.strip()
        is_continuation = False
        
        if not line_no_stripped:
            # No line number - this might be a continuation row
            has_hs = bool(hs_code)
            has_station = any([
                get_col(row, col_map["port_klang"]).strip(),
                get_col(row, col_map["klia"]).strip(),
                get_col(row, col_map["bukit_kayu_hitam"]).strip()
            ])
            if (has_hs or has_station) and items:
                is_continuation = True
        
        if is_continuation:
            # Merge this row's data into the previous item
            prev_item = items[-1]
            
            # Fill in missing HS code
            if not prev_item["hs_code"] and hs_code:
                prev_item["hs_code"] = hs_code
            
            # Fill in missing quantity (try amended extraction)
            if prev_item["approved_quantity"] == 0 and qty_text:
                amended_qty = _extract_amended_number(qty_text)
                if amended_qty:
                    prev_item["approved_quantity"] = amended_qty
                else:
                    qty_val, uom_val = _parse_qty_and_uom(qty_text, uom_text)
                    if qty_val > 0:
                        prev_item["approved_quantity"] = qty_val
                        if uom_val and not prev_item["uom"]:
                            prev_item["uom"] = uom_val
            
            # Fill in missing station values
            for station_key, col_key in [
                ("PORT_KLANG", "port_klang"),
                ("KLIA", "klia"),
                ("BUKIT_KAYU_HITAM", "bukit_kayu_hitam")
            ]:
                if prev_item["station_split"][station_key] is None:
                    val = parse_station_value(row, col_map[col_key])
                    if val is not None:
                        prev_item["station_split"][station_key] = val
            continue
        
        if not hs_code and not item_name and not qty_text:
            continue
        
        # Skip rows that look like declaration fields (line_no contains declaration text)
        if declaration_re.search(line_no):
            continue
        
        # Skip rows with invalid line numbers (containing : but not a digit, or text-based)
        # Valid line_no should be a simple integer like "1", "20", "100"
        if line_no_stripped:
            # If line_no contains ':' it's likely a label not an item number
            if ':' in line_no_stripped:
                continue
            # If line_no is not purely numeric (with optional dot), skip
            if not re.match(r'^\d+\.?$', line_no_stripped):
                continue

        # Parse and normalize qty/uom - try amended extraction first
        amended_qty = _extract_amended_number(qty_text)
        if amended_qty is not None:
            approved_quantity = amended_qty
            # Try to get UOM from text
            uom_match = re.search(r'\b(kg|kgm|unit|units|u|pcs)\b', qty_text, re.IGNORECASE)
            uom = _normalize_uom(uom_match.group(1)) if uom_match else ""
        else:
            approved_quantity, uom = _parse_qty_and_uom(qty_text, uom_text)
        
        # Skip rows with empty line_no unless they have valid HS code or qty
        # This catches stray signature/name rows
        if not line_no_stripped:
            if not hs_code and approved_quantity == 0:
                continue
        
        # Parse station split - always include all 3 keys
        station_split = {
            "PORT_KLANG": parse_station_value(row, col_map["port_klang"]),
            "KLIA": parse_station_value(row, col_map["klia"]),
            "BUKIT_KAYU_HITAM": parse_station_value(row, col_map["bukit_kayu_hitam"])
        }

        items.append({
            "line_no": line_no.strip(),
            "hs_code": hs_code.strip(),
            "item_name": item_name.strip(),
            "approved_quantity": approved_quantity,
            "uom": uom,
            "station_split": station_split
        })

    return {
        "items": items,
        "header_row_idx": best_header_idx,
        "score": best_score,
        "col_map": col_map
    }


def parse_quota_items(analyze_result: Any) -> Dict[str, Any]:
    # Check if this looks like a quota doc based on text content
    full_text = getattr(analyze_result, "content", "") or ""
    upper_text = full_text.upper()
    is_quota_doc = "KOD HS" in upper_text and "KUANTITI DILULUSKAN" in upper_text and "NAMA DAGANGAN" in upper_text

    tables = getattr(analyze_result, "tables", []) or []
    
    # Two-pass approach:
    # 1. First pass: find tables with headers (score >= 2) and get their column mappings
    # 2. Second pass: parse all tables, using fallback column mapping for headerless tables
    
    SCORE_THRESHOLD = 2
    table_stats = []
    
    # First pass: find the best column mapping from a header table
    best_col_map = None
    best_col_map_score = 0
    
    for i, table in enumerate(tables):
        parsed = _parse_single_table(table, i, fallback_col_map=None)
        if parsed["score"] >= SCORE_THRESHOLD and parsed["col_map"]:
            if parsed["score"] > best_col_map_score:
                best_col_map = parsed["col_map"]
                best_col_map_score = parsed["score"]
    
    # Second pass: parse all tables using the fallback column mapping
    selected_tables = []
    
    for i, table in enumerate(tables):
        parsed = _parse_single_table(table, i, fallback_col_map=best_col_map)
        page_no = _get_table_page_number(table)
        
        stat = {
            "index": i,
            "page_no": page_no,
            "score": parsed["score"],
            "items_found": len(parsed["items"]),
            "has_header": parsed["score"] >= SCORE_THRESHOLD
        }
        table_stats.append(stat)
        
        # Accept tables that have items (either with header or using fallback)
        if parsed["items"]:
            selected_tables.append({
                "index": i,
                "page_no": page_no,
                "score": parsed["score"],
                "items": parsed["items"]
            })
    
    # Merge all items from selected tables
    seen = set()
    merged_items = []
    
    for tbl in selected_tables:
        for item in tbl["items"]:
            key = (item.get("line_no", ""), item.get("hs_code", ""))
            if key not in seen:
                seen.add(key)
                merged_items.append(item)
    
    # Sort by numeric line_no
    def sort_key(item):
        try:
            return int(item.get("line_no", "0"))
        except (ValueError, TypeError):
            return 9999
    
    merged_items.sort(key=sort_key)
    
    # Build debug info
    table_indices_selected = [t["index"] for t in selected_tables]
    tables_selected_count = len(selected_tables)
    
    # Determine if table mode "failed"
    table_mode_failed = False
    if is_quota_doc and len(merged_items) == 0:
        table_mode_failed = True

    return {
        "items": merged_items, 
        "debug": {
            "tables_found": len(tables),
            "table_index": table_indices_selected[0] if table_indices_selected else -1,
            "table_indices_selected": table_indices_selected,
            "tables_selected_count": tables_selected_count,
            "table_stats": table_stats,
            "reason": f"Selected {tables_selected_count} tables ({len([t for t in table_stats if t['has_header']])} with headers, {len([t for t in table_stats if not t['has_header'] and t['items_found'] > 0])} continuation)",
            "table_mode_failed": table_mode_failed,
            "items_total_after_merge": len(merged_items)
        }
    }
