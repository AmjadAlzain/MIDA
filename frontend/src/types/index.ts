// ==========================================
// Company Types
// ==========================================
export interface Company {
  id: string;
  name: string;
  sst_default_behavior: 'all_on' | 'mida_only';
  dual_flag_routing: boolean;
}

// ==========================================
// Certificate Types
// ==========================================
export interface Certificate {
  id: string;
  certificate_number: string;
  company_name: string;
  model_number?: string;
  exemption_start_date: string;
  exemption_end_date: string;
  status: 'active' | 'expired' | 'deleted';
  source_filename?: string;
  items?: CertificateItem[];
  created_at?: string;
  updated_at?: string;
  deleted_at?: string;
}

export interface CertificateItem {
  id: string;
  line_no: number;
  hs_code: string;
  item_name: string;
  uom: string;
  approved_quantity: number;
  port_klang_qty: number;
  klia_qty: number;
  bukit_kayu_hitam_qty: number;
}

export interface CertificateItemBalance extends CertificateItem {
  item_id: string;
  certificate_id: string;
  certificate_number?: string;
  remaining_quantity: number;
  remaining_port_klang: number;
  remaining_klia: number;
  remaining_bukit_kayu_hitam: number;
  quantity_status: 'normal' | 'warning' | 'depleted' | 'overdrawn';
}

export interface CertificateListResponse {
  items: Certificate[];
  total: number;
}

export interface CertificateItemsResponse {
  items: CertificateItemBalance[];
  total: number;
}

// ==========================================
// Import Record Types
// ==========================================
export interface ImportRecord {
  id: string;
  certificate_item_id: string;
  import_date: string;
  declaration_form_reg_no?: string;
  invoice_number: string;
  invoice_line: number;
  quantity_imported: number;
  port: 'port_klang' | 'klia' | 'bukit_kayu_hitam';
  balance_before: number;
  balance_after: number;
  remarks?: string;
  created_at: string;
}

export interface ImportRecordsResponse {
  imports: ImportRecord[];
  total: number;
}

export interface BulkImportRequest {
  records: {
    certificate_item_id: string;
    import_date: string;
    declaration_form_reg_no?: string;
    invoice_number: string;
    invoice_line: number;
    quantity_imported: number;
    port: string;
    remarks?: string;
  }[];
}

// ==========================================
// Classification Types
// ==========================================
export interface ClassificationItem {
  id: string;
  line_no: number;
  description: string;
  parts_name?: string;
  hs_code: string;
  mida_hs_code?: string;
  quantity: number;
  uom: string;
  amount?: number;
  net_weight_kg?: number;
  sst_exempted: boolean;
  sst_exempted_default: boolean;
  sst_manually_changed: boolean;
  manually_moved: boolean;
  original_table: 'form_d' | 'mida' | 'duties_payable';
  current_table: 'form_d' | 'mida' | 'duties_payable';
  // MIDA-specific fields
  mida_item_id?: string;
  mida_certificate_id?: string;
  mida_certificate_number?: string;
  mida_line_no?: number;
  remaining_qty?: number;
  deduction_quantity?: number;
  match_score?: number;
  hscode_uom?: string;
}

export interface ClassificationResponse {
  form_d_items: ClassificationItem[];
  mida_items: ClassificationItem[];
  duties_payable_items: ClassificationItem[];
  total_items: number;
  company: Company;
  warnings?: string[];
}

export interface ClassificationState {
  form_d_items: ClassificationItem[];
  mida_items: ClassificationItem[];
  duties_payable_items: ClassificationItem[];
  company: Company | null;
  country: string;
  port: string;
  import_date: string;
}

// ==========================================
// Certificate Parser Types
// ==========================================
export interface ParsedCertificateItem {
  line_no: number;
  hs_code: string;
  item_name: string;
  approved_quantity: number;
  uom: string;
  station_split?: {
    PORT_KLANG?: number;
    KLIA?: number;
    BUKIT_KAYU_HITAM?: number;
  };
}

export interface ParsedCertificate {
  mida_no: string;
  company_name: string;
  model_number?: string;
  exemption_start: string;
  exemption_end: string;
  items: ParsedCertificateItem[];
  warnings?: string[];
}

export interface SaveCertificateRequest {
  header: {
    certificate_number: string;
    company_name: string;
    model_number?: string;
    exemption_start_date: string;
    exemption_end_date: string;
    source_filename?: string;
  };
  items: {
    line_no: number;
    hs_code: string;
    item_name: string;
    uom: string;
    approved_quantity: number;
    port_klang_qty?: number;
    klia_qty?: number;
    bukit_kayu_hitam_qty?: number;
  }[];
  raw_ocr_json?: ParsedCertificate;
}

// ==========================================
// K1 Export Types
// ==========================================
export interface K1ExportItem {
  hs_code: string;
  description: string;
  description2?: string;
  quantity: number;
  uom: string;
  amount?: number;
  net_weight_kg?: number;
  sst_exempted: boolean;
}

export interface K1ExportRequest {
  items: K1ExportItem[];
  export_type: 'form_d' | 'mida' | 'duties_payable';
  country: string;
}

// ==========================================
// Common Types
// ==========================================
export interface PaginationParams {
  page: number;
  perPage: number;
}

export interface ApiError {
  detail: string | { detail: string };
}

export type Port = 'port_klang' | 'klia' | 'bukit_kayu_hitam';

export const PORT_DISPLAY_NAMES: Record<Port | 'all', string> = {
  all: 'All Ports',
  port_klang: 'Port Klang',
  klia: 'KLIA',
  bukit_kayu_hitam: 'Bukit Kayu Hitam',
};

export const COUNTRIES = [
  { code: 'JP', name: 'Japan' },
  { code: 'CN', name: 'China' },
  { code: 'US', name: 'United States' },
  { code: 'DE', name: 'Germany' },
  { code: 'KR', name: 'Korea, Republic of' },
  { code: 'TW', name: 'Taiwan' },
  { code: 'TH', name: 'Thailand' },
  { code: 'SG', name: 'Singapore' },
  { code: 'ID', name: 'Indonesia' },
  { code: 'VN', name: 'Vietnam' },
  { code: 'MY', name: 'Malaysia' },
  { code: 'IN', name: 'India' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'FR', name: 'France' },
  { code: 'IT', name: 'Italy' },
  // Add more as needed
] as const;

export const PORTS: { value: Port; label: string }[] = [
  { value: 'port_klang', label: 'Port Klang' },
  { value: 'klia', label: 'KLIA' },
  { value: 'bukit_kayu_hitam', label: 'Bukit Kayu Hitam' },
];
