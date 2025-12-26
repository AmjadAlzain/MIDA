from typing import Dict, Any, List
from app.services.azure_di_client import analyze_prebuilt_layout
from app.services.header_parser import parse_header_fields
from app.services.table_parser import parse_quota_items
from app.services.text_quota_parser import parse_quota_items_from_text
from app.services.normalize_validate import validate_items


def extract_page_texts(result, full_text: str) -> List[Dict[str, Any]]:
    """
    Extract text for each page using Azure spans.
    Returns: [{"page_no": 1, "text": "..."}, ...]
    """
    pages = getattr(result, "pages", None) or []
    if not pages:
        # Fallback: return full_text as single page
        return [{"page_no": 1, "text": full_text}]
    
    page_texts = []
    for page in pages:
        page_no = getattr(page, "page_number", len(page_texts) + 1)
        spans = getattr(page, "spans", None) or []
        
        if spans:
            # Concatenate text from all spans for this page
            page_content_parts = []
            for span in spans:
                offset = getattr(span, "offset", 0)
                length = getattr(span, "length", 0)
                if length > 0 and offset + length <= len(full_text):
                    page_content_parts.append(full_text[offset:offset + length])
            page_text = "".join(page_content_parts)
        else:
            # Fallback: can't extract per-page, skip
            page_text = ""
        
        page_texts.append({"page_no": page_no, "text": page_text})
    
    # If no page texts extracted, fallback to full text
    if not page_texts or all(not p["text"] for p in page_texts):
        return [{"page_no": 1, "text": full_text}]
    
    return page_texts


