import React from 'react';
import { cn } from '@/utils';

interface TabItem {
  id: string;
  label: React.ReactNode;
  count?: number;
  color?: 'blue' | 'green' | 'purple' | 'orange';
}

interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  className?: string;
}

const colorStyles = {
  blue: 'text-blue-600 border-blue-600',
  green: 'text-green-600 border-green-600',
  purple: 'text-purple-600 border-purple-600',
  orange: 'text-orange-600 border-orange-600',
};

const countColorStyles = {
  blue: 'bg-blue-600',
  green: 'bg-green-600',
  purple: 'bg-purple-600',
  orange: 'bg-orange-600',
};

export function Tabs({ tabs, activeTab, onTabChange, className }: TabsProps) {
  return (
    <div className={cn('border-b border-gray-200', className)}>
      <div className="flex gap-0">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab;
          const color = tab.color || 'blue';
          
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={cn(
                'px-4 py-3 font-semibold text-sm border-b-2 -mb-px transition-colors',
                isActive
                  ? colorStyles[color]
                  : 'text-gray-500 border-transparent hover:text-gray-700 hover:border-gray-300'
              )}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span
                  className={cn(
                    'ml-2 px-2 py-0.5 text-xs rounded-full text-white',
                    isActive ? countColorStyles[color] : 'bg-gray-400'
                  )}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
