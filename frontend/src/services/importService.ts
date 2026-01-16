import api from './api';
import { ImportRecordsResponse, BulkImportRequest, ImportRecord } from '@/types';

export interface UpdateImportRequest {
  import_date?: string;
  declaration_form_reg_no?: string;
  invoice_number?: string;
  invoice_line?: number;
  quantity_imported?: number;
  port?: string;
  remarks?: string;
}

export const importService = {
  /**
   * Get import records for a specific item
   */
  async getByItemId(
    itemId: string,
    params: { port?: string; limit?: number; offset?: number } = {}
  ): Promise<ImportRecordsResponse> {
    const response = await api.get<ImportRecordsResponse>(`/mida/imports/history/item/${itemId}`, {
      params,
    });
    return response.data;
  },

  /**
   * Get a single import record by ID
   */
  async getById(recordId: string): Promise<ImportRecord> {
    const response = await api.get<ImportRecord>(`/mida/imports/${recordId}`);
    return response.data;
  },

  /**
   * Create bulk import records
   */
  async createBulk(data: BulkImportRequest): Promise<ImportRecord[]> {
    const response = await api.post<ImportRecord[]>('/mida/imports/bulk', data);
    return response.data;
  },

  /**
   * Update an import record
   */
  async update(recordId: string, data: UpdateImportRequest): Promise<ImportRecord> {
    const response = await api.put<ImportRecord>(`/mida/imports/${recordId}`, data);
    return response.data;
  },

  /**
   * Delete an import record
   */
  async delete(recordId: string): Promise<void> {
    await api.delete(`/mida/imports/${recordId}`);
  },
};
