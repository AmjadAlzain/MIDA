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

## Phase 6: Complete Certificate Parser Integration (TODO)

### 6.1 Wire Save to Database Button
- [ ] Implement `saveToDatabaseConfirmed()` to call `POST /api/mida/certificates/draft`
- [ ] Map frontend data structure to `CertificateDraftCreateRequest` schema
- [ ] Handle success (show certificate ID, enable "Confirm" action)
- [ ] Handle errors (409 Conflict for confirmed certs, validation errors)

### 6.2 Certificate List & Management UI
- [ ] Add "View Saved Certificates" section in Certificate Parser tab
- [ ] Fetch certificates via `GET /api/mida/certificates/?status=draft` and `status=confirmed`
- [ ] Display as searchable/filterable table with columns: Cert No, Company, Status, Date
- [ ] Click to load → populate edit form (if draft) or read-only view (if confirmed)
- [ ] Add "Confirm Certificate" button to lock drafts

### 6.3 Certificate Dropdown in Invoice Converter
- [ ] Replace text input with searchable dropdown/autocomplete
- [ ] Populate from `GET /api/mida/certificates/?status=confirmed`
- [ ] Show cert number + company name + expiry date in dropdown

---

## Phase 7: MIDA Invoice Converter & Purple Output (TODO)

### Reference: How Form-D-demo Works
Form-D-demo (`/api/convert`) does:
1. Upload invoice Excel → parse with pandas
2. Filter rows where `Form Flag == "FORM-D"`
3. Map to K1 Import Template columns (HSCode, StatisticalUOM, DeclaredUOM, StatisticalQty, etc.)
4. Look up UOM from HSCODE.json mapping
5. Generate XLS file using `K1 Import Template.xls` (JobCargo sheet)
6. Return as downloadable file

### 7.1 Invoice Classification Logic
- [ ] Parse uploaded invoice Excel
- [ ] Classify items by Form Flag column:
  - **FORM-D** → Skip for MIDA (handled by Form-D converter)
  - **Empty/Blank** → MIDA-eligible, proceed to matching
  - **Other values** → Log/warn, exclude or treat as MIDA-eligible

### 7.2 MIDA Matching & Cross-Check
- [ ] Match MIDA-eligible items against selected certificate's items
- [ ] Matching criteria: HS Code (exact/prefix) + Item Name (fuzzy similarity)
- [ ] For each match:
  - Get approved_quantity from certificate
  - Calculate remaining_qty = approved - already_consumed
  - Warn if requested qty > remaining_qty
  - Warn if nearing limit (>90% consumed)

### 7.3 Purple Output Generation (K1 Import Format)
- [ ] Create `convert_to_k1_mida()` function (similar to Form-D-demo)
- [ ] Use same K1 Import Template.xls with JobCargo sheet
- [ ] Map columns:
  | Source | Template Column |
  |--------|-----------------|
  | Certificate Country | Country of Origin |
  | HS Code (normalized + "00" suffix) | HSCode |
  | UOM from certificate | StatisticalUOM, DeclaredUOM |
  | Quantity | StatisticalQty, DeclaredQty |
  | Amount | ItemAmount |
  | Parts Name | ItemDescription |
  | Quantity (again) | ItemDescription2 |
- [ ] Set exemption fields:
  - ImportDutyMethod = "Exemption"
  - ImportDutyRateExemptedPercentage = 100
  - SSTMethod = "Exemption"
  - SSTRateExemptedPercentage = 100
- [ ] Leave vehicle fields blank (ExciseDutyMethod, VehicleType, etc.)

### 7.4 Download Flow
- [ ] Return XLS as downloadable file: `mida-k1-import-{timestamp}.xls`
- [ ] Add "Download MIDA Output" button in UI after successful conversion
- [ ] Optionally: Generate separate files for FORM-D and MIDA items

---

## Phase 8: Database Schema & Quota Tracking System (TODO)

### Overview: What Happens When "Save to Database" is Clicked

When the user clicks "Save to Database" after parsing and editing a MIDA certificate, the system must:

1. **Create the certificate header record** (master table)
2. **Create certificate item records with remaining quantities** (initially = approved)
3. **Create per-item import ledger tables** (1 for approved + 1 per active port = up to 4 tables per item)

---

### 8.1 Database Schema Design

#### Table 1: `mida_certificates` (Certificate Header - Master Table)
Stores certificate-level metadata. **Already exists** in current models.

