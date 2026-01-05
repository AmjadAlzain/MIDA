# MIDA Project – Development Plan (Azure OCR)

## What we have so far (Phase 1–8 done, Phase 9 in progress)
- Repo scaffolded similar to Form-D-demo:
  - `server/` FastAPI backend
  - `web/` simple HTML upload page with 3-tab classification UI
- Endpoints:
  - `POST /api/mida/certificate/certificate/parse` - Production parsing
  - `POST /api/mida/certificate/certificate/parse-debug` - Debug parsing with stats
  - `POST /api/convert` - Invoice conversion with MIDA matching
  - `POST /api/convert-multi` - Multi-certificate MIDA matching
  - `GET /api/companies` - Get all companies for classification
  - `POST /api/convert/classify` - 3-tab classification (Form-D, MIDA, Duties Payable)
  - `POST /api/convert/export-classified` - K1 XLS export for classified items
- Database:
  - Companies table (HICOM YAMAHA MOTOR SDN BHD, HONG LEONG YAMAHA MOTOR SDN BHD)
  - HSCODE UOM mappings table for balance deduction
  - 8 Alembic migrations (certificates, import tracking, status, declaration form, model number, soft delete, hscode uom, companies)

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

---

## ✅ Phase 5 Completed (feature/certificate-parser): Certificate Parser UI & CRUD API

### Implemented by Coworker (Dec 2025)

**Frontend - Certificate Parser Tab** ([web/index.html](web/index.html))
- Two-tab interface: "Invoice Converter" and "Certificate Parser"
- Upload PDF → OCR via Azure Document Intelligence → Editable table
- Header fields: Certificate Number, Company Name, Exemption Start/End Dates
- Items table: Line No, HS Code, Item Name, Approved Qty, UOM, Station splits
- Edit mode with Save Changes / Cancel buttons
- "Save to Database" button with confirmation modal

**Backend - Certificate CRUD API** ([server/app/routers/mida_certificates.py](server/app/routers/mida_certificates.py))
- `POST /api/mida/certificates/draft` - Create or replace draft certificate
- `PUT /api/mida/certificates/{id}` - Update draft by ID
- `POST /api/mida/certificates/{id}/confirm` - Confirm (makes read-only)
- `GET /api/mida/certificates/{id}` - Get certificate by ID
- `GET /api/mida/certificates/` - List certificates with pagination
- Draft/Confirmed workflow (confirmed certificates are immutable)

**Service Layer** ([server/app/services/mida_certificate_service.py](server/app/services/mida_certificate_service.py))
- `create_or_replace_draft()` - Create new or update existing draft
- `update_draft_by_id()` - Update by UUID
- `confirm_certificate()` - Lock certificate
- Transactional item replacement (delete existing + insert new)

### ⚠️ Known Issue: Save to Database Not Working
The frontend "Save to Database" button shows a placeholder alert instead of calling the API:
```javascript
// TODO: Implement actual database save API call
alert('Certificate data will be saved to database...');
```
**Fix needed**: Wire frontend to POST `/api/mida/certificates/draft`

---

## ✅ Phase 6 Completed: Save to Database Wiring

### 6.1 ✅ Wire Save to Database Button
- [x] Implemented `saveToDatabaseConfirmed()` to call `POST /api/mida/certificates/draft`
- [x] Map frontend data structure to `CertificateDraftCreateRequest` schema
- [x] Handle success (show certificate ID, enable "Confirm" action)
- [x] Handle errors (409 Conflict for confirmed certs, validation errors)
- [x] Fixed run_server.py to load .env file using python-dotenv

### 6.2 Certificate List & Management (Partially Done)
- [x] API endpoints for certificate CRUD operations
- [ ] Add "View Saved Certificates" section in Certificate Parser tab (future)
- [ ] Display as searchable/filterable table (future)

### 6.3 Certificate Dropdown in Invoice Converter
- [x] Certificate selection via ID input for multi-certificate matching
- [ ] Searchable dropdown/autocomplete (future enhancement)

---

## ✅ Phase 7 Completed: MIDA Invoice Converter & K1 Output

### 7.1 ✅ Invoice Classification Logic
- [x] Parse uploaded invoice Excel with `parse_all_invoice_items()`
- [x] Classify items by Form Flag column:
  - **FORM-D** → Form-D table
  - **Empty/Blank** → MIDA-eligible (if matched) or Duties Payable
- [x] Support both single and multi-certificate matching

