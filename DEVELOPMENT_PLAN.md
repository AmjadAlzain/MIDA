# MIDA Project – Development Plan (Azure OCR)

## What we have so far (Phase 1 & 2 done)
- Repo scaffolded similar to Form-D-demo:
  - `server/` FastAPI backend
  - `web/` simple HTML upload page
- Endpoints:
  - `POST /api/mida/certificate/certificate/parse` - Production parsing
  - `POST /api/mida/certificate/certificate/parse-debug` - Debug parsing with stats

## ✅ Phase 2 Completed: Certificate OCR

### Implemented Parsers

**1. Header Parser (`header_parser.py`)**
- Extracts MIDA number (regex: `CDE\d?/\d{4}/\d+`)
- Extracts company name with smart lookahead (skips junk lines like "UNTUK KEGUNAAN RASMI")
- Extracts exemption period (start/end dates in ISO format)

**2. Text Quota Parser (`text_quota_parser.py`)**
- Primary parser for TE01 certificates
- Uses HS code pattern as item anchors (`\d{4}\.\d{2}\.\d{4}`)
- Extracts: line_no, hs_code, item_name, approved_quantity, uom, station_split
- **Page-by-page parsing**: Each page parsed independently, then merged
- UOM normalization: kg→KGM, u/unit/pcs→UNIT
- Smart station split detection (avoids confusing line numbers with station values)
- **Skips numbered headings** (e.g., "9.") and declaration keywords when parsing stations
- **Handwritten amendment handling**: Prefers last comma-formatted number, leaves ambiguous values empty

**3. Certificate Parser (`certificate_parser.py`)**
- `extract_page_texts()`: Extracts text per page using Azure spans
- `merge_items_from_pages()`: De-duplicates items by (line_no, hs_code), sorts by line_no
- Page-by-page parsing avoids cross-page interference from repeated headers/footers

**4. Table Parser (`table_parser.py`)**
- **Parses ALL matching quota tables** across the document (not just one best table)
- Scores table headers to find quota tables (score >= 2 threshold)
- **Station sub-header detection**: Finds station column headers (PORT_KLANG, KLIA, BUKIT_KAYU_HITAM) in sub-rows after main header
- **Continuation row handling**: Merges data from rows without line numbers into previous item
- **Amended value extraction**: Extracts clean numbers from noisy cells with stamps/crossouts (e.g., `239073.760 <<<<< 239,871.00`)
- **OCR artifact cleaning**: Removes `:unselected:`, `:selected:` markers from Azure DI
- **Declaration row filtering**: Skips signature/name rows (Nama/Name, Jawatan/Designation, Tarikh/Date)
- Merges items from all selected tables, de-duplicates by (line_no, hs_code)
- Sorts merged items by numeric line_no
- UOM normalization in table mode: kg→KGM, unit/pcs→UNIT
- Station split parsing from table columns with amended value support
- Falls back to text parser if table parsing yields 0 items

**5. Normalize/Validate (`normalize_validate.py`)**
- Validates required fields (HS code, item name)
- Preserves numeric quantities from text parser
- Passes through station_split data

### Debug Statistics Returned
- `qty_uom_parsed_count`: Successfully parsed quantities
- `qty_parse_fail_count`: Failed quantity extractions
- `qty_ambiguous_count`: Quantities accepted but flagged as ambiguous (handwriting)
- `qty_fail_samples`: Debug samples for failed parsing (max 5)
- `hs_code_indices`: Line indices where HS codes found
- `full_text_length`: Total extracted text length
- `parsing_mode`: "table" or "text_fallback"
- `pages_count`: Number of pages from Azure DI
- `page_text_lengths`: Text length per page
- `page_item_counts`: Items found per page
- `items_total_after_merge`: Total items after de-duplication
- `tables_found`: Number of tables detected by Azure DI
- `table_indices_selected`: Indices of tables used for parsing
- `tables_selected_count`: Number of tables selected for parsing
- `table_stats`: Per-table stats (index, page_no, score, items_found)
- `handwritten_spans_count`: Count of handwritten spans detected
- `handwritten_text_samples`: Sample text from handwritten spans (max 3)
- `pdf_page_count_local`: Page count from local PDF parsing (pypdf)
- `input_pdf_size_bytes`: Size of uploaded PDF in bytes
- `azure_pages_seen`: Number of pages Azure DI returned
- `azure_content_length`: Length of Azure content string
- `first_page_excerpt`: First 200 chars of first page text
- `last_page_excerpt`: Last 200 chars of last page text

## Project Goal
Build the MIDA module for Kagayaku's workflow:
1) Upload invoice → detect MIDA items → generate ALDEC "purple format" rows (Button 1)
2) After ALDEC approval → user inputs BXXXXX → update quota ledgers + remaining quota (Button 2)
3) Rare workflow: upload cleanly scanned MIDA certificate PDF → OCR table → user review/edit → save master + create empty ledgers
4) View certificate + per-item balance sheets

---

# Part A — Certificate OCR: What the parser outputs

## JSON contract (output from /certificate/parse)
```json
{
  "mida_no": "CDE2/2024/00755",
  "company_name": "HONG LEONG YAMAHA MOTOR SDN BHD",
  "exemption_start": "2024-07-19",
  "exemption_end": "2027-07-18",
  "items": [
    {
      "line_no": "1",
      "hs_code": "7318.15.9000",
      "item_name": "BOLT, FLG.",
      "approved_quantity": 14844.0,
      "uom": "KGM",
      "station_split": {
        "PORT_KLANG": 1484.4,
        "KLIA": null,
        "BUKIT_KAYU_HITAM": 13359.6
      }
    }
  ],
  "warnings": []
}
```

## Known Limitations
- Corrupt OCR text (e.g., "KEM DIRALA MALAYMAT" instead of "kg") results in empty UOM
- Station column order detected from sub-header row (PORT_KLANG, KLIA, BUKIT_KAYU_HITAM)
- Heavily corrupted handwritten amendments may still need manual review in GUI
- Multi-row items with complex splits may occasionally miss data

## Recent Improvements (Dec 2025)
- ✅ Station sub-header detection for correct column mapping
- ✅ Continuation row merging for items split across table rows
- ✅ Amended value extraction from noisy cells with stamps/pen crossouts
- ✅ OCR artifact removal (`:unselected:`, `:selected:` markers)
- ✅ Declaration/signature row filtering
- ✅ All 71 items in test PDF now parse correctly with valid station splits

---

# Part B — Next Steps (TODO)

## Phase 3: Database & Quota Tracking
- [ ] Database schema for certificates and quota ledgers
- [ ] API endpoints for CRUD operations
- [ ] Quota balance calculation per item

## Phase 4: Invoice Matching
- [ ] Upload invoice → detect MIDA items
- [ ] Generate ALDEC "purple format" rows
- [ ] Update quota ledgers after approval

## Phase 5: UI Enhancements
- [ ] User review/edit interface for parsed data
- [ ] Certificate + per-item balance sheet views