```sql
CREATE TABLE mida_certificates (
  id UUID PRIMARY KEY,
  certificate_number VARCHAR(100) UNIQUE NOT NULL,
  company_name VARCHAR(500) NOT NULL,
  exemption_start_date DATE,
  exemption_end_date DATE,
  status VARCHAR(20) DEFAULT 'draft',  -- 'draft' or 'confirmed'
  source_filename VARCHAR(500),
  raw_ocr_json JSONB,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

#### Table 2: `mida_certificate_items` (Certificate Items with Remaining Quantities)
Stores each line item with **both approved AND remaining quantities**.
**UPDATE NEEDED**: Add remaining quantity columns (initially = approved quantities).

```sql
CREATE TABLE mida_certificate_items (
  id UUID PRIMARY KEY,
  certificate_id UUID REFERENCES mida_certificates(id) ON DELETE CASCADE,
  line_no INTEGER NOT NULL,
  hs_code VARCHAR(20) NOT NULL,
  item_name TEXT NOT NULL,
  uom VARCHAR(50) NOT NULL,
  
  -- Approved quantities (from certificate)
  approved_quantity DECIMAL(18,3),
  port_klang_qty DECIMAL(18,3),
  klia_qty DECIMAL(18,3),
  bukit_kayu_hitam_qty DECIMAL(18,3),
  
  -- Remaining quantities (decreases with each import)
  remaining_quantity DECIMAL(18,3),        -- Initially = approved_quantity
  remaining_port_klang DECIMAL(18,3),      -- Initially = port_klang_qty
  remaining_klia DECIMAL(18,3),            -- Initially = klia_qty
  remaining_bukit_kayu_hitam DECIMAL(18,3), -- Initially = bukit_kayu_hitam_qty
  
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  
  UNIQUE (certificate_id, line_no)
);
```

#### Table 3: `mida_import_ledger` (Per-Item Import Tracking - Unified Ledger)
Tracks each import transaction per item, per port. Similar to existing `Table1` schema.
Each row = one import event deducting from one port's quota.

```sql
CREATE TABLE mida_import_ledger (
  id UUID PRIMARY KEY,
  certificate_item_id UUID REFERENCES mida_certificate_items(id) ON DELETE CASCADE,
  
  -- Import details
  s_no SERIAL,                             -- Sequential number
  import_date DATE NOT NULL,
  declaration_reg_no VARCHAR(255),         -- ALDEC declaration reference
  kagayaku_ref_no VARCHAR(255),            -- Internal reference (BXXXXX)
  
  -- Port indicator (which port this import came through)
  port VARCHAR(50) NOT NULL,               -- 'PORT_KLANG', 'KLIA', 'BUKIT_KAYU_HITAM', or 'TOTAL'
  
  -- Balance tracking (like Table1 schema)
  balance_carried_forward DECIMAL(18,3),   -- Balance before this import
  quantity_imported DECIMAL(18,3),         -- Amount deducted in this import
  balance_after DECIMAL(18,3),             -- Balance after this import
  
  -- Metadata
  created_at TIMESTAMP DEFAULT NOW(),
  created_by VARCHAR(100),
  notes TEXT,
  
  -- Ensure item links to correct certificate via FK chain
  CONSTRAINT fk_item FOREIGN KEY (certificate_item_id) 
    REFERENCES mida_certificate_items(id) ON DELETE CASCADE
);

-- Index for fast lookups
CREATE INDEX ix_import_ledger_item ON mida_import_ledger(certificate_item_id);
CREATE INDEX ix_import_ledger_port ON mida_import_ledger(port);
CREATE INDEX ix_import_ledger_date ON mida_import_ledger(import_date);
```

---

### 8.2 How the Tables Relate (RDBMS Relationships)

```
┌─────────────────────────┐
│   mida_certificates     │  (1 per MIDA certificate)
│   - id (PK)             │
│   - certificate_number  │
│   - company_name        │
│   - exemption dates     │
└───────────┬─────────────┘
            │ 1:N
            ▼
┌─────────────────────────────────────────────┐
│        mida_certificate_items               │  (N items per certificate)
│   - id (PK)                                 │
│   - certificate_id (FK → mida_certificates) │
│   - hs_code, item_name, uom                 │
│   - approved_quantity, port_klang_qty, etc. │
│   - remaining_quantity, remaining_port_*, etc│
└───────────┬─────────────────────────────────┘
            │ 1:N
            ▼
