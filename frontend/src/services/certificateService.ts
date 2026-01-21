import api from './api';
import {
  Certificate,
  CertificateListResponse,
  CertificateItemsResponse,
  SaveCertificateRequest,
} from '@/types';

/**
 * Trigger file download from a blob response
 */
const downloadBlob = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const certificateService = {
  /**
   * Get paginated list of certificates
   */
  async getAll(params: { limit?: number; offset?: number } = {}): Promise<CertificateListResponse> {
    const response = await api.get<CertificateListResponse>('/mida/certificates', { params });
    return response.data;
  },

  /**
   * Get certificates by company name
   */
  async getByCompany(
    companyName: string,
    status: 'active' | 'expired' | 'all' = 'active'
  ): Promise<{ certificates: Certificate[] }> {
    const response = await api.get<{ certificates: Certificate[] }>(
      `/mida/certificates/by-company/${encodeURIComponent(companyName)}`,
      { params: { status } }
    );
    return response.data;
  },

  /**
   * Get a single certificate by ID
   */
  async getById(id: string): Promise<Certificate> {
    const response = await api.get<Certificate>(`/mida/certificates/${id}`);
    return response.data;
  },

  /**
   * Check if a certificate number already exists
   */
  async checkExists(certificateNumber: string): Promise<{ exists: boolean; status?: string; company_name?: string }> {
    const response = await api.get(`/mida/certificates/check/${encodeURIComponent(certificateNumber)}`);
    return response.data;
  },

  /**
   * Create a new certificate (draft)
   */
  async create(data: SaveCertificateRequest): Promise<Certificate> {
    const response = await api.post<Certificate>('/mida/certificates/draft', data);
    return response.data;
  },

  /**
   * Update an existing certificate
   */
  async update(id: string, data: SaveCertificateRequest): Promise<Certificate> {
    const response = await api.put<Certificate>(`/mida/certificates/${id}`, data);
    return response.data;
  },

  /**
   * Soft delete a certificate
   */
  async delete(id: string): Promise<void> {
    await api.delete(`/mida/certificates/${id}`);
  },

  /**
   * Get deleted certificates
   */
  async getDeleted(params: { limit?: number; offset?: number } = {}): Promise<CertificateListResponse> {
    const response = await api.get<CertificateListResponse>('/mida/certificates/deleted', { params });
    return response.data;
  },

  /**
   * Restore a deleted certificate
   */
  async restore(id: string): Promise<Certificate> {
    const response = await api.post<Certificate>(`/mida/certificates/${id}/restore`);
    return response.data;
  },

  /**
   * Permanently delete a certificate
   */
  async permanentDelete(id: string): Promise<void> {
    await api.delete(`/mida/certificates/${id}/permanent`);
  },

  /**
   * Get certificate items with balances
   */
  async getItemBalances(
    certificateId: string,
    params: { limit?: number; offset?: number } = {}
  ): Promise<CertificateItemsResponse> {
    const response = await api.get<CertificateItemsResponse>('/mida/imports/balances', {
      params: { certificate_id: certificateId, ...params },
    });
    return response.data;
  },

  /**
   * Parse a PDF certificate
   */
  async parsePdf(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await api.post('/mida/certificate/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  // =========================================================================
  // Export Functions
  // =========================================================================

  /**
   * Export a certificate to XLSX format
   */
  async exportCertificate(certificateId: string, certificateNumber: string): Promise<void> {
    const response = await api.get(`/mida/certificates/${certificateId}/export`, {
      responseType: 'blob',
    });
    
    const safeCertNum = certificateNumber.replace(/[/\\]/g, '_');
    const filename = `${safeCertNum}_certificate.xlsx`;
    downloadBlob(response.data, filename);
  },

  /**
   * Export an item's balance sheet to XLSX format
   * @param port - 'port_klang', 'klia', 'bukit_kayu_hitam', or undefined for all ports
   */
  async exportItemBalanceSheet(
    certificateId: string,
    itemId: string,
    certificateNumber: string,
    lineNo: number,
    port?: string
  ): Promise<void> {
    const params = port && port !== 'all' ? { port } : {};
    const response = await api.get(
      `/mida/certificates/${certificateId}/items/${itemId}/balance-sheet/export`,
      { params, responseType: 'blob' }
    );
    
    const safeCertNum = certificateNumber.replace(/[/\\]/g, '_');
    const portSuffix = port && port !== 'all' ? `_${port}` : '_all_ports';
    const filename = `${safeCertNum}_item${lineNo}_balance${portSuffix}.xlsx`;
    downloadBlob(response.data, filename);
  },

  /**
   * Export all items' balance sheets for a specific port
   */
  async exportAllBalanceSheets(
    certificateId: string,
    certificateNumber: string,
    port: string
  ): Promise<void> {
    const response = await api.get(
      `/mida/certificates/${certificateId}/balance-sheets/export`,
      { params: { port }, responseType: 'blob' }
    );
    
    const safeCertNum = certificateNumber.replace(/[/\\]/g, '_');
    const portDisplay: Record<string, string> = {
      port_klang: 'PortKlang',
      klia: 'KLIA',
      bukit_kayu_hitam: 'BKH',
    };
    const filename = `${safeCertNum}_all_balances_${portDisplay[port] || port}.xlsx`;
    downloadBlob(response.data, filename);
  },
};
