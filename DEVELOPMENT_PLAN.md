# MIDA Project – Development Plan (Azure OCR)

## What we have so far (Phase 1, 2, 3 & 4 done)
- Repo scaffolded similar to Form-D-demo:
  - `server/` FastAPI backend
  - `web/` simple HTML upload page
- Endpoints:
  - `POST /api/mida/certificate/certificate/parse` - Production parsing
  - `POST /api/mida/certificate/certificate/parse-debug` - Debug parsing with stats
  - `POST /api/convert` - Invoice conversion with MIDA matching

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

## ✅ Phase 3 Completed: MIDA API Client

### MIDA Client (`mida_client.py`)
- Production-ready HTTP client for fetching certificate data
- Uses REST API calls instead of direct database access for portability
- In-memory TTL caching to reduce API calls
- Clean error handling with structured exceptions:
  - `MidaCertificateNotFoundError` (404)
  - `MidaApiError` (non-2xx responses)
  - `MidaClientConfigError` (missing configuration)
- Configurable timeout and base URL via environment variables
- Singleton pattern for shared client instance

### Environment Variables
- `MIDA_API_BASE_URL`: Base URL of the MIDA API
- `MIDA_API_TIMEOUT_SECONDS`: Request timeout (default: 10)
- `MIDA_API_CACHE_TTL_SECONDS`: Cache TTL (default: 60)

## ✅ Phase 4 Completed: Invoice Matching

### Invoice Matching Service (`mida_matching_service.py`)
- Parses Excel files (.xls, .xlsx) with automatic format detection
- Extracts invoice items with column auto-detection
- Supports Form Flag filtering (skips FORM-D items for MIDA matching)
- Column candidates for flexible parsing:
  - Item, Invoice No, Product Title, Model Code, Spec Code
  - Parts No, Parts Name, Net Weight(Kg), Gross Weight(Kg)
  - Quantity, Amount(USD), Form Flag, HS Code

### MIDA Matcher (`mida_matcher.py`)
- Matches invoice items to MIDA certificate items
- Supports exact and fuzzy matching with configurable threshold
- Text normalization (casefold, strip punctuation, collapse spaces)
- UOM normalization and compatibility checking
- 1-to-1 matching (each MIDA item matched once)
- Deterministic tie-breaking (higher score wins, prefer exact, lower line_no)
- Warning generation:
  - UOM mismatch
  - Exceeds remaining quantity
  - Near limit (>=90% usage)

### Convert Endpoint (`/api/convert`)
- Two modes:
  1. **Normal Mode**: Returns all invoice items without matching
  2. **MIDA Mode**: Matches invoice items to certificate, returns matched items
- Form Flag filtering in MIDA mode (skips FORM-D items)
- Returns matched items with MIDA details and remaining quantities
- Comprehensive error handling (422 for invalid input, 404 for missing cert)

### Test Coverage
- 35 unit tests for mida_matcher.py
- 13 integration tests for convert endpoint
- All tests passing

---

# Part B — Next Steps (TODO)

## Phase 5: Database & Quota Tracking
- [ ] Track consumed quantities per MIDA certificate item
- [ ] Quota balance calculation per item (approved - consumed)
- [ ] Historical ledger for quota usage

## Phase 6: UI Enhancements
- [ ] User review/edit interface for parsed data
- [ ] Certificate + per-item balance sheet views
- [ ] MIDA certificate dropdown selection (instead of text input)
