import axios, { AxiosError, AxiosInstance } from 'axios';
import { ApiError } from '@/types';

// Create axios instance with base configuration
const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 minutes for long operations like classification and OCR
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for logging/auth
api.interceptors.request.use(
  (config) => {
    // Add any auth headers here if needed
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => {
    // Extract error message
    let message = 'An unexpected error occurred';
    
    if (error.response?.data) {
      const detail = error.response.data.detail;
      if (typeof detail === 'string') {
        message = detail;
      } else if (Array.isArray(detail)) {
        // Pydantic validation errors come as an array
        const messages = detail.map((err: { msg?: string; loc?: string[] }) => {
          const field = err.loc?.slice(-1)[0] || 'field';
          return `${field}: ${err.msg || 'validation error'}`;
        });
        message = messages.join('; ');
      } else if (detail && typeof detail === 'object' && 'detail' in detail) {
        message = detail.detail;
      }
    } else if (error.message) {
      message = error.message;
    }
    
    // Create a new error with the extracted message
    const customError = new Error(message);
    (customError as any).status = error.response?.status;
    (customError as any).originalError = error;
    
    return Promise.reject(customError);
  }
);

export default api;
