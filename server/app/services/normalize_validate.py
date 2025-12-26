import re
from typing import List, Dict, Any, Tuple

def parse_number(text: str) -> Tuple[float, str]:
    """
    Extracts number and UOM from string like "1,234.56 UNIT".
    Returns (1234.56, "UNIT").
    """
    if not text:
        return 0.0, ""
    
    # Remove commas
    clean_text = text.replace(",", "")
    
    # Regex to find the first floating point number
    # Matches 123, 123.45, .45
    match = re.search(r"[-+]?\d*\.\d+|[-+]?\d+", clean_text)
    
    if match:
        num_str = match.group(0)
        try:
            val = float(num_str)
            # Remove the number from the original text (cleaned) to get UOM
            # This is a bit rough, but works for "1234 UNIT" -> " UNIT" -> "UNIT"
            # It might fail if text is "UNIT 1234".
            
            # Let's assume UOM follows number usually.
            # We can just return the rest of the string.
            start, end = match.span()
            # Construct UOM from parts before and after?
            # Or just strip the number part?
            uom_part = clean_text[:start] + clean_text[end:]
            uom = uom_part.strip()
            
            return val, uom
        except ValueError:
            return 0.0, text
            
    return 0.0, text

def validate_items(raw_items: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    normalized_items = []
    warnings = []

    for i, item in enumerate(raw_items):
        line_no_raw = item.get("line_no", "")
        line_no = line_no_raw.strip() if isinstance(line_no_raw, str) else str(line_no_raw)
        hs_code_raw = item.get("hs_code", "")
        hs_code = hs_code_raw.strip() if isinstance(hs_code_raw, str) else str(hs_code_raw)
        item_name_raw = item.get("item_name", "")
        item_name = item_name_raw.strip() if isinstance(item_name_raw, str) else str(item_name_raw)
        
        # Check if approved_quantity is already a number (from text_quota_parser)
        existing_qty = item.get("approved_quantity")
        existing_uom = item.get("uom", "")
        
        if isinstance(existing_qty, (int, float)) and existing_qty != 0:
            qty_val = float(existing_qty)
            uom = existing_uom.strip() if isinstance(existing_uom, str) else str(existing_uom)
        else:
            # Fallback: parse from quantity_text or approved_quantity string
            qty_text = item.get("quantity_text", "")
            if not qty_text and isinstance(existing_qty, str):
                qty_text = existing_qty
            qty_text = qty_text.strip() if isinstance(qty_text, str) else ""
            qty_val, uom = parse_number(qty_text)
        
        # Normalize HS Code
        hs_code_clean = hs_code
        
        # Validation rules
        row_warnings = []
        if not hs_code_clean:
            row_warnings.append("Missing HS Code")
        if not item_name:
            row_warnings.append("Missing Item Name")
        # We don't warn on zero qty because sometimes it might be valid or parse error, 
        # but the task says "add warnings for invalid rows".
        # I'll warn if qty is 0.
        if qty_val == 0:
            row_warnings.append("Quantity is 0 or unparseable")

        if row_warnings:
            warnings.append(f"Row {i+1} (Line {line_no}): " + ", ".join(row_warnings))

        # Preserve station_split if present
        station_split = item.get("station_split")

        normalized_items.append({
            "line_no": line_no,
            "hs_code": hs_code_clean,
            "item_name": item_name,
            "approved_quantity": qty_val,
            "uom": uom,
            "station_split": station_split
        })

    return normalized_items, warnings