### 7.2 ✅ MIDA Matching & Cross-Check
- [x] Match MIDA-eligible items against selected certificate's items
- [x] Matching criteria: Item Name (fuzzy similarity) + Model Number
- [x] For each match:
  - Get approved_quantity from certificate
  - Calculate remaining_qty from certificate items
  - Warn if requested qty > remaining_qty
  - Warn if nearing limit (>90% consumed)

### 7.3 ✅ K1 Output Generation (Purple Format)
- [x] Created `generate_k1_xls_with_options()` function in `k1_export_service.py`
- [x] Uses K1 Import Template.xls with JobCargo sheet
- [x] Column mapping:
  | Source | Template Column |
  |--------|-----------------|
  | Country Code | CountryOfOrigin |
  | HS Code (normalized + "00" suffix) | HSCode |
  | UOM from invoice | StatisticalUOM, DeclaredUOM |
  | Quantity | StatisticalQty, DeclaredQty |
  | Amount | ItemAmount |
  | Parts Name | ItemDescription |
  | Quantity (again) | ItemDescription2 |
- [x] Export type settings:
  - **form_d**: ImportDutyMethod = "Exemption", Method = "E", 100%
  - **mida**: ImportDutyMethod = "Exemption", Method = "E", 100%
  - **duties_payable**: ImportDutyMethod = empty, Method = empty
- [x] SST columns per item based on `sst_exempted` field:
  - If sst_exempted=True: SSTMethod = "Exemption", Method = "E", 100%
  - If sst_exempted=False: Empty SST columns

### 7.4 ✅ Download Flow
- [x] Return XLS as downloadable file: `k1-{export_type}-{timestamp}.xls`
- [x] Add "Export to K1" button in each tab of the 3-tab UI
- [x] Generate separate files for Form-D, MIDA, and Duties Payable items

---

## ✅ Phase 8 Completed: Database Schema & Import Tracking

### 8.1 ✅ Database Schema Design

#### Table 1: `mida_certificates` (Certificate Header - Master Table)
✅ Exists with all fields including:
- id, certificate_number, company_name
- exemption_start_date, exemption_end_date
- status ('draft' or 'confirmed')
- model_number (added in migration 005)
- source_filename, raw_ocr_json, created_at, updated_at

#### Table 2: `mida_certificate_items` (Certificate Items with Remaining Quantities)
✅ Exists with remaining quantity columns:
- approved_quantity, remaining_quantity
- port_klang_qty, klia_qty, bukit_kayu_hitam_qty
- remaining_port_klang, remaining_klia, remaining_bukit_kayu_hitam
- is_deleted (soft delete, migration 006)

#### Table 3: `mida_import_records` (Import Tracking)
✅ Created via migration 002:
- certificate_item_id, port, quantity_imported
- balance_before, balance_after
- import_date, declaration_ref, kagayaku_ref

#### Table 4: `companies` (Company Configuration)
✅ Created via migration 008:
- name: "HICOM YAMAHA MOTOR SDN BHD" or "HONG LEONG YAMAHA MOTOR SDN BHD"
- sst_default_behavior: "all_on" (HICOM) or "mida_only" (Hong Leong)
- dual_flag_routing: "form_d" (HICOM) or "mida" (Hong Leong)

#### Table 5: `hscode_uom_mappings` (HSCODE to UOM)
✅ Created via migration 007:
- hs_code (normalized, dots removed)
- uom: "UNIT" or "KGM"

### 8.2 ✅ Alembic Migrations
All 8 migrations created and applied:
1. `001_add_mida_certificates.py` - Certificate tables
2. `002_add_import_tracking.py` - Import ledger
3. `003_add_certificate_status.py` - Status column
4. `004_add_declaration_form_number.py` - Declaration form field
5. `005_add_model_number.py` - Model number field
6. `006_add_soft_delete.py` - is_deleted flag
7. `007_add_hscode_uom_mappings.py` - HSCODE UOM table
8. `008_companies.py` - Companies table with HICOM/Hong Leong

### 8.3 ✅ Service Layer Implementation
- `mida_import_service.py` - Record imports, update balances
- `mida_certificate_service.py` - Certificate CRUD operations
- `company_repo.py` - Company lookups
- `hscode_uom_repo.py` - HSCODE UOM lookups

### 8.4 ✅ API Endpoints for Import Tracking
- `POST /api/mida/imports` - Record import
- `GET /api/mida/imports/{item_id}` - Get import history
- Certificate endpoints in `mida_certificates.py` router

---

## ✅ Phase 9 Completed: 3-Tab Classification System (Form-D Integration)

### Overview
Integrated Form-D classification workflow with company-specific SST and routing rules.

