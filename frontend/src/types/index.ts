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
  item_count?: number;  // Used in list views where items aren't fully loaded
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

export interface ImportPreview {
  certificate_item_id: string;
  certificate_number: string;
  item_name: string;
  hs_code: string;
  port: string;
  quantity_to_import: number;
  current_balance: number;
  balance_after_import: number;
  new_status: string;
  will_trigger_warning: boolean;
  will_deplete: boolean;
  will_overdraw: boolean;
  warning_message?: string;
}

export interface ImportPreviewResponse {
  previews: ImportPreview[];
  has_warnings: boolean;
  has_depletions: boolean;
  has_overdrawns: boolean;
  total_items: number;
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
  // MIDA-specific fields
  mida_item_name?: string;
  remaining_qty?: number;
  remaining_port_klang?: number;
  remaining_klia?: number;
  remaining_bukit_kayu_hitam?: number;
  port_specific_remaining?: number;
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
  is_dummy?: boolean;
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
    is_dummy?: boolean;
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
  { code: 'AF', name: 'Afghanistan' },
  { code: 'AL', name: 'Albania' },
  { code: 'DZ', name: 'Algeria' },
  { code: 'AD', name: 'Andorra' },
  { code: 'AO', name: 'Angola' },
  { code: 'AG', name: 'Antigua and Barbuda' },
  { code: 'AR', name: 'Argentina' },
  { code: 'AM', name: 'Armenia' },
  { code: 'AU', name: 'Australia' },
  { code: 'AT', name: 'Austria' },
  { code: 'AZ', name: 'Azerbaijan' },
  { code: 'BS', name: 'Bahamas' },
  { code: 'BH', name: 'Bahrain' },
  { code: 'BD', name: 'Bangladesh' },
  { code: 'BB', name: 'Barbados' },
  { code: 'BY', name: 'Belarus' },
  { code: 'BE', name: 'Belgium' },
  { code: 'BZ', name: 'Belize' },
  { code: 'BJ', name: 'Benin' },
  { code: 'BT', name: 'Bhutan' },
  { code: 'BO', name: 'Bolivia' },
  { code: 'BA', name: 'Bosnia and Herzegovina' },
  { code: 'BW', name: 'Botswana' },
  { code: 'BR', name: 'Brazil' },
  { code: 'BN', name: 'Brunei' },
  { code: 'BG', name: 'Bulgaria' },
  { code: 'BF', name: 'Burkina Faso' },
  { code: 'BI', name: 'Burundi' },
  { code: 'KH', name: 'Cambodia' },
  { code: 'CM', name: 'Cameroon' },
  { code: 'CA', name: 'Canada' },
  { code: 'CV', name: 'Cape Verde' },
  { code: 'CF', name: 'Central African Republic' },
  { code: 'TD', name: 'Chad' },
  { code: 'CL', name: 'Chile' },
  { code: 'CN', name: 'China' },
  { code: 'CO', name: 'Colombia' },
  { code: 'KM', name: 'Comoros' },
  { code: 'CG', name: 'Congo' },
  { code: 'CD', name: 'Congo, Democratic Republic' },
  { code: 'CR', name: 'Costa Rica' },
  { code: 'CI', name: "Côte d'Ivoire" },
  { code: 'HR', name: 'Croatia' },
  { code: 'CU', name: 'Cuba' },
  { code: 'CY', name: 'Cyprus' },
  { code: 'CZ', name: 'Czech Republic' },
  { code: 'DK', name: 'Denmark' },
  { code: 'DJ', name: 'Djibouti' },
  { code: 'DM', name: 'Dominica' },
  { code: 'DO', name: 'Dominican Republic' },
  { code: 'EC', name: 'Ecuador' },
  { code: 'EG', name: 'Egypt' },
  { code: 'SV', name: 'El Salvador' },
  { code: 'GQ', name: 'Equatorial Guinea' },
  { code: 'ER', name: 'Eritrea' },
  { code: 'EE', name: 'Estonia' },
  { code: 'SZ', name: 'Eswatini' },
  { code: 'ET', name: 'Ethiopia' },
  { code: 'FJ', name: 'Fiji' },
  { code: 'FI', name: 'Finland' },
  { code: 'FR', name: 'France' },
  { code: 'GA', name: 'Gabon' },
  { code: 'GM', name: 'Gambia' },
  { code: 'GE', name: 'Georgia' },
  { code: 'DE', name: 'Germany' },
  { code: 'GH', name: 'Ghana' },
  { code: 'GR', name: 'Greece' },
  { code: 'GD', name: 'Grenada' },
  { code: 'GT', name: 'Guatemala' },
  { code: 'GN', name: 'Guinea' },
  { code: 'GW', name: 'Guinea-Bissau' },
  { code: 'GY', name: 'Guyana' },
  { code: 'HT', name: 'Haiti' },
  { code: 'HN', name: 'Honduras' },
  { code: 'HK', name: 'Hong Kong' },
  { code: 'HU', name: 'Hungary' },
  { code: 'IS', name: 'Iceland' },
  { code: 'IN', name: 'India' },
  { code: 'ID', name: 'Indonesia' },
  { code: 'IR', name: 'Iran' },
  { code: 'IQ', name: 'Iraq' },
  { code: 'IE', name: 'Ireland' },
  { code: 'IL', name: 'Israel' },
  { code: 'IT', name: 'Italy' },
  { code: 'JM', name: 'Jamaica' },
  { code: 'JP', name: 'Japan' },
  { code: 'JO', name: 'Jordan' },
  { code: 'KZ', name: 'Kazakhstan' },
  { code: 'KE', name: 'Kenya' },
  { code: 'KI', name: 'Kiribati' },
  { code: 'KP', name: 'Korea, North' },
  { code: 'KR', name: 'Korea, South' },
  { code: 'KW', name: 'Kuwait' },
  { code: 'KG', name: 'Kyrgyzstan' },
  { code: 'LA', name: 'Laos' },
  { code: 'LV', name: 'Latvia' },
  { code: 'LB', name: 'Lebanon' },
  { code: 'LS', name: 'Lesotho' },
  { code: 'LR', name: 'Liberia' },
  { code: 'LY', name: 'Libya' },
  { code: 'LI', name: 'Liechtenstein' },
  { code: 'LT', name: 'Lithuania' },
  { code: 'LU', name: 'Luxembourg' },
  { code: 'MO', name: 'Macau' },
  { code: 'MG', name: 'Madagascar' },
  { code: 'MW', name: 'Malawi' },
  { code: 'MY', name: 'Malaysia' },
  { code: 'MV', name: 'Maldives' },
  { code: 'ML', name: 'Mali' },
  { code: 'MT', name: 'Malta' },
  { code: 'MH', name: 'Marshall Islands' },
  { code: 'MR', name: 'Mauritania' },
  { code: 'MU', name: 'Mauritius' },
  { code: 'MX', name: 'Mexico' },
  { code: 'FM', name: 'Micronesia' },
  { code: 'MD', name: 'Moldova' },
  { code: 'MC', name: 'Monaco' },
  { code: 'MN', name: 'Mongolia' },
  { code: 'ME', name: 'Montenegro' },
  { code: 'MA', name: 'Morocco' },
  { code: 'MZ', name: 'Mozambique' },
  { code: 'MM', name: 'Myanmar' },
  { code: 'NA', name: 'Namibia' },
  { code: 'NR', name: 'Nauru' },
  { code: 'NP', name: 'Nepal' },
  { code: 'NL', name: 'Netherlands' },
  { code: 'NZ', name: 'New Zealand' },
  { code: 'NI', name: 'Nicaragua' },
  { code: 'NE', name: 'Niger' },
  { code: 'NG', name: 'Nigeria' },
  { code: 'MK', name: 'North Macedonia' },
  { code: 'NO', name: 'Norway' },
  { code: 'OM', name: 'Oman' },
  { code: 'PK', name: 'Pakistan' },
  { code: 'PW', name: 'Palau' },
  { code: 'PS', name: 'Palestine' },
  { code: 'PA', name: 'Panama' },
  { code: 'PG', name: 'Papua New Guinea' },
  { code: 'PY', name: 'Paraguay' },
  { code: 'PE', name: 'Peru' },
  { code: 'PH', name: 'Philippines' },
  { code: 'PL', name: 'Poland' },
  { code: 'PT', name: 'Portugal' },
  { code: 'QA', name: 'Qatar' },
  { code: 'RO', name: 'Romania' },
  { code: 'RU', name: 'Russia' },
  { code: 'RW', name: 'Rwanda' },
  { code: 'KN', name: 'Saint Kitts and Nevis' },
  { code: 'LC', name: 'Saint Lucia' },
  { code: 'VC', name: 'Saint Vincent and the Grenadines' },
  { code: 'WS', name: 'Samoa' },
  { code: 'SM', name: 'San Marino' },
  { code: 'ST', name: 'Sao Tome and Principe' },
  { code: 'SA', name: 'Saudi Arabia' },
  { code: 'SN', name: 'Senegal' },
  { code: 'RS', name: 'Serbia' },
  { code: 'SC', name: 'Seychelles' },
  { code: 'SL', name: 'Sierra Leone' },
  { code: 'SG', name: 'Singapore' },
  { code: 'SK', name: 'Slovakia' },
  { code: 'SI', name: 'Slovenia' },
  { code: 'SB', name: 'Solomon Islands' },
  { code: 'SO', name: 'Somalia' },
  { code: 'ZA', name: 'South Africa' },
  { code: 'SS', name: 'South Sudan' },
  { code: 'ES', name: 'Spain' },
  { code: 'LK', name: 'Sri Lanka' },
  { code: 'SD', name: 'Sudan' },
  { code: 'SR', name: 'Suriname' },
  { code: 'SE', name: 'Sweden' },
  { code: 'CH', name: 'Switzerland' },
  { code: 'SY', name: 'Syria' },
  { code: 'TW', name: 'Taiwan' },
  { code: 'TJ', name: 'Tajikistan' },
  { code: 'TZ', name: 'Tanzania' },
  { code: 'TH', name: 'Thailand' },
  { code: 'TL', name: 'Timor-Leste' },
  { code: 'TG', name: 'Togo' },
  { code: 'TO', name: 'Tonga' },
  { code: 'TT', name: 'Trinidad and Tobago' },
  { code: 'TN', name: 'Tunisia' },
  { code: 'TR', name: 'Turkey' },
  { code: 'TM', name: 'Turkmenistan' },
  { code: 'TV', name: 'Tuvalu' },
  { code: 'UG', name: 'Uganda' },
  { code: 'UA', name: 'Ukraine' },
  { code: 'AE', name: 'United Arab Emirates' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'US', name: 'United States' },
  { code: 'UY', name: 'Uruguay' },
  { code: 'UZ', name: 'Uzbekistan' },
  { code: 'VU', name: 'Vanuatu' },
  { code: 'VA', name: 'Vatican City' },
  { code: 'VE', name: 'Venezuela' },
  { code: 'VN', name: 'Vietnam' },
  { code: 'YE', name: 'Yemen' },
  { code: 'ZM', name: 'Zambia' },
  { code: 'ZW', name: 'Zimbabwe' },
] as const;

export const PORTS: { value: Port; label: string }[] = [
  { value: 'port_klang', label: 'Port Klang' },
  { value: 'klia', label: 'KLIA' },
  { value: 'bukit_kayu_hitam', label: 'Bukit Kayu Hitam' },
];