def merge_items_from_pages(page_items_list: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Merge items from multiple pages, de-duplicate by (line_no, hs_code).
    Keep first occurrence, order by numeric line_no.
    """
    seen = set()
    merged = []
    
    for items in page_items_list:
        for item in items:
            key = (item.get("line_no", ""), item.get("hs_code", ""))
            if key not in seen:
                seen.add(key)
                merged.append(item)
    
    # Sort by numeric line_no where possible
    def sort_key(item):
        try:
            return int(item.get("line_no", "0"))
        except (ValueError, TypeError):
            return 9999
    
    merged.sort(key=sort_key)
    return merged


def parse_mida_certificate(pdf_bytes: bytes) -> Dict[str, Any]:
    result = analyze_prebuilt_layout(pdf_bytes)

    full_text = getattr(result, "content", "") or ""
    header = parse_header_fields(full_text)

    table_out = parse_quota_items(result)
    raw_items = table_out["items"]

    # Fallback logic: parse page-by-page and merge
    if table_out["debug"].get("table_mode_failed"):
        page_texts = extract_page_texts(result, full_text)
        all_page_items = []
        for page_data in page_texts:
            page_items, _ = parse_quota_items_from_text(page_data["text"])
            all_page_items.append(page_items)
        merged_items = merge_items_from_pages(all_page_items)
        if merged_items:
            raw_items = merged_items

    items, warnings = validate_items(raw_items)

    return {
        **header,
        "items": items,
        "warnings": warnings
    }

def parse_mida_certificate_debug(pdf_bytes: bytes) -> Dict[str, Any]:
    result = analyze_prebuilt_layout(pdf_bytes)
    full_text = getattr(result, "content", "") or ""
    header = parse_header_fields(full_text)

    table_out = parse_quota_items(result)
    raw_items = table_out["items"]
    
    parsing_mode = "table"
    text_fallback_stats = None
    page_item_counts = []
    items_total_after_merge = len(raw_items)  # Start with table mode count

    # Extract page info
    pages = getattr(result, "pages", None) or []
    pages_count = len(pages)
    page_texts = extract_page_texts(result, full_text)
    page_text_lengths = [len(p["text"]) for p in page_texts]
    
    # Additional diagnostics
    azure_pages_seen = pages_count
    azure_content_length = len(full_text)
    first_page_excerpt = page_texts[0]["text"][:200] if page_texts and page_texts[0]["text"] else ""
    last_page_excerpt = page_texts[-1]["text"][-200:] if page_texts and page_texts[-1]["text"] else ""

    # Fallback logic: parse page-by-page and merge
    if table_out["debug"].get("table_mode_failed"):
        all_page_items = []
        combined_stats = {
            "items_found": 0,
            "qty_uom_parsed_count": 0,
            "qty_parse_fail_count": 0,
            "qty_ambiguous_count": 0,
            "qty_fail_samples": []
        }
        
        for page_data in page_texts:
            page_items, tf_stats = parse_quota_items_from_text(page_data["text"])
            all_page_items.append(page_items)
            page_item_counts.append({"page_no": page_data["page_no"], "items": len(page_items)})
            
            # Aggregate stats
            stats = tf_stats.get("text_fallback_stats", {})
            combined_stats["items_found"] += stats.get("items_found", 0)
            combined_stats["qty_uom_parsed_count"] += stats.get("qty_uom_parsed_count", 0)
            combined_stats["qty_parse_fail_count"] += stats.get("qty_parse_fail_count", 0)
            combined_stats["qty_ambiguous_count"] += stats.get("qty_ambiguous_count", 0)
            # Append fail samples (cap at 5 total)
            if len(combined_stats["qty_fail_samples"]) < 5:
                for sample in stats.get("qty_fail_samples", []):
                    if len(combined_stats["qty_fail_samples"]) < 5:
                        combined_stats["qty_fail_samples"].append(sample)
        
        merged_items = merge_items_from_pages(all_page_items)
        items_total_after_merge = len(merged_items)
        
        if merged_items:
            raw_items = merged_items
            parsing_mode = "text_fallback"
            text_fallback_stats = combined_stats

    items, warnings = validate_items(raw_items)

    # Helper for key phrases
    upper_text = full_text.upper()
    key_phrases = ["KOD HS", "KUANTITI DILULUSKAN", "NAMA DAGANGAN", "PORT KLANG", "KLIA", "BUKIT KAYU HITAM", "TE01"]
    phrases_found = {kp: (kp in upper_text) for kp in key_phrases}

    # Extract handwritten span info if available (Document Intelligence Layout model)
    handwritten_spans_count = 0
    handwritten_text_samples = []
    try:
        styles = getattr(result, "styles", None) or []
        for style in styles:
            # Check if style indicates handwriting
            is_handwritten = getattr(style, "is_handwritten", False)
            if is_handwritten:
                spans = getattr(style, "spans", []) or []
                handwritten_spans_count += len(spans)
                # Extract up to 3 short text samples from handwritten spans
                if len(handwritten_text_samples) < 3:
                    for span in spans:
                        if len(handwritten_text_samples) >= 3:
                            break
                        offset = getattr(span, "offset", 0)
                        length = getattr(span, "length", 0)
                        if length > 0 and offset + length <= len(full_text):
                            sample = full_text[offset:offset + length][:50]  # Cap at 50 chars
                            if sample.strip():
                                handwritten_text_samples.append(sample)
    except Exception:
        # Safe fallback if styles not present or different format
        pass

    return {
        **header,
        "items": items,
        "warnings": warnings,
        "debug": {
            **table_out["debug"],
            "key_phrases_found": phrases_found,
            "parsing_mode": parsing_mode,
            "text_fallback_stats": text_fallback_stats,
            "full_text_length": len(full_text),
            "pages_count": pages_count,
            "page_text_lengths": page_text_lengths,
            "page_item_counts": page_item_counts,
            "items_total_after_merge": items_total_after_merge,
            "handwritten_spans_count": handwritten_spans_count,
            "handwritten_text_samples": handwritten_text_samples,
            "azure_pages_seen": azure_pages_seen,
            "azure_content_length": azure_content_length,
            "first_page_excerpt": first_page_excerpt,
            "last_page_excerpt": last_page_excerpt
        },
        "text_sample": full_text[:8000]
    }
