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

def parse_quota_items(analyze_result: Any) -> Dict[str, Any]:
    # Check if this looks like a quota doc based on text content
    full_text = getattr(analyze_result, "content", "") or ""
    upper_text = full_text.upper()
    is_quota_doc = "KOD HS" in upper_text and "KUANTITI DILULUSKAN" in upper_text and "NAMA DAGANGAN" in upper_text

    tables = getattr(analyze_result, "tables", []) or []
    
    scored_candidates = []
    
    for i, table in enumerate(tables):
        matrix = _table_to_matrix(table)
        
        # Scan first 5 rows for header
        for r_idx in range(min(5, len(matrix))):
            row_text = " ".join(matrix[r_idx])
            score = _calculate_row_score(row_text)
            
            scored_candidates.append({
                "table_idx": i,
                "row_idx": r_idx,
                "score": score,
                "header_preview": row_text,
                "matrix": matrix
            })

    # Sort by score descending
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    
    debug_table_headers = [
        {
            "index": c["table_idx"],
            "row": c["row_idx"], 
            "score": c["score"], 
            "header_preview": c["header_preview"][:100]
        }
        for c in scored_candidates
    ]

    target_matrix = None
    target_table_idx = -1
    header_row_idx = -1
    debug_reason = "No tables found or score too low"

    # Selection threshold (at least score >= 2 to be reasonably confident)
    if scored_candidates:
        best = scored_candidates[0]
        if best["score"] >= 2: 
            target_matrix = best["matrix"]
            target_table_idx = best["table_idx"]
            header_row_idx = best["row_idx"]
            debug_reason = f"Selected table {target_table_idx} row {header_row_idx} with score {best['score']}"

    if not target_matrix:
        return {
            "items": [], 
            "debug": {
                "tables_found": len(tables),
                "table_index": -1, 
                "reason": debug_reason,
                "table_headers": debug_table_headers,
                "matrix_sample": [],
                "table_mode_failed": is_quota_doc # True if it looks like quota doc but table failed
            }
        }

    # Identify columns from header row
    header_row = target_matrix[header_row_idx]
    col_map = {
        "line_no": -1,
        "hs_code": -1,
        "item_name": -1,
        "qty": -1,
        "uom": -1
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

    items = []
    
    # Iterate rows after header
    for r in range(header_row_idx + 1, len(target_matrix)):
        row = target_matrix[r]
        if not "".join(row).strip():
            continue
            
        def get_col(idx):
            return row[idx] if idx != -1 and 0 <= idx < len(row) else ""

        line_no = get_col(col_map["line_no"])
        hs_code = get_col(col_map["hs_code"])
        item_name = get_col(col_map["item_name"])
        qty_text = get_col(col_map["qty"])
        uom = get_col(col_map["uom"])
        
        # Fallback if specific columns not mapped, but table was identified
        if col_map["hs_code"] == -1 and col_map["item_name"] == -1:
             # Heuristic: 0=line, 1=HS, 2=Desc, 3=Qty
             if len(row) > 1: hs_code = row[1]
             if len(row) > 2: item_name = row[2]
             if len(row) > 3: qty_text = row[3]

        if not hs_code and not item_name and not qty_text:
            continue

        items.append({
            "line_no": line_no,
            "hs_code": hs_code,
            "item_name": item_name,
            "approved_quantity": qty_text, # User asked for "approved_quantity"
            "uom": uom
        })

    # Determine if table mode "failed" (yielded 0 items despite being a quota doc)
    table_mode_failed = False
    if is_quota_doc and len(items) == 0:
        table_mode_failed = True

    return {
        "items": items, 
        "debug": {
            "tables_found": len(tables),
            "table_index": target_table_idx, 
            "reason": debug_reason,
            "table_headers": debug_table_headers,
            "matrix_sample": target_matrix[:8],
            "table_mode_failed": table_mode_failed
        }
    }
