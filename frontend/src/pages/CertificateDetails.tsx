import { useState, useRef, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ArrowLeft,
  Edit2,
  Save,
  X,
  Package,
  Calendar,
  FileText,
  BarChart3,
  Plus,
  Trash2,
  Download,
  ChevronDown,
  TableIcon,
  LayoutList,
  AlertCircle,
  AlertTriangle,
} from 'lucide-react';
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  Input,
  Badge,
  StatusBadge,
  Breadcrumb,
  Alert,
  ConfirmModal,
} from '@/components/ui';
import { certificateService } from '@/services';
import {
  Certificate,
  CertificateItem,
  CertificateItemBalance,
  CertificateItemsResponse,
  SaveCertificateRequest,
  PORTS,
} from '@/types';
import { cn, formatNumber, formatDate, getQuantityStatusClass } from '@/utils';

export function CertificateDetails() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // State
  const [isEditing, setIsEditing] = useState(false);
  const [editedCertificate, setEditedCertificate] = useState<Certificate | null>(null);
  const [deleteItemIndex, setDeleteItemIndex] = useState<number | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [showExportDropdown, setShowExportDropdown] = useState(false);
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('table');
  const exportDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (exportDropdownRef.current && !exportDropdownRef.current.contains(event.target as Node)) {
        setShowExportDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch certificate
  const {
    data: certificate,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['certificate', id],
    queryFn: () => certificateService.getById(id!),
    enabled: !!id,
  });

  // Fetch item balances
  const { data: balancesResponse } = useQuery<CertificateItemsResponse>({
    queryKey: ['certificate-balances', id],
    queryFn: () => certificateService.getItemBalances(id!),
    enabled: !!id,
    staleTime: 0, // Always refetch balance data to ensure up-to-date values
    refetchOnMount: 'always', // Always refetch when component mounts
  });

  const itemBalances = balancesResponse?.items ?? [];

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: SaveCertificateRequest) =>
      certificateService.update(id!, data),
    onSuccess: () => {
      toast.success('Certificate updated successfully');
      queryClient.invalidateQueries({ queryKey: ['certificate', id] });
      queryClient.invalidateQueries({ queryKey: ['certificate-balances', id] });
      setIsEditing(false);
      setEditedCertificate(null);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update certificate');
    },
  });

  // Validation types
  interface ValidationWarning {
    type: 'error' | 'warning' | 'info';
    field?: string;
    itemIndex?: number;
    message: string;
  }

  // Validation logic
  const validationWarnings = useMemo((): ValidationWarning[] => {
    if (!isEditing || !editedCertificate) return [];
    
    const warnings: ValidationWarning[] = [];
    
    // Header field validation
    if (!editedCertificate.certificate_number || editedCertificate.certificate_number.trim() === '') {
      warnings.push({ type: 'error', field: 'certificate_number', message: 'Certificate Number is required' });
    }
    if (!editedCertificate.company_name || editedCertificate.company_name.trim() === '') {
      warnings.push({ type: 'error', field: 'company_name', message: 'Company Name is required' });
    }
    if (!editedCertificate.model_number || editedCertificate.model_number.trim() === '') {
      warnings.push({ type: 'error', field: 'model_number', message: 'Model Number is required' });
    }
    if (!editedCertificate.exemption_start_date) {
      warnings.push({ type: 'warning', field: 'exemption_start_date', message: 'Exemption Start Date is missing' });
    }
    if (!editedCertificate.exemption_end_date) {
      warnings.push({ type: 'warning', field: 'exemption_end_date', message: 'Exemption End Date is missing' });
    }
    
    // Item validation
    const items = editedCertificate.items || [];
    if (items.length === 0) {
      warnings.push({ type: 'error', message: 'At least one item is required' });
    }
    
    items.forEach((item, index) => {
      const lineLabel = `Item #${item.line_no || index + 1}`;
      const isNewItem = item.id?.startsWith('temp-');
      
      if (!item.hs_code || item.hs_code.trim() === '') {
        warnings.push({ type: 'error', itemIndex: index, field: 'hs_code', message: `${lineLabel}: HS Code is required` });
      }
      if (!item.item_name || item.item_name.trim() === '') {
        warnings.push({ type: 'error', itemIndex: index, field: 'item_name', message: `${lineLabel}: Item Name is required` });
      }
      if (!item.uom || item.uom.trim() === '') {
        warnings.push({ type: 'error', itemIndex: index, field: 'uom', message: `${lineLabel}: UOM is required` });
      }
      
      // Only validate quantities for new items (existing items have read-only quantities)
      if (isNewItem) {
        if (!item.approved_quantity || item.approved_quantity <= 0) {
          warnings.push({ type: 'error', itemIndex: index, field: 'approved_quantity', message: `${lineLabel}: Approved Quantity must be greater than 0` });
        }
        
        // Quantity discrepancy check - always compare approved qty with station sum
        const portKlang = item.port_klang_qty || 0;
        const klia = item.klia_qty || 0;
        const bukitKayuHitam = item.bukit_kayu_hitam_qty || 0;
        const stationSum = portKlang + klia + bukitKayuHitam;
        const approvedQty = item.approved_quantity || 0;
        
        // Show warning if approved qty doesn't match station sum
        const difference = Math.abs(approvedQty - stationSum);
        if (difference > 0.01) {
          warnings.push({
            type: 'warning',
            itemIndex: index,
            message: `${lineLabel}: Quantity mismatch - Approved (${formatNumber(approvedQty)}) ≠ Station Sum (${formatNumber(stationSum)})`,
          });
        }
      }
    });
    
    // Check for duplicate line numbers
    const lineNumbers = items.map((i) => i.line_no);
    const duplicates = lineNumbers.filter((v, i, a) => a.indexOf(v) !== i);
    if (duplicates.length > 0) {
      warnings.push({
        type: 'error',
        message: `Duplicate line numbers found: ${[...new Set(duplicates)].join(', ')}`,
      });
    }
    
    return warnings;
  }, [isEditing, editedCertificate]);

  const errorCount = validationWarnings.filter((w) => w.type === 'error').length;
  const warningCount = validationWarnings.filter((w) => w.type === 'warning').length;
  const hasBlockingErrors = errorCount > 0;

  // Check if a specific field has an error
  const getFieldError = (field: string, itemIndex?: number): boolean => {
    return validationWarnings.some(
      (w) => w.type === 'error' && w.field === field && w.itemIndex === itemIndex
    );
  };

  // Check if a specific field has a warning
  const getFieldWarning = (field: string, itemIndex?: number): boolean => {
    return validationWarnings.some(
      (w) => w.type === 'warning' && w.field === field && w.itemIndex === itemIndex
    );
  };

  // Check if an item has any error
  const getItemHasError = (itemIndex: number): boolean => {
    return validationWarnings.some(
      (w) => w.type === 'error' && w.itemIndex === itemIndex
    );
  };

  // Check if an item has any warning
  const getItemHasWarning = (itemIndex: number): boolean => {
    return validationWarnings.some(
      (w) => w.type === 'warning' && w.itemIndex === itemIndex
    );
  };

  // Get cell class based on validation state
  const getCellClass = (field: string, itemIndex: number): string => {
    if (getFieldError(field, itemIndex)) {
      return 'border-red-500 bg-red-50';
    }
    if (getFieldWarning(field, itemIndex)) {
      return 'border-yellow-500 bg-yellow-50';
    }
    return 'border-gray-300';
  };

  // Start editing
  const handleStartEdit = () => {
    setEditedCertificate(certificate ? { ...certificate, items: [...(certificate.items || [])] } : null);
    setIsEditing(true);
  };

  // Cancel editing
  const handleCancelEdit = () => {
    setEditedCertificate(null);
    setIsEditing(false);
  };

  // Save changes
  const handleSave = () => {
    if (!editedCertificate) return;

    // Block save if there are validation errors
    if (hasBlockingErrors) {
      toast.error(`Cannot save: ${errorCount} error(s) must be fixed first`);
      return;
    }

    // Show warning about non-blocking issues
    if (warningCount > 0) {
      const proceed = window.confirm(
        `There are ${warningCount} warning(s). Do you want to proceed anyway?`
      );
      if (!proceed) return;
    }

    // Build the request matching SaveCertificateRequest
    const updateData: SaveCertificateRequest = {
      header: {
        certificate_number: editedCertificate.certificate_number,
        company_name: editedCertificate.company_name,
        model_number: editedCertificate.model_number,
        exemption_start_date: editedCertificate.exemption_start_date,
        exemption_end_date: editedCertificate.exemption_end_date,
        source_filename: editedCertificate.source_filename,
      },
      items: editedCertificate.items?.map((item) => ({
        line_no: item.line_no,
        hs_code: item.hs_code,
        item_name: item.item_name,
        uom: item.uom,
        approved_quantity: item.approved_quantity,
        port_klang_qty: item.port_klang_qty,
        klia_qty: item.klia_qty,
        bukit_kayu_hitam_qty: item.bukit_kayu_hitam_qty,
      })) || [],
    };

    updateMutation.mutate(updateData);
  };

  // Field change handler
  const handleFieldChange = (field: keyof Certificate, value: string) => {
    setEditedCertificate((prev) => (prev ? { ...prev, [field]: value } : null));
  };

  // Item field change handler
  const handleItemChange = (index: number, field: keyof CertificateItem, value: string | number) => {
    setEditedCertificate((prev) => {
      if (!prev || !prev.items) return prev;
      const items = [...prev.items];
      items[index] = { ...items[index], [field]: value };
      return { ...prev, items };
    });
  };

  // Add new item
  const handleAddItem = () => {
    setEditedCertificate((prev) => {
      if (!prev) return prev;
      const items = prev.items || [];
      // Use max line_no + 1 to ensure unique line number
      const maxLineNo = items.length > 0 ? Math.max(...items.map(i => i.line_no)) : 0;
      const newItem: CertificateItem = {
        id: `temp-${Date.now()}`,
        line_no: maxLineNo + 1,
        hs_code: '',
        item_name: '',
        uom: '',
        approved_quantity: 0,
        port_klang_qty: 0,
        klia_qty: 0,
        bukit_kayu_hitam_qty: 0,
      };
      return { ...prev, items: [...items, newItem] };
    });
  };

  // Remove item
  const handleRemoveItem = (index: number) => {
    setEditedCertificate((prev) => {
      if (!prev || !prev.items) return prev;
      // Remove the item but DO NOT renumber - preserve line_no for backend matching
      const items = prev.items.filter((_, i) => i !== index);
      return { ...prev, items };
    });
    setDeleteItemIndex(null);
  };

  // Get balance for an item
  const getItemBalance = (itemId: string): CertificateItemBalance | undefined => {
    return itemBalances.find((b) => b.item_id === itemId);
  };

  // Export certificate to XLSX
  const handleExportCertificate = async () => {
    if (!certificate) return;
    setIsExporting(true);
    try {
      await certificateService.exportCertificate(certificate.id, certificate.certificate_number);
      toast.success('Certificate exported successfully');
    } catch (error) {
      toast.error('Failed to export certificate');
    } finally {
      setIsExporting(false);
    }
  };

  // Export all balance sheets for a specific port
  const handleExportAllBalanceSheets = async (port: string) => {
    if (!certificate) return;
    setIsExporting(true);
    setShowExportDropdown(false);
    try {
      await certificateService.exportAllBalanceSheets(certificate.id, certificate.certificate_number, port);
      toast.success('Balance sheets exported successfully');
    } catch (error) {
      toast.error('Failed to export balance sheets');
    } finally {
      setIsExporting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error || !certificate) {
    return (
      <Alert variant="error" title="Error">
        Certificate not found or failed to load.
        <Button variant="secondary" onClick={() => navigate('/database')} className="mt-4">
          Back to Database
        </Button>
      </Alert>
    );
  }

  const currentData = isEditing && editedCertificate ? editedCertificate : certificate;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { label: 'Database', href: '/database' },
          { label: certificate.certificate_number },
        ]}
      />

      {/* Header */}
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-gray-900">
                {certificate.certificate_number}
              </h1>
              <StatusBadge status={certificate.status} />
            </div>
            <p className="text-gray-600">{certificate.company_name}</p>
            {certificate.model_number && (
              <p className="text-sm text-gray-500">Model: {certificate.model_number}</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                {hasBlockingErrors && (
                  <span className="text-red-600 text-sm flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    Fix errors to save
                  </span>
                )}
                {!hasBlockingErrors && warningCount > 0 && (
                  <span className="text-yellow-600 text-sm flex items-center gap-1">
                    <AlertTriangle className="w-4 h-4" />
                    {warningCount} warning(s)
                  </span>
                )}
                <Button variant="secondary" onClick={handleCancelEdit}>
                  <X className="w-4 h-4 mr-2" />
                  Cancel
                </Button>
                <Button
                  variant={hasBlockingErrors ? 'secondary' : 'success'}
                  onClick={handleSave}
                  isLoading={updateMutation.isPending}
                  disabled={hasBlockingErrors}
                >
                  <Save className="w-4 h-4 mr-2" />
                  Save
                </Button>
              </>
            ) : (
              <>
                <Button variant="secondary" onClick={() => navigate('/database')}>
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back
                </Button>
                {certificate.status !== 'deleted' && (
                  <>
                    <Button variant="primary" onClick={handleStartEdit}>
                      <Edit2 className="w-4 h-4 mr-2" />
                      Edit
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={handleExportCertificate}
                      isLoading={isExporting}
                      disabled={isExporting}
                    >
                      <Download className="w-4 h-4 mr-2" />
                      Export Certificate
                    </Button>
                    <div className="relative" ref={exportDropdownRef}>
                      <Button
                        variant="secondary"
                        onClick={() => setShowExportDropdown(!showExportDropdown)}
                        disabled={isExporting}
                      >
                        <Download className="w-4 h-4 mr-2" />
                        Export All Balances
                        <ChevronDown className="w-4 h-4 ml-2" />
                      </Button>
                      {showExportDropdown && (
                        <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-10">
                          {PORTS.map((port) => (
                            <button
                              key={port.value}
                              onClick={() => handleExportAllBalanceSheets(port.value)}
                              className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                            >
                              {port.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </Card>

      {/* Certificate Details */}
      <Card>
        <CardHeader>
          <CardTitle icon={<FileText className="w-5 h-5 text-blue-600" />}>
            Certificate Information
          </CardTitle>
        </CardHeader>

        {isEditing ? (
          <div className="grid md:grid-cols-3 gap-4">
            <Input
              label="Certificate Number"
              value={currentData.certificate_number}
              onChange={(e) => handleFieldChange('certificate_number', e.target.value)}
              required
              error={getFieldError('certificate_number') ? 'Required' : undefined}
              className={getFieldError('certificate_number') ? 'border-red-500' : ''}
            />
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
              <select
                value={currentData.company_name}
                onChange={(e) => handleFieldChange('company_name', e.target.value)}
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                  getFieldError('company_name') ? 'border-red-500 bg-red-50' : 'border-gray-300'
                }`}
              >
                <option value="">Select Company...</option>
                <option value="HONG LEONG YAMAHA MOTOR SDN BHD">HONG LEONG YAMAHA MOTOR SDN BHD</option>
                <option value="HICOM YAMAHA MOTOR SDN BHD">HICOM YAMAHA MOTOR SDN BHD</option>
              </select>
            </div>
            <Input
              label="Model Number"
              value={currentData.model_number || ''}
              onChange={(e) => handleFieldChange('model_number', e.target.value)}
              required
              error={getFieldError('model_number') ? 'Required' : undefined}
              className={getFieldError('model_number') ? 'border-red-500' : ''}
            />
            <Input
              label="Exemption Start"
              type="date"
              value={currentData.exemption_start_date?.split('T')[0] || ''}
              onChange={(e) => handleFieldChange('exemption_start_date', e.target.value)}
              className={getFieldWarning('exemption_start_date') ? 'border-yellow-500' : ''}
            />
            <Input
              label="Exemption End"
              type="date"
              value={currentData.exemption_end_date?.split('T')[0] || ''}
              onChange={(e) => handleFieldChange('exemption_end_date', e.target.value)}
              className={getFieldWarning('exemption_end_date') ? 'border-yellow-500' : ''}
            />
          </div>
        ) : (
          <div className="grid md:grid-cols-3 gap-6">
            <div className="flex items-start gap-3">
              <Calendar className="w-5 h-5 text-gray-400 mt-0.5" />
              <div>
                <p className="text-sm text-gray-500">Exemption Period</p>
                <p className="font-medium">
                  {formatDate(certificate.exemption_start_date)} -{' '}
                  {formatDate(certificate.exemption_end_date)}
                </p>
              </div>
            </div>
            {certificate.model_number && (
              <div className="flex items-start gap-3">
                <Package className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="text-sm text-gray-500">Model Number</p>
                  <p className="font-medium">{certificate.model_number}</p>
                </div>
              </div>
            )}
            {certificate.source_filename && (
              <div className="flex items-start gap-3">
                <FileText className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="text-sm text-gray-500">Source File</p>
                  <p className="font-medium">{certificate.source_filename}</p>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Certificate Items */}
      <Card>
        <CardHeader
          action={
            <div className="flex items-center gap-2">
              {/* View Mode Toggle */}
              <div className="flex items-center gap-1 border border-gray-200 rounded-lg p-0.5">
                <button
                  onClick={() => setViewMode('table')}
                  className={`p-1.5 rounded ${viewMode === 'table' ? 'bg-blue-100 text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}
                  title="Table View"
                >
                  <TableIcon className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewMode('cards')}
                  className={`p-1.5 rounded ${viewMode === 'cards' ? 'bg-blue-100 text-blue-600' : 'text-gray-400 hover:text-gray-600'}`}
                  title="Card View"
                >
                  <LayoutList className="w-4 h-4" />
                </button>
              </div>
            </div>
          }
        >
          <CardTitle icon={<Package className="w-5 h-5 text-purple-600" />}>
            Certificate Items
            <Badge variant="purple" className="ml-2">
              {(isEditing && editedCertificate?.items?.length) || certificate.items?.length || 0}
            </Badge>
          </CardTitle>
        </CardHeader>

        {/* Editable Mode */}
        {isEditing && editedCertificate?.items && editedCertificate.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-3 py-3 text-left font-semibold w-16">Line #</th>
                  <th className="px-3 py-3 text-left font-semibold" style={{ minWidth: '120px' }}>HS Code</th>
                  <th className="px-3 py-3 text-left font-semibold" style={{ minWidth: '200px' }}>Item Name</th>
                  <th className="px-3 py-3 text-right font-semibold" style={{ minWidth: '120px' }}>Approved Qty</th>
                  <th className="px-3 py-3 text-left font-semibold w-24">UOM</th>
                  <th className="px-3 py-3 text-right font-semibold" style={{ minWidth: '120px' }}>Port Klang</th>
                  <th className="px-3 py-3 text-right font-semibold" style={{ minWidth: '120px' }}>KLIA</th>
                  <th className="px-3 py-3 text-right font-semibold" style={{ minWidth: '120px' }}>BKH</th>
                  <th className="px-3 py-3 text-center font-semibold w-16">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {editedCertificate.items.map((item, index) => (
                  <tr key={item.id || index} className={`hover:bg-gray-50 ${getItemHasError(index) ? 'bg-red-50' : getItemHasWarning(index) ? 'bg-yellow-50' : ''}`}>
                    <td className="px-3 py-2">
                      <span className="bg-purple-100 text-purple-700 px-2 py-1 rounded text-xs font-semibold">
                        {item.line_no}
                      </span>
                    </td>
                    <td className="px-3 py-2" style={{ minWidth: '120px' }}>
                      <input
                        type="text"
                        value={item.hs_code}
                        onChange={(e) => handleItemChange(index, 'hs_code', e.target.value)}
                        className={`w-full px-2 py-1.5 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm ${getCellClass('hs_code', index)}`}
                      />
                    </td>
                    <td className="px-3 py-2" style={{ minWidth: '200px' }}>
                      <input
                        type="text"
                        value={item.item_name}
                        onChange={(e) => handleItemChange(index, 'item_name', e.target.value)}
                        className={`w-full px-2 py-1.5 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm ${getCellClass('item_name', index)}`}
                      />
                    </td>
                    <td className="px-3 py-2" style={{ minWidth: '120px' }}>
                      {item.id?.startsWith('temp-') ? (
                        <input
                          type="number"
                          value={item.approved_quantity}
                          onChange={(e) => handleItemChange(index, 'approved_quantity', parseFloat(e.target.value) || 0)}
                          className={`w-full px-2 py-1.5 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-right ${getCellClass('approved_quantity', index)}`}
                        />
                      ) : (
                        <span className="block w-full px-2 py-1.5 text-sm text-right text-gray-700">
                          {formatNumber(item.approved_quantity)}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={item.uom}
                        onChange={(e) => handleItemChange(index, 'uom', e.target.value)}
                        className={`w-full px-2 py-1.5 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm ${getCellClass('uom', index)}`}
                      >
                        <option value="">Select...</option>
                        <option value="KGM">KGM</option>
                        <option value="UNT">UNT</option>
                      </select>
                    </td>
                    <td className="px-3 py-2" style={{ minWidth: '120px' }}>
                      {item.id?.startsWith('temp-') ? (
                        <input
                          type="number"
                          value={item.port_klang_qty || 0}
                          onChange={(e) => handleItemChange(index, 'port_klang_qty', parseFloat(e.target.value) || 0)}
                          className={`w-full px-2 py-1.5 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-right ${getCellClass('port_klang_qty', index)}`}
                          title="Port Klang Quantity"
                        />
                      ) : (
                        <span className="block w-full px-2 py-1.5 text-sm text-right text-gray-700">
                          {formatNumber(item.port_klang_qty || 0)}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2" style={{ minWidth: '120px' }}>
                      {item.id?.startsWith('temp-') ? (
                        <input
                          type="number"
                          value={item.klia_qty || 0}
                          onChange={(e) => handleItemChange(index, 'klia_qty', parseFloat(e.target.value) || 0)}
                          className={`w-full px-2 py-1.5 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-right ${getCellClass('klia_qty', index)}`}
                          title="KLIA Quantity"
                        />
                      ) : (
                        <span className="block w-full px-2 py-1.5 text-sm text-right text-gray-700">
                          {formatNumber(item.klia_qty || 0)}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2" style={{ minWidth: '120px' }}>
                      {item.id?.startsWith('temp-') ? (
                        <input
                          type="number"
                          value={item.bukit_kayu_hitam_qty || 0}
                          onChange={(e) => handleItemChange(index, 'bukit_kayu_hitam_qty', parseFloat(e.target.value) || 0)}
                          className={`w-full px-2 py-1.5 border rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-right ${getCellClass('bukit_kayu_hitam_qty', index)}`}
                          title="Bukit Kayu Hitam Quantity"
                        />
                      ) : (
                        <span className="block w-full px-2 py-1.5 text-sm text-right text-gray-700">
                          {formatNumber(item.bukit_kayu_hitam_qty || 0)}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleteItemIndex(index)}
                        className="text-red-600 hover:bg-red-50"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* Add Item button at bottom */}
            <div className="p-4 border-t border-gray-200">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleAddItem}
                leftIcon={<Plus className="w-4 h-4" />}
              >
                Add Item
              </Button>
            </div>
          </div>
        )}

        {/* Read-only Mode */}
        {!isEditing && certificate.items && certificate.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-4 py-3 text-left font-semibold">Line #</th>
                  <th className="px-4 py-3 text-left font-semibold">HS Code</th>
                  <th className="px-4 py-3 text-left font-semibold">Item Name</th>
                  <th className="px-4 py-3 text-right font-semibold">Approved Qty</th>
                  <th className="px-4 py-3 text-right font-semibold">Remaining</th>
                  <th className="px-4 py-3 text-left font-semibold">UOM</th>
                  <th className="px-4 py-3 text-center font-semibold">Port Allocation (Approved / Remaining)</th>
                  <th className="px-4 py-3 text-center font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {certificate.items.map((item) => {
                  const balance = getItemBalance(item.id);
                  const remainingQty = balance?.remaining_quantity ?? item.approved_quantity;
                  const quantityStatus = balance?.quantity_status ?? 'normal';

                  return (
                    <tr key={item.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">{item.line_no}</td>
                      <td className="px-4 py-3 font-mono text-blue-600">{item.hs_code}</td>
                      <td className="px-4 py-3 max-w-xs truncate" title={item.item_name}>
                        {item.item_name}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {formatNumber(item.approved_quantity)}
                      </td>
                      <td
                        className={cn(
                          'px-4 py-3 text-right font-semibold',
                          getQuantityStatusClass(quantityStatus)
                        )}
                      >
                        {formatNumber(remainingQty)}
                      </td>
                      <td className="px-4 py-3">{item.uom}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1 text-xs">
                          {(item.port_klang_qty > 0 || (balance?.remaining_port_klang ?? 0) > 0) && (
                            <div className="flex justify-between items-center">
                              <span className="text-gray-500">Port Klang:</span>
                              <span>
                                <span className="text-gray-700">{formatNumber(item.port_klang_qty)}</span>
                                <span className="text-gray-400 mx-1">/</span>
                                <span className={cn(
                                  'font-medium',
                                  (balance?.remaining_port_klang ?? item.port_klang_qty) > 0 ? 'text-green-600' : 'text-red-600'
                                )}>
                                  {formatNumber(balance?.remaining_port_klang ?? item.port_klang_qty)}
                                </span>
                              </span>
                            </div>
                          )}
                          {(item.klia_qty > 0 || (balance?.remaining_klia ?? 0) > 0) && (
                            <div className="flex justify-between items-center">
                              <span className="text-gray-500">KLIA:</span>
                              <span>
                                <span className="text-gray-700">{formatNumber(item.klia_qty)}</span>
                                <span className="text-gray-400 mx-1">/</span>
                                <span className={cn(
                                  'font-medium',
                                  (balance?.remaining_klia ?? item.klia_qty) > 0 ? 'text-green-600' : 'text-red-600'
                                )}>
                                  {formatNumber(balance?.remaining_klia ?? item.klia_qty)}
                                </span>
                              </span>
                            </div>
                          )}
                          {(item.bukit_kayu_hitam_qty > 0 || (balance?.remaining_bukit_kayu_hitam ?? 0) > 0) && (
                            <div className="flex justify-between items-center">
                              <span className="text-gray-500">BKH:</span>
                              <span>
                                <span className="text-gray-700">{formatNumber(item.bukit_kayu_hitam_qty)}</span>
                                <span className="text-gray-400 mx-1">/</span>
                                <span className={cn(
                                  'font-medium',
                                  (balance?.remaining_bukit_kayu_hitam ?? item.bukit_kayu_hitam_qty) > 0 ? 'text-green-600' : 'text-red-600'
                                )}>
                                  {formatNumber(balance?.remaining_bukit_kayu_hitam ?? item.bukit_kayu_hitam_qty)}
                                </span>
                              </span>
                            </div>
                          )}
                          {item.port_klang_qty === 0 && item.klia_qty === 0 && item.bukit_kayu_hitam_qty === 0 && (
                            <span className="text-gray-400 italic">No port split</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            navigate(
                              `/database/certificates/${certificate.id}/items/${item.id}/imports`
                            )
                          }
                          title="View Import Records"
                        >
                          <BarChart3 className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty State */}
        {((isEditing && (!editedCertificate?.items || editedCertificate.items.length === 0)) ||
          (!isEditing && (!certificate.items || certificate.items.length === 0))) && (
          <div className="text-center py-8 text-gray-500">
            <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No items in this certificate</p>
            {isEditing && (
              <Button variant="secondary" onClick={handleAddItem} className="mt-4">
                <Plus className="w-4 h-4 mr-2" />
                Add First Item
              </Button>
            )}
          </div>
        )}
      </Card>

      {/* Delete Item Confirmation */}
      <ConfirmModal
        isOpen={deleteItemIndex !== null}
        onClose={() => setDeleteItemIndex(null)}
        onConfirm={() => deleteItemIndex !== null && handleRemoveItem(deleteItemIndex)}
        title="Delete Item"
        message="Are you sure you want to remove this item? This change will take effect when you save the certificate."
        confirmText="Remove"
        variant="danger"
      />
    </div>
  );
}
