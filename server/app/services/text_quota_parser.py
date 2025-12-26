import re
from typing import List, Dict, Any, Tuple, Optional

def parse_number(s: str) -> Optional[float]:
    """Strip, remove commas, allow decimals, return float or None."""
    try:
        cleaned = s.strip().replace(",", "")
        if not cleaned:
            return None
        return float(cleaned)
    except ValueError:
        return None

def normalize_uom(uom: str) -> str:
    """Normalize UOM: kg -> KGM, u -> UNIT."""
    uom_upper = uom.upper().strip()
    if uom_upper in ("KG", "K.G", "KGS", "KGM"):
        return "KGM"
    if uom_upper in ("U", "UNIT", "UNITS", "PCS", "PC"):
        return "UNIT"
    return uom_upper

# Patterns for handwriting/edit marker detection
EDIT_MARKER_PATTERN = re.compile(r"[<>{}\\/]{2,}|x{3,}|/{3,}|[\u2190\u2192\u2194]", re.IGNORECASE)
# UOM detection pattern (case-insensitive)
UOM_PATTERN = re.compile(r"\b(kg|k\.g|kgs|kgm|unit|units|u|pcs|pc)\b", re.IGNORECASE)
# Numeric token extraction pattern
NUMERIC_TOKEN_PATTERN = re.compile(r"[\d,]+(?:\.\d+)?")

def is_line_ambiguous(line: str, numeric_tokens: List[str]) -> bool:
    """
    Detect if line is ambiguous due to handwriting/noise.
    Returns True if ambiguous (should leave empty for manual review).
    """
    # If 2+ numeric tokens AND has edit markers -> potentially ambiguous
    if len(numeric_tokens) >= 2:
        if EDIT_MARKER_PATTERN.search(line):
            return True
        # Lots of letters (excluding UOM) can indicate handwriting noise
        text_no_uom = UOM_PATTERN.sub("", line)
        letter_count = len(re.findall(r"[a-zA-Z]", text_no_uom))
        if letter_count > 10:
            return True
    return False

def choose_best_numeric_token(tokens: List[str]) -> Optional[float]:
    """
    Choose the best numeric token from a list.
    Prefer the last comma-containing token (handles crossed-out amendments).
    Otherwise choose the largest value.
    """
    if not tokens:
        return None
    
    # Find tokens with commas (likely formatted numbers)
    comma_tokens = [t for t in tokens if "," in t]
    if comma_tokens:
        # Prefer the last comma-containing token (amended value)
        return parse_number(comma_tokens[-1])
    
    # No comma tokens - choose largest value
    values = []
    for t in tokens:
        v = parse_number(t)
        if v is not None:
            values.append(v)
    return max(values) if values else None

def is_clean_qty(token: str, value: float) -> bool:
    """
    Check if a qty token looks 'clean' (has comma grouping or typical format).
    Used for ambiguous lines to decide if we should accept the value.
    """
    # Has comma grouping -> clean
    if "," in token:
        return True
    # Has decimal point -> likely clean
    if "." in token:
        return True
    # Large round number without formatting is suspicious
    if value > 1000 and "," not in token:
        return False
    return True

def parse_qty_uom(line: str) -> Tuple[Optional[float], str, bool]:
    """Parse a line for quantity and optional UOM.
    Works with noisy lines containing handwriting/stamps.
    
    Returns (qty_float, normalized_uom, is_ambiguous).
    - is_ambiguous=True means qty was left empty due to unclear OCR.
    """
    # Extract all numeric tokens from the line
    numeric_tokens = NUMERIC_TOKEN_PATTERN.findall(line)
    
    # Filter out very small tokens (likely noise like "0" standalone)
    numeric_tokens = [t for t in numeric_tokens if parse_number(t) is not None]
    
    if not numeric_tokens:
        return (None, "", False)
    
    # Detect UOM anywhere in the line
    uom_match = UOM_PATTERN.search(line)
    uom = ""
    if uom_match:
        uom = normalize_uom(uom_match.group(1))
    
    # Check for ambiguity
    ambiguous = is_line_ambiguous(line, numeric_tokens)
    
    # Choose best numeric token
    best_token = None
    best_value = None
    
    # Find the token we're choosing
    comma_tokens = [t for t in numeric_tokens if "," in t]
    if comma_tokens:
        best_token = comma_tokens[-1]
        best_value = parse_number(best_token)
    else:
        # Find largest
        best_value = 0.0
        for t in numeric_tokens:
            v = parse_number(t)
            if v is not None and v > best_value:
                best_value = v
                best_token = t
    
    if best_value is None or best_value == 0:
        return (None, "", False)
    
    # If ambiguous, only accept if the chosen value is "clean"
    if ambiguous:
        if best_token and not is_clean_qty(best_token, best_value):
            # Leave empty for manual review
            return (None, "", True)
    
    return (best_value, uom, ambiguous)

