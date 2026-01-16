import api from './api';
import { ClassificationResponse, K1ExportRequest } from '@/types';

export const classificationService = {
  /**
   * Classify invoice items into Form-D, MIDA, and Duties Payable categories
   */
  async classifyInvoice(params: {
    file: File;
    companyId: string;
    country: string;
    port?: string;
    importDate?: string;
    certificateIds?: string[];
  }): Promise<ClassificationResponse> {
    const formData = new FormData();
    formData.append('file', params.file);
    formData.append('company_id', params.companyId);
    formData.append('country', params.country);
    
    if (params.port) {
      formData.append('port', params.port);
    }
    if (params.importDate) {
      formData.append('import_date', params.importDate);
    }
    if (params.certificateIds && params.certificateIds.length > 0) {
      formData.append('mida_certificate_ids', params.certificateIds.join(','));
    }

    const response = await api.post<ClassificationResponse>('/convert/classify', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  /**
   * Export classified items to K1 XLS format
   */
  async exportK1(data: K1ExportRequest): Promise<Blob> {
    const response = await api.post('/convert/export-classified', data, {
      responseType: 'blob',
    });
    return response.data;
  },

  /**
   * Download the exported file
   */
  downloadBlob(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  },
};