### 9.1 ✅ Company Model & Configuration
- [x] Created `Company` model in `server/app/models/company.py`
- [x] Two companies configured:
  - **HICOM YAMAHA MOTOR SDN BHD**: sst_default='all_on', dual_flag_routing='form_d'
  - **HONG LEONG YAMAHA MOTOR SDN BHD**: sst_default='mida_only', dual_flag_routing='mida'
- [x] Repository: `company_repo.py` with `get_all_companies()`, `get_company_by_id()`

### 9.2 ✅ Invoice Classification Service
- [x] Created `invoice_classification_service.py` with:
  - `parse_all_invoice_items()` - Parse ALL invoice items including Form-D flagged
  - `classify_items()` - Classify into 3 categories based on rules
- [x] Classification Rules:
  | Form-D Flag | MIDA Matched | Result |
  |-------------|--------------|--------|
  | Yes | No | Form-D table |
  | No | Yes | MIDA table |
  | Yes | Yes | Depends on company (HICOM→Form-D, Hong Leong→MIDA) |
  | No | No | Duties Payable table |
- [x] SST Exemption Defaults:
  - HICOM: SST ON for all items in all tables
  - Hong Leong: SST ON only for MIDA table items

### 9.3 ✅ K1 Export Service with Options
- [x] Created `generate_k1_xls_with_options()` in `k1_export_service.py`
- [x] Three export types: form_d, mida, duties_payable
- [x] Per-item SST exemption support
- [x] Import duty exemption only for Form-D and MIDA exports

### 9.4 ✅ Classification API Endpoints
- [x] `GET /api/companies` - List all companies for dropdown
- [x] `POST /api/convert/classify` - Full classification endpoint
  - Accepts: file, company_id, mida_certificate_ids (optional), country, port, import_date
  - Returns: ClassifyResponse with 3 item lists + metadata
- [x] `POST /api/convert/export-classified` - Export classified items to K1 XLS
  - Accepts: K1ExportRequest with items, export_type, country
  - Returns: StreamingResponse with XLS file

### 9.5 ✅ Schemas for Classification
- [x] Created `server/app/schemas/classification.py`:
  - `ExportType` enum: form_d, mida, duties_payable
  - `ItemTable` enum: form_d, mida, duties_payable
  - `ClassifiedItem` - Full item with all fields and classification metadata
  - `CompanyOut` - Company info for API response
  - `ClassifyResponse` - Response with 3 item lists
  - `K1ExportItem` - Item for K1 export
  - `K1ExportRequest` - Request body for export

### 9.6 ✅ Frontend 3-Tab UI
- [x] Company dropdown populated from `/api/companies`
- [x] 3 tabs: Form-D, MIDA, Duties Payable
- [x] Per-item SST toggle checkbox in each table
- [x] "Move to" dropdown to move items between tables
- [x] "Export to K1" button in each tab
- [x] Item counts per tab updated dynamically

---

# Part B — Remaining Work (Future Phases)
## Phase 10: UI Enhancements (TODO)

### 10.1 Certificate List & Management UI
- [ ] Add "View Saved Certificates" section in Certificate Parser tab
- [ ] Fetch certificates via `GET /api/mida/certificates/?status=draft` and `status=confirmed`
- [ ] Display as searchable/filterable table with columns: Cert No, Company, Status, Date
- [ ] Click to load → populate edit form (if draft) or read-only view (if confirmed)
- [ ] Add "Confirm Certificate" button to lock drafts

### 10.2 Certificate Dropdown Enhancement
- [ ] Replace text input with searchable dropdown/autocomplete
- [ ] Populate from `GET /api/mida/certificates/?status=confirmed`
- [ ] Show cert number + company name + expiry date in dropdown

### 10.3 Balance Sheet Views
- [ ] Per-certificate summary: All items with approved/remaining for each port
- [ ] Per-item detail: Full import history with running balance
- [ ] Export to Excel/PDF for reporting
- [ ] Filter by date range, port, item

---

## Phase 11: ALDEC Integration (TODO)

### 11.1 Post-ALDEC Workflow
- [ ] After ALDEC approval → user inputs BXXXXX (kagayaku_ref_no)
- [ ] Link imports to ALDEC declaration reference
- [ ] Support batch import from ALDEC export file

### 11.2 Declaration Reference Tracking
- [ ] Add declaration_reg_no field validation
- [ ] Auto-generate sequential kagayaku_ref_no

---

## Summary of Remaining Work