def parse_quota_items_from_text(full_text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    
    items = []
    qty_uom_parsed_count = 0
    qty_parse_fail_count = 0
    qty_ambiguous_count = 0
    qty_fail_samples = []  # Debug samples for failed qty parsing (max 5)
    
    # Regex patterns
    hs_code_pattern = re.compile(r"\b\d{4}\.\d{2}\.\d{4}\b")
    
    # Lines that indicate page headers/footers to skip when looking for item data
    skip_line_patterns = [
        r"PERAKUAN SYARIKAT",
        r"COMPANY'S DECLARATION",
        r"PENENTUAN DAN PENGAGIHAN",
        r"Determination and distribution",
        r"Borang TE01",
        r"Form TE01",
        r"UNTUK KEGUNAAN RASMI",
        r"FOR OFFICIAL USE",
        r"Nama Syarikat",
        r"Company'?s Name",
        r"Treasury Exemption",
        r"No Ruj Kelulusan",
        r"Tempoh Kelulusan",
        r"Approved Period",
        r"PORT KLANG",
        r"^\s*KLIA\s*$",
        r"BUKIT KAYU HITAM"
    ]
    skip_re = re.compile("|".join(skip_line_patterns), re.IGNORECASE)

    # Collect ALL HS code indices first (don't stop at page footers)
    hs_indices = []
    for i, line in enumerate(lines):
        # Check for HS Code
        if hs_code_pattern.search(line):
            hs_indices.append(i)

    # Process each block around HS code
    processed_items = []
    
    for idx_in_list, hs_idx in enumerate(hs_indices):
        # 1. HS Code
        hs_line = lines[hs_idx]
        hs_match = hs_code_pattern.search(hs_line)
        hs_code = hs_match.group(0) if hs_match else ""
        
        # 2. Approved Quantity - scan forward to find qty line
        # Prefer a line that has qty AND uom (letters). 
        # If none has uom, accept first numeric-only line.
        approved_quantity = 0.0
        uom = ""
        approved_qty_line_idx = -1
        was_ambiguous = False
        raw_candidate_lines = []  # For debug
        
        # Determine search boundary (up to next item or end of lines)
        search_end = len(lines)
        if idx_in_list + 1 < len(hs_indices):
            search_end = hs_indices[idx_in_list + 1]
        
        # Scan forward from hs_idx + 1 to find approved qty
        candidate_with_uom = None
        candidate_numeric_only = None
        
        for scan_idx in range(hs_idx + 1, min(search_end, hs_idx + 10)):
            if scan_idx >= len(lines):
                break
            scan_line = lines[scan_idx]
            raw_candidate_lines.append(scan_line)
            parsed_qty, parsed_uom, is_ambig = parse_qty_uom(scan_line)
            if parsed_qty is not None:
                if parsed_uom:  # Has UOM - prefer this
                    if candidate_with_uom is None:
                        candidate_with_uom = (scan_idx, parsed_qty, parsed_uom, is_ambig)
                    break  # Found one with UOM, use it
                else:  # Numeric only
                    if candidate_numeric_only is None:
                        candidate_numeric_only = (scan_idx, parsed_qty, parsed_uom, is_ambig)
            elif is_ambig:
                # Line was ambiguous - record for potential warning
                was_ambiguous = True
        
        # Choose best candidate
        if candidate_with_uom:
            approved_qty_line_idx, approved_quantity, uom, was_ambiguous = candidate_with_uom
            qty_uom_parsed_count += 1
            if was_ambiguous:
                qty_ambiguous_count += 1
        elif candidate_numeric_only:
            approved_qty_line_idx, approved_quantity, uom, was_ambiguous = candidate_numeric_only
            qty_uom_parsed_count += 1
            if was_ambiguous:
                qty_ambiguous_count += 1
        else:
            qty_parse_fail_count += 1
            # Add debug sample (max 5)
            if len(qty_fail_samples) < 5:
                qty_fail_samples.append({
                    "line_no": "",  # Will be filled later
                    "hs_code": hs_code,
                    "raw_candidate_lines": raw_candidate_lines[:5]
                })
        
        station_start_idx = approved_qty_line_idx + 1 if approved_qty_line_idx != -1 else hs_idx + 1

        # 3. Station Quantities (lines after qty)
        # Find boundary for this item (next HS code or end of document)
        next_boundary = len(lines)
        if idx_in_list + 1 < len(hs_indices):
            next_hs_idx = hs_indices[idx_in_list + 1]
            next_boundary = next_hs_idx

        # 3. Station splits - collect subsequent numeric-only lines (max 3 stations)
        # Station values are typically large decimals, line numbers are small integers
        station_values = []
        current_scan_idx = station_start_idx
        
        # Pattern to detect numbered headings like "9." or "10." (these are section headers, not station values)
        numbered_heading_pattern = re.compile(r"^\s*\d{1,2}\.\s*$")
        # Declaration keywords to skip
        declaration_keywords = ["PERAKUAN", "DECLARATION", "SYARIKAT", "COMPANY"]
        
        while current_scan_idx < next_boundary and current_scan_idx < len(lines) and len(station_values) < 3:
            line_val = lines[current_scan_idx]
            
            # Skip numbered headings like "9." or "10."
            if numbered_heading_pattern.match(line_val):
                break
            
            # Skip lines containing declaration keywords
            line_upper = line_val.upper()
            if any(kw in line_upper for kw in declaration_keywords):
                break
            
            parsed_station_qty, parsed_station_uom, _ = parse_qty_uom(line_val)
            # Only accept numeric-only lines (no UOM) for stations
            if parsed_station_qty is not None and not parsed_station_uom:
                # Heuristic: Ignore small integers (<= 100) without decimals
                # They are likely line numbers or OCR junk, not station values
                # Accept station values if: have decimals OR are large (>100) OR have commas
                has_decimal = "." in line_val.strip()
                has_comma = "," in line_val.strip()
                is_small_int = (parsed_station_qty <= 100 and 
                               parsed_station_qty == int(parsed_station_qty) and
                               not has_decimal)
                
                if is_small_int and not has_comma:
                    # This looks like a line number or junk, stop collecting
                    break
                    
                station_values.append(parsed_station_qty)
                current_scan_idx += 1
            else:
                # Not a pure numeric line, stop collecting stations
                break
                
        # Map stations: PORT_KLANG, KLIA, BUKIT_KAYU_HITAM (in order)
        # Always include all 3 keys, even if values are null
        station_split = {
            "PORT_KLANG": None,
            "KLIA": None,
            "BUKIT_KAYU_HITAM": None
        }
        if len(station_values) >= 1:
            station_split["PORT_KLANG"] = station_values[0] if station_values[0] else None
        if len(station_values) >= 2:
            # 2 values: PORT_KLANG and BUKIT_KAYU_HITAM (KLIA empty)
            station_split["BUKIT_KAYU_HITAM"] = station_values[1] if station_values[1] else None
        if len(station_values) >= 3:
            # 3 values: shift BUKIT_KAYU_HITAM to position 3, KLIA at position 2
            station_split["KLIA"] = station_values[1] if station_values[1] else None
            station_split["BUKIT_KAYU_HITAM"] = station_values[2] if station_values[2] else None
            
        # 4. Item Name and Line No
        # They are before HS code.
        # How far back? Until previous item's stations ended?
        # Or if first item, until headers?
        
        # Determine start of this item block
        # If previous item existed, its block ended at 'prev_station_end_idx'
        # We can calculate 'prev_end_idx' from previous loop, or look at hs_indices[idx-1]
        
        # Let's look backwards from HS code
        # We expect:
        # HS Code
        # Name Line K
        # ...
        # Name Line 1
        # Line No
        
        # We scan backwards for line_no. Line_no is typically an integer.
        # But wait, sometimes name contains numbers. 
        # Requirement: "line_no" is the first thing in the block.
        
        # Let's try to find the line_no line.
        # It should be a small integer.
        
        item_name_lines = []
        line_no = ""
        
        # Search backwards from hs_idx - 1
        curr_back = hs_idx - 1
        found_line_no = False
        
        # Limit backward search to avoid going into previous item
        # Previous item roughly ends at... well, if we processed sequentially, we know where we stopped.
        # But we are doing random access via HS indices.
        # Let's limit backward search to say 10 lines or until we see something that looks like a station/qty of prev item.
        
        limit_idx = 0
        if idx_in_list > 0:
            # Previous HS index
            limit_idx = hs_indices[idx_in_list - 1] + 1 
            # +1 is just after prev HS. But prev item has qty and stations.
            # So effectively we shouldn't go past prev HS code.
        
        while curr_back >= limit_idx:
            txt = lines[curr_back]
            # Check if this is line_no
            # Regex for simple number, maybe with dot? "1" or "1."
            if re.match(r"^\d+\.?$", txt):
                line_no = txt.replace(".", "")
                found_line_no = True
                break
            
            # Add to name (prepend)
            item_name_lines.insert(0, txt)
            curr_back -= 1
            
        item_name = " ".join(item_name_lines)
        
        # Update debug sample with line_no if this was a fail case
        for sample in qty_fail_samples:
            if sample["hs_code"] == hs_code and sample["line_no"] == "":
                sample["line_no"] = line_no
        
        processed_items.append({
            "line_no": line_no,
            "hs_code": hs_code,
            "item_name": item_name,
            "approved_quantity": approved_quantity,
            "uom": uom,
            "station_split": station_split
        })

    debug_info = {
        "text_fallback_stats": {
            "items_found": len(processed_items),
            "hs_code_indices": hs_indices,
            "first_line_no": processed_items[0]["line_no"] if processed_items else None,
            "last_line_no": processed_items[-1]["line_no"] if processed_items else None,
            "qty_uom_parsed_count": qty_uom_parsed_count,
            "qty_parse_fail_count": qty_parse_fail_count,
            "qty_ambiguous_count": qty_ambiguous_count,
            "qty_fail_samples": qty_fail_samples
        }
    }
    
    return processed_items, debug_info
