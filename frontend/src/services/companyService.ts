import api from './api';
import { Company } from '@/types';

export const companyService = {
  /**
   * Get all companies
   */
  async getAll(): Promise<Company[]> {
    const response = await api.get<Company[]>('/companies');
    return response.data;
  },

  /**
   * Get company by ID
   */
  async getById(id: string): Promise<Company> {
    const response = await api.get<Company>(`/companies/${id}`);
    return response.data;
  },
};