┌─────────────────────────────────────────────┐
│          mida_import_ledger                 │  (N imports per item)
│   - id (PK)                                 │
│   - certificate_item_id (FK → items)        │
│   - port (which port)                       │
│   - balance_carried_forward                 │
│   - quantity_imported                       │
│   - balance_after                           │
│   - import_date, declaration_reg_no         │
└─────────────────────────────────────────────┘
```

**Key RDBMS Constraints:**
- Same item can exist in multiple certificates → `certificate_item_id` links each ledger entry to the correct certificate
- When an import occurs at a port, TWO ledger entries are created:
  1. One for the specific port (e.g., `port='PORT_KLANG'`)
  2. One for the total approved quantity (`port='TOTAL'`)
- Remaining quantities in `mida_certificate_items` are updated via trigger or application logic

---

### 8.3 Implementation Tasks

#### 8.3.1 Update Existing Model (Add Remaining Quantity Columns)
- [ ] Add to `MidaCertificateItem` model:
  ```python
  remaining_quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 3), nullable=True)
  remaining_port_klang: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 3), nullable=True)
  remaining_klia: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 3), nullable=True)
  remaining_bukit_kayu_hitam: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 3), nullable=True)
  ```
- [ ] Create Alembic migration to add these columns
- [ ] On certificate save, initialize `remaining_* = approved_*` for all columns

#### 8.3.2 Create Import Ledger Model
- [ ] Create `MidaImportLedger` model in `app/models/mida_import_ledger.py`
- [ ] Define PortType enum: `PORT_KLANG`, `KLIA`, `BUKIT_KAYU_HITAM`, `TOTAL`
- [ ] Create Alembic migration for the new table

#### 8.3.3 Service Layer for Import Recording
- [ ] Create `mida_import_service.py` with functions:
  - `record_import(certificate_item_id, port, quantity, declaration_ref, notes)`
  - `get_item_ledger(certificate_item_id, port=None)` - get all imports for an item
  - `get_item_balance(certificate_item_id)` - get current remaining for all ports
- [ ] Implement balance update logic:
  - When recording import for a port:
    1. Get current `remaining_*` for that port
    2. Calculate `balance_carried_forward = remaining_*`
    3. Calculate `balance_after = balance_carried_forward - quantity_imported`
    4. Insert ledger entry for the specific port
    5. Insert ledger entry for TOTAL (approved_quantity)
    6. Update `remaining_*` columns in `mida_certificate_items`
  - All operations in single transaction

#### 8.3.4 API Endpoints
- [ ] `POST /api/mida/certificates/{cert_id}/items/{item_id}/import`
  - Record an import for a specific item at a specific port
  - Request body: `{port, quantity, declaration_reg_no, kagayaku_ref_no, import_date, notes}`
- [ ] `GET /api/mida/certificates/{cert_id}/items/{item_id}/ledger`
  - Get all import history for an item (optionally filter by port)
- [ ] `GET /api/mida/certificates/{cert_id}/balance`
  - Get remaining quantities for all items in certificate

#### 8.3.5 Update Save to Database Flow
- [ ] When saving certificate:
  1. Create/update `mida_certificates` record
  2. Create/update `mida_certificate_items` records with remaining = approved
  3. Return certificate ID for confirmation

---

### 8.4 Balance Calculation Rules

**When an import is recorded at a port:**
1. Deduct from that port's remaining quantity (`remaining_port_klang`, etc.)
2. Also deduct from total remaining quantity (`remaining_quantity`)
3. Create ledger entry for port with marker
4. Create ledger entry for total with marker indicating which port

**Validation:**
- Cannot import more than remaining quantity
- Cannot import if certificate is expired (check exemption_end_date)
- Warn if remaining is near zero (<10% remaining)

---

### 8.5 Balance Sheet Views (UI)
- [ ] Per-certificate summary: All items with approved/remaining for each port
- [ ] Per-item detail: Full import history with running balance
- [ ] Export to Excel/PDF for reporting
- [ ] Filter by date range, port, item

---

### 8.6 ALDEC Integration (Future)
- [ ] After ALDEC approval → user inputs BXXXXX (kagayaku_ref_no)
- [ ] Link imports to ALDEC declaration reference
- [ ] Support batch import from ALDEC export file

---

## Summary of Remaining Work

| Phase | Description | Priority | Effort |
|-------|-------------|----------|--------|
| 6.1 | Wire Save to Database button | 🔴 High | Small |
| 6.2 | Certificate list & management UI | 🟡 Medium | Medium |
| 6.3 | Certificate dropdown in converter | 🟡 Medium | Small |
| 7.1-7.4 | MIDA invoice converter + K1 output | 🔴 High | Large |
| 8.1 | Database schema (remaining qty columns + ledger table) | 🔴 High | Medium |
| 8.2-8.3 | Import recording service + API endpoints | 🔴 High | Large |
| 8.4 | Balance calculation & validation | 🟡 Medium | Medium |
| 8.5 | Balance sheet views (UI) | 🟡 Medium | Large |
| 8.6 | ALDEC integration | 🟢 Low | Medium |
