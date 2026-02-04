import api from './api';
import { MigrationPreviewResponse, MigrationApplyRequest, MigrationApplyResponse } from '@/types';

export const migrationService = {
  /**
   * Preview balance sheet migration from XLSX file
   */
  async previewMigration(file: File, port: string): Promise<MigrationPreviewResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('port', port);

    const response = await api.post<MigrationPreviewResponse>('/mida/migration/preview', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  /**
   * Apply balance sheet migration with user resolutions
   */
  async applyMigration(request: MigrationApplyRequest): Promise<MigrationApplyResponse> {
    const response = await api.post<MigrationApplyResponse>('/mida/migration/apply', request);
    return response.data;
  },
};
