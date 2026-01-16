import React, { useCallback } from 'react';
import { cn } from '@/utils';
import { Upload, File, X } from 'lucide-react';

interface FileUploadProps {
  accept?: string;
  label?: string;
  helperText?: string;
  value?: File | null;
  onChange: (file: File | null) => void;
  error?: string;
  disabled?: boolean;
}

export function FileUpload({
  accept,
  label,
  helperText,
  value,
  onChange,
  error,
  disabled = false,
}: FileUploadProps) {
  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (disabled) return;
      
      const file = e.dataTransfer.files[0];
      if (file) {
        onChange(file);
      }
    },
    [onChange, disabled]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0] || null;
      onChange(file);
      // Reset input value to allow selecting the same file again
      e.target.value = '';
    },
    [onChange]
  );

  const handleClear = useCallback(() => {
    onChange(null);
  }, [onChange]);

  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-semibold text-gray-700 mb-1">
          {label}
        </label>
      )}
      
      <div
        className={cn(
          'relative border-2 border-dashed rounded-lg p-6 transition-colors',
          'hover:border-blue-400 hover:bg-blue-50/50',
          disabled
            ? 'bg-gray-100 cursor-not-allowed border-gray-300'
            : error
            ? 'border-red-400 bg-red-50/50'
            : value
            ? 'border-green-400 bg-green-50/50'
            : 'border-gray-300 bg-gray-50'
        )}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        <input
          type="file"
          accept={accept}
          onChange={handleChange}
          disabled={disabled}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
        />
        
        {value ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <File className="w-8 h-8 text-green-600" />
              <div>
                <p className="font-medium text-gray-900">{value.name}</p>
                <p className="text-sm text-gray-500">
                  {(value.size / 1024).toFixed(1)} KB
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleClear();
              }}
              className="p-2 rounded-full hover:bg-red-100 text-red-600"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        ) : (
          <div className="text-center">
            <Upload className="mx-auto h-10 w-10 text-gray-400 mb-2" />
            <p className="text-sm text-gray-600">
              <span className="font-semibold text-blue-600">Click to upload</span> or
              drag and drop
            </p>
            {helperText && (
              <p className="text-xs text-gray-500 mt-1">{helperText}</p>
            )}
          </div>
        )}
      </div>
      
      {error && <p className="mt-1 text-sm text-red-500">{error}</p>}
    </div>
  );
}
