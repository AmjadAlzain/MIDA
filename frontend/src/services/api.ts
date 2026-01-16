import axios, { AxiosError, AxiosInstance } from 'axios';
import { ApiError } from '@/types';

// Create axios instance with base configuration
const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
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
