import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes with clsx
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a number with thousands separator and decimal places
 */
export function formatNumber(value: number | null | undefined, decimals = 3): string {
  if (value === null || value === undefined) return '-';
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format a date from ISO string to display format (DD/MM/YYYY)
 */
export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return '-';
  const date = new Date(isoDate);
  if (isNaN(date.getTime())) return isoDate;
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

/**
 * Format a date for HTML input (YYYY-MM-DD)
 */
export function formatDateForInput(isoDate: string | null | undefined): string {
  if (!isoDate) return '';
  const date = new Date(isoDate);
  if (isNaN(date.getTime())) return '';
  return date.toISOString().split('T')[0];
}

/**
 * Get today's date in ISO format (YYYY-MM-DD)
 */
export function getTodayISO(): string {
  return new Date().toISOString().split('T')[0];
}

/**
 * Escape HTML special characters
 */
export function escapeHtml(text: string | null | undefined): string {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Generate a unique ID
 */
export function generateId(): string {
  return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Debounce function
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  
  return (...args: Parameters<T>) => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => {
      func(...args);
    }, wait);
  };
}

/**
 * Get status class for quantity status
 */
export function getQuantityStatusClass(status: string): string {
  switch (status) {
    case 'normal':
      return 'text-green-600 font-semibold';
    case 'warning':
      return 'text-yellow-600 font-semibold';
    case 'depleted':
      return 'text-red-500 font-semibold';
    case 'overdrawn':
      return 'text-red-700 font-bold bg-red-50';
    default:
      return '';
  }
}

/**
 * Get port display name
 */
export function getPortDisplayName(port: string): string {
  switch (port) {
    case 'port_klang':
      return 'Port Klang';
    case 'klia':
      return 'KLIA';
    case 'bukit_kayu_hitam':
      return 'Bukit Kayu Hitam';
    default:
      return port;
  }
}
