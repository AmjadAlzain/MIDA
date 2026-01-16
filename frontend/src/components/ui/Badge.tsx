import React from 'react';
import { cn } from '@/utils';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'purple' | 'orange';
  size?: 'sm' | 'md';
  className?: string;
}

const variantStyles = {
  default: 'bg-gray-100 text-gray-700',
  success: 'bg-green-100 text-green-700',
  warning: 'bg-yellow-100 text-yellow-800',
  danger: 'bg-red-100 text-red-700',
  info: 'bg-blue-100 text-blue-700',
  purple: 'bg-purple-100 text-purple-700',
  orange: 'bg-orange-100 text-orange-700',
};

const sizeStyles = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-sm',
};

export function Badge({ children, variant = 'default', size = 'sm', className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center font-semibold rounded-full',
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
    >
      {children}
    </span>
  );
}

// Status-specific badge
interface StatusBadgeProps {
  status: 'active' | 'expired' | 'deleted' | 'draft' | 'confirmed' | string;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const variant = {
    active: 'success',
    confirmed: 'success',
    expired: 'danger',
    deleted: 'danger',
    draft: 'warning',
  }[status] || 'default';
  
  return (
    <Badge variant={variant as any} className={cn('capitalize', className)}>
      {status}
    </Badge>
  );
}