| Phase | Description | Priority | Effort | Status |
|-------|-------------|----------|--------|--------|
| 10.1 | Certificate list & management UI | 🟡 Medium | Medium | TODO |
| 10.2 | Certificate dropdown in converter | 🟡 Medium | Small | TODO |
| 10.3 | Balance sheet views (UI) | 🟡 Medium | Large | TODO |
| 11.1 | ALDEC post-approval workflow | 🟢 Low | Medium | TODO |
| 11.2 | Declaration reference tracking | 🟢 Low | Small | TODO |

---

## Current Codebase Structure

```
server/
├── app/
│   ├── main.py                          # FastAPI app entry point
│   ├── config.py                        # 12-factor settings
│   ├── logging_config.py                # Structured logging
│   ├── clients/
│   │   └── mida_client.py               # MIDA API client with caching
│   ├── db/
│   │   ├── base.py                      # SQLAlchemy Base
│   │   ├── mixins.py                    # UUID, Timestamp mixins
│   │   └── session.py                   # Database session
│   ├── models/
│   │   ├── company.py                   # Company model (SST rules)
│   │   ├── hscode_uom_mapping.py        # HSCODE to UOM mapping
│   │   └── mida_certificate.py          # Certificate & items
│   ├── repositories/
│   │   ├── company_repo.py              # Company queries
│   │   ├── hscode_uom_repo.py           # HSCODE UOM queries
│   │   ├── mida_certificate_repo.py     # Certificate queries
│   │   └── mida_import_repo.py          # Import record queries
│   ├── routers/
│   │   ├── convert.py                   # Main conversion endpoints
│   │   ├── hscode_uom.py                # HSCODE UOM endpoints
│   │   ├── mida_certificate.py          # Certificate parsing
│   │   ├── mida_certificates.py         # Certificate CRUD
│   │   └── mida_imports.py              # Import tracking
│   ├── schemas/
│   │   ├── classification.py            # 3-tab classification schemas
│   │   ├── convert.py                   # Conversion schemas
│   │   ├── mida_certificate.py          # Certificate schemas
│   │   └── mida_import.py               # Import schemas
│   └── services/
│       ├── azure_di_client.py           # Azure Document Intelligence
│       ├── invoice_classification_service.py  # Classification logic
│       ├── k1_export_service.py         # K1 XLS generation
│       ├── mida_certificate_service.py  # Certificate CRUD
│       ├── mida_import_service.py       # Import recording
│       ├── mida_matcher.py              # Invoice-to-MIDA matching
│       └── mida_matching_service.py     # Invoice parsing
├── alembic/
│   └── versions/
│       ├── 001_add_mida_certificates.py
│       ├── 002_add_import_tracking.py
│       ├── 003_add_certificate_status.py
│       ├── 004_add_declaration_form_number.py
│       ├── 005_add_model_number.py
│       ├── 006_add_soft_delete.py
│       ├── 007_add_hscode_uom_mappings.py
│       └── 008_companies.py
├── templates/
│   └── K1_Import_Template.xls           # K1 export template
├── run_server.py                        # Quick server startup
└── requirements.txt

web/
└── index.html                           # Frontend with 3-tab UI
```

---

## API Endpoint Summary

### Conversion Endpoints (`/api/convert/...`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/companies` | List all companies for dropdown |
| POST | `/api/convert` | Single certificate MIDA matching |
| POST | `/api/convert-multi` | Multi-certificate MIDA matching |
| POST | `/api/convert/classify` | 3-tab classification (Form-D, MIDA, Duties Payable) |
| POST | `/api/convert/export` | Export non-FORM-D items to K1 XLS |
| POST | `/api/convert/export-mida` | Export MIDA matched items to K1 XLS |
| POST | `/api/convert/export-classified` | Export classified items to K1 XLS |

### Certificate Endpoints (`/api/mida/certificates/...`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/mida/certificates/` | List certificates with pagination |
| GET | `/api/mida/certificates/{id}` | Get certificate by ID |
| POST | `/api/mida/certificates/draft` | Create or replace draft |
| PUT | `/api/mida/certificates/{id}` | Update draft by ID |
| POST | `/api/mida/certificates/{id}/confirm` | Confirm certificate |

### Import Endpoints (`/api/mida/imports/...`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mida/imports` | Record import |
| GET | `/api/mida/imports/{item_id}` | Get import history |

### Certificate Parsing (`/api/mida/certificate/...`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mida/certificate/parse` | Parse certificate PDF |
| POST | `/api/mida/certificate/parse-debug` | Parse with debug info |

### HSCODE UOM Endpoints (`/api/hscode-uom/...`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/hscode-uom/{hs_code}` | Get UOM for HSCODE |