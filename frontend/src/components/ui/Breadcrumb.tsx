import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/utils';

interface BreadcrumbItem {
  label: string;
  href?: string;
  icon?: React.ReactNode;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
  className?: string;
}

export function Breadcrumb({ items, className }: BreadcrumbProps) {
  return (
    <nav
      className={cn(
        'flex items-center gap-2 text-sm bg-gray-100 px-4 py-2.5 rounded-lg',
        className
      )}
    >
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        
        return (
          <React.Fragment key={index}>
            {index > 0 && <ChevronRight className="w-4 h-4 text-gray-400" />}
            {isLast || !item.href ? (
              <span
                className={cn(
                  'flex items-center gap-1',
                  isLast ? 'font-semibold text-gray-900' : 'text-gray-600'
                )}
              >
                {item.icon}
                {item.label}
              </span>
            ) : (
              <Link
                to={item.href}
                className="flex items-center gap-1 text-blue-600 hover:text-blue-800 hover:underline"
              >
                {item.icon}
                {item.label}
              </Link>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}
