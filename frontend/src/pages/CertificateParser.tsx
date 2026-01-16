import { useState, useMemo } from 'react';
import toast from 'react-hot-toast';
import {
  FileSearch,
  Upload,
  Eye,
  Save,
  FileText,
  Package,
  Plus,
  Trash2,
  TableIcon,
  LayoutList,
  AlertTriangle,
  AlertCircle,
  Info,
} from 'lucide-react';
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  FileUpload,
  Modal,
  Alert,
  Input,
  Badge,
} from '@/components/ui';
import { certificateService } from '@/services';
import { ParsedCertificate, ParsedCertificateItem, SaveCertificateRequest } from '@/types';
import { formatNumber, formatDate } from '@/utils';

// Validation types
interface ValidationWarning {
  type: 'error' | 'warning' | 'info';
  field?: string;
  itemIndex?: number;
  message: string;
}

export function CertificateParser() {
  // State
  const [file, setFile] = useState<File | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [_parsedData, setParsedData] = useState<ParsedCertificate | null>(null);
  const [editedData, setEditedData] = useState<ParsedCertificate | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');

  // Validation logic
  const validationWarnings = useMemo((): ValidationWarning[] => {
    if (!editedData) return [];
    
    const warnings: ValidationWarning[] = [];
    
    // OCR warnings from backend
    if (editedData.warnings && editedData.warnings.length > 0) {
      editedData.warnings.forEach((w) => {
        warnings.push({ type: 'warning', message: `OCR: ${w}` });
      });
    }
    
    // Header field validation
    if (!editedData.mida_no || editedData.mida_no.trim() === '') {
      warnings.push({ type: 'error', field: 'mida_no', message: 'Certificate Number is required' });
    }
    if (!editedData.company_name || editedData.company_name.trim() === '') {
      warnings.push({ type: 'error', field: 'company_name', message: 'Company Name is required' });
    }
    if (!editedData.model_number || editedData.model_number.trim() === '') {
      warnings.push({ type: 'warning', field: 'model_number', message: 'Model Number is missing (usually required)' });
    }
    if (!editedData.exemption_start) {
      warnings.push({ type: 'warning', field: 'exemption_start', message: 'Exemption Start Date is missing' });
    }
    if (!editedData.exemption_end) {
      warnings.push({ type: 'warning', field: 'exemption_end', message: 'Exemption End Date is missing' });
    }
    
    // Item validation
    if (editedData.items.length === 0) {
      warnings.push({ type: 'error', message: 'At least one item is required' });
    }
    
    editedData.items.forEach((item, index) => {
      const lineLabel = `Item #${item.line_no || index + 1}`;
      
      // Required field checks
      if (!item.hs_code || item.hs_code.trim() === '') {
        warnings.push({ type: 'error', itemIndex: index, field: 'hs_code', message: `${lineLabel}: HS Code is required` });
      }
      if (!item.item_name || item.item_name.trim() === '') {
        warnings.push({ type: 'error', itemIndex: index, field: 'item_name', message: `${lineLabel}: Item Name is required` });
      }
      if (!item.uom || item.uom.trim() === '') {
        warnings.push({ type: 'error', itemIndex: index, field: 'uom', message: `${lineLabel}: UOM is required` });
      }
      if (!item.approved_quantity || item.approved_quantity <= 0) {
        warnings.push({ type: 'error', itemIndex: index, field: 'approved_quantity', message: `${lineLabel}: Approved Quantity must be greater than 0` });
      }
      
      // Quantity discrepancy check
      const stationSplit = item.station_split || {};
      const portKlang = stationSplit.PORT_KLANG || 0;
      const klia = stationSplit.KLIA || 0;
      const bukitKayuHitam = stationSplit.BUKIT_KAYU_HITAM || 0;
      const stationSum = portKlang + klia + bukitKayuHitam;
      
      // Only check if at least one station has a value
      const hasStationValues = portKlang > 0 || klia > 0 || bukitKayuHitam > 0;
      if (hasStationValues) {
        const approvedQty = item.approved_quantity || 0;
        const difference = Math.abs(approvedQty - stationSum);
        if (difference > 0.01) {
          warnings.push({
            type: 'warning',
            itemIndex: index,
            message: `${lineLabel}: Quantity mismatch - Approved (${formatNumber(approvedQty)}) ≠ Station Sum (${formatNumber(stationSum)}). Difference: ${formatNumber(approvedQty - stationSum)}`,
          });
        }
      } else if (item.approved_quantity > 0) {
        // No station split defined but has approved quantity
        warnings.push({
          type: 'info',
          itemIndex: index,
          message: `${lineLabel}: No port allocation specified. Total quantity (${formatNumber(item.approved_quantity)}) not split across stations.`,
        });
      }
    });
    
    // Check for duplicate line numbers
    const lineNumbers = editedData.items.map((i) => i.line_no);
    const duplicates = lineNumbers.filter((v, i, a) => a.indexOf(v) !== i);
    if (duplicates.length > 0) {
      warnings.push({
        type: 'error',
        message: `Duplicate line numbers found: ${[...new Set(duplicates)].join(', ')}`,
      });
    }
    
    return warnings;
  }, [editedData]);

  // Separate warnings by type
  const errorCount = validationWarnings.filter((w) => w.type === 'error').length;
  const warningCount = validationWarnings.filter((w) => w.type === 'warning').length;
  const infoCount = validationWarnings.filter((w) => w.type === 'info').length;
  const hasBlockingErrors = errorCount > 0;

  // Check if a specific field has an error
  const getFieldError = (field: string, itemIndex?: number): boolean => {
    return validationWarnings.some(
      (w) => w.type === 'error' && w.field === field && w.itemIndex === itemIndex
    );
  };

  // Handle file parse
  const handleParse = async () => {
    if (!file) {
      toast.error('Please select a PDF file first');
      return;
    }

    setIsParsing(true);
    try {
      const result = await certificateService.parsePdf(file);
      setParsedData(result);
      setEditedData(result);
      toast.success('Certificate parsed successfully!');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to parse certificate';
      toast.error(message);
    } finally {
      setIsParsing(false);
    }
  };

  // Handle field changes
  const handleFieldChange = (field: keyof ParsedCertificate, value: string) => {
    setEditedData((prev) => (prev ? { ...prev, [field]: value } : null));
  };

  // Handle item changes
  const handleItemChange = (index: number, field: keyof ParsedCertificateItem, value: string | number) => {
    setEditedData((prev) => {
      if (!prev) return null;
      const items = [...prev.items];
      items[index] = { ...items[index], [field]: value };
      return { ...prev, items };
    });
  };

  // Handle station split (port allocation) changes
  const handleStationSplitChange = (index: number, port: 'PORT_KLANG' | 'KLIA' | 'BUKIT_KAYU_HITAM', value: number) => {
    setEditedData((prev) => {
      if (!prev) return null;
      const items = [...prev.items];
      const currentSplit = items[index].station_split || {};
      items[index] = {
        ...items[index],
        station_split: { ...currentSplit, [port]: value },
      };
      return { ...prev, items };
    });
  };

  // Add new item
  const handleAddItem = () => {
    setEditedData((prev) => {
      if (!prev) return null;
      const newItem: ParsedCertificateItem = {
        line_no: prev.items.length + 1,
        hs_code: '',
        item_name: '',
        approved_quantity: 0,
        uom: '',
      };
      return {
        ...prev,
        items: [...prev.items, newItem],
      };
    });
  };

  // Remove item
  const handleRemoveItem = (index: number) => {
    setEditedData((prev) => {
      if (!prev) return null;
      const items = prev.items.filter((_, i) => i !== index);
      // Re-number items
      return {
        ...prev,
        items: items.map((item, i) => ({ ...item, line_no: i + 1 })),
      };
    });
  };

  // Save certificate
  const handleSave = async () => {
    if (!editedData) return;

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

    setIsSaving(true);
    try {
      const request: SaveCertificateRequest = {
        header: {
          certificate_number: editedData.mida_no,
          company_name: editedData.company_name,
          model_number: editedData.model_number,
          exemption_start_date: editedData.exemption_start,
          exemption_end_date: editedData.exemption_end,
          source_filename: file?.name,
        },
        items: editedData.items.map((item) => ({
          line_no: item.line_no,
          hs_code: item.hs_code,
          item_name: item.item_name,
          uom: item.uom,
          approved_quantity: item.approved_quantity,
          port_klang_qty: item.station_split?.PORT_KLANG,
          klia_qty: item.station_split?.KLIA,
          bukit_kayu_hitam_qty: item.station_split?.BUKIT_KAYU_HITAM,
        })),
        raw_ocr_json: editedData,
      };

      await certificateService.create(request);
      toast.success('Certificate saved successfully!');
      
      // Reset form
      setFile(null);
      setParsedData(null);
      setEditedData(null);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to save certificate';
      toast.error(message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      <Card>
        <CardHeader>
          <CardTitle icon={<FileSearch className="w-5 h-5 text-green-600" />}>
            Certificate Parser
          </CardTitle>
          <CardDescription>
            Upload a MIDA certificate PDF to extract data automatically
          </CardDescription>
        </CardHeader>

        <div className="grid md:grid-cols-2 gap-6">
          <FileUpload
            accept=".pdf"
            label="Upload Certificate PDF"
            helperText="PDF format only (max 20MB)"
            value={file}
            onChange={setFile}
          />

          <div className="flex flex-col justify-end gap-4">
            <Button
              onClick={handleParse}
              isLoading={isParsing}
              disabled={!file}
              size="lg"
              variant="success"
              leftIcon={<Upload className="w-4 h-4" />}
            >
              Parse Certificate
            </Button>
          </div>
        </div>
      </Card>

      {/* Parsed Data Form */}
      {editedData && (
        <Card>
          <CardHeader
            action={
              <div className="flex items-center gap-2">
                {/* Validation status indicator */}
                {hasBlockingErrors && (
                  <span className="text-red-600 text-sm flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    Fix errors to save
                  </span>
                )}
                <Button
                  variant="secondary"
                  onClick={() => setShowPreview(true)}
                  leftIcon={<Eye className="w-4 h-4" />}
                >
                  Preview
                </Button>
                <Button
                  variant={hasBlockingErrors ? 'secondary' : 'success'}
                  onClick={handleSave}
                  isLoading={isSaving}
                  disabled={hasBlockingErrors}
                  leftIcon={<Save className="w-4 h-4" />}
                  title={hasBlockingErrors ? 'Fix all errors before saving' : 'Save certificate to database'}
                >
                  Save Certificate
                </Button>
              </div>
            }
          >
            <CardTitle icon={<FileText className="w-5 h-5 text-blue-600" />}>
              Certificate Details
              {validationWarnings.length > 0 && (
                <Badge 
                  variant={hasBlockingErrors ? 'danger' : 'warning'} 
                  className="ml-2"
                >
                  {validationWarnings.length} issue{validationWarnings.length !== 1 ? 's' : ''}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>

          {/* Certificate Info Grid */}
          <div className="grid md:grid-cols-3 gap-4 mb-6">
            <Input
              label="Certificate No (MIDA No)"
              value={editedData.mida_no}
              onChange={(e) => handleFieldChange('mida_no', e.target.value)}
              required
              error={getFieldError('mida_no') ? 'Required' : undefined}
              className={getFieldError('mida_no') ? 'border-red-500' : ''}
            />
            <Input
              label="Company Name"
              value={editedData.company_name}
              onChange={(e) => handleFieldChange('company_name', e.target.value)}
              required
              error={getFieldError('company_name') ? 'Required' : undefined}
              className={getFieldError('company_name') ? 'border-red-500' : ''}
            />
            <Input
              label="Model Number"
              value={editedData.model_number || ''}
              onChange={(e) => handleFieldChange('model_number', e.target.value)}
              className={validationWarnings.some(w => w.field === 'model_number') ? 'border-yellow-500' : ''}
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4 mb-6">
            <Input
              label="Exemption Start"
              type="date"
              value={editedData.exemption_start || ''}
              onChange={(e) => handleFieldChange('exemption_start', e.target.value)}
              className={validationWarnings.some(w => w.field === 'exemption_start') ? 'border-yellow-500' : ''}
            />
            <Input
              label="Exemption End"
              type="date"
              value={editedData.exemption_end || ''}
              onChange={(e) => handleFieldChange('exemption_end', e.target.value)}
              className={validationWarnings.some(w => w.field === 'exemption_end') ? 'border-yellow-500' : ''}
            />
          </div>

          {/* Validation Warnings Section */}
          {validationWarnings.length > 0 && (
            <div className="mb-6 space-y-3">
              {/* Summary badges */}
              <div className="flex items-center gap-3 flex-wrap">
                {errorCount > 0 && (
                  <div className="flex items-center gap-1.5 bg-red-100 text-red-700 px-3 py-1.5 rounded-full text-sm font-medium">
                    <AlertCircle className="w-4 h-4" />
                    {errorCount} Error{errorCount !== 1 ? 's' : ''} (must fix)
                  </div>
                )}
                {warningCount > 0 && (
                  <div className="flex items-center gap-1.5 bg-yellow-100 text-yellow-700 px-3 py-1.5 rounded-full text-sm font-medium">
                    <AlertTriangle className="w-4 h-4" />
                    {warningCount} Warning{warningCount !== 1 ? 's' : ''}
                  </div>
                )}
                {infoCount > 0 && (
                  <div className="flex items-center gap-1.5 bg-blue-100 text-blue-700 px-3 py-1.5 rounded-full text-sm font-medium">
                    <Info className="w-4 h-4" />
                    {infoCount} Info
                  </div>
                )}
              </div>

              {/* Detailed warnings list */}
              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 max-h-64 overflow-y-auto">
                <div className="space-y-2">
                  {validationWarnings.map((warning, idx) => (
                    <div
                      key={idx}
                      className={`flex items-start gap-2 text-sm p-2 rounded ${
                        warning.type === 'error'
                          ? 'bg-red-50 text-red-700 border-l-4 border-red-500'
                          : warning.type === 'warning'
                          ? 'bg-yellow-50 text-yellow-700 border-l-4 border-yellow-500'
                          : 'bg-blue-50 text-blue-700 border-l-4 border-blue-500'
                      }`}
                    >
                      {warning.type === 'error' ? (
                        <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                      ) : warning.type === 'warning' ? (
                        <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                      ) : (
                        <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
                      )}
                      <span>{warning.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Items Section */}
          <div className="border-t border-gray-200 pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Package className="w-5 h-5 text-purple-600" />
                Certificate Items
                <Badge variant="purple">{editedData.items.length}</Badge>
              </h3>
              <div className="flex items-center gap-2">
                {/* View Mode Toggle */}
                <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden">
                  <button
                    onClick={() => setViewMode('cards')}
                    className={`p-2 ${viewMode === 'cards' ? 'bg-purple-100 text-purple-700' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
                    title="Card View"
                  >
                    <LayoutList className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setViewMode('table')}
                    className={`p-2 ${viewMode === 'table' ? 'bg-purple-100 text-purple-700' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
                    title="Table View"
                  >
                    <TableIcon className="w-4 h-4" />
                  </button>
                </div>
                <Button variant="secondary" onClick={handleAddItem} leftIcon={<Plus className="w-4 h-4" />}>
                  Add Item
                </Button>
              </div>
            </div>

            {/* Card View */}
            {viewMode === 'cards' && (
              <div className="space-y-4">
                {editedData.items.map((item, index) => (
                  <div
                    key={index}
                    className="bg-gray-50 rounded-lg p-4 border border-gray-200"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <span className="bg-purple-100 text-purple-700 px-2 py-1 rounded font-semibold text-sm">
                        Item #{item.line_no}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveItem(index)}
                        className="text-red-600 hover:bg-red-50"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>

                    <div className="grid md:grid-cols-4 gap-4 mb-4">
                      <Input
                        label="HS Code"
                        value={item.hs_code}
                        onChange={(e) => handleItemChange(index, 'hs_code', e.target.value)}
                        required
                      />
                      <Input
                        label="Item Name"
                        value={item.item_name}
                        onChange={(e) => handleItemChange(index, 'item_name', e.target.value)}
                        required
                      />
                      <Input
                        label="Approved Quantity"
                        type="number"
                        value={item.approved_quantity}
                        onChange={(e) => handleItemChange(index, 'approved_quantity', parseFloat(e.target.value) || 0)}
                        required
                      />
                      <Input
                        label="UOM"
                        value={item.uom}
                        onChange={(e) => handleItemChange(index, 'uom', e.target.value)}
                        required
                      />
                    </div>
                    {/* Port Allocation */}
                    <div className="bg-white rounded border border-gray-200 p-3">
                      <p className="text-xs font-semibold text-gray-600 mb-2">Port Allocation</p>
                      <div className="grid md:grid-cols-3 gap-4">
                        <Input
                          label="Port Klang"
                          type="number"
                          value={item.station_split?.PORT_KLANG || 0}
                          onChange={(e) => handleStationSplitChange(index, 'PORT_KLANG', parseFloat(e.target.value) || 0)}
                        />
                        <Input
                          label="KLIA"
                          type="number"
                          value={item.station_split?.KLIA || 0}
                          onChange={(e) => handleStationSplitChange(index, 'KLIA', parseFloat(e.target.value) || 0)}
                        />
                        <Input
                          label="Bukit Kayu Hitam"
                          type="number"
                          value={item.station_split?.BUKIT_KAYU_HITAM || 0}
                          onChange={(e) => handleStationSplitChange(index, 'BUKIT_KAYU_HITAM', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                    </div>
                  </div>
                ))}

                {editedData.items.length === 0 && (
                  <Alert variant="warning">
                    <p>No items added yet. Click "Add Item" to add certificate items.</p>
                  </Alert>
                )}
              </div>
            )}

            {/* Table View */}
            {viewMode === 'table' && (
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="px-3 py-3 text-left font-semibold w-16">#</th>
                      <th className="px-3 py-3 text-left font-semibold">HS Code</th>
                      <th className="px-3 py-3 text-left font-semibold">Item Name</th>
                      <th className="px-3 py-3 text-right font-semibold w-28">Quantity</th>
                      <th className="px-3 py-3 text-left font-semibold w-20">UOM</th>
                      <th className="px-3 py-3 text-right font-semibold w-24">Port Klang</th>
                      <th className="px-3 py-3 text-right font-semibold w-24">KLIA</th>
                      <th className="px-3 py-3 text-right font-semibold w-24">BKH</th>
                      <th className="px-3 py-3 text-center font-semibold w-16">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {editedData.items.map((item, index) => (
                      <tr key={index} className="hover:bg-gray-50">
                        <td className="px-3 py-2">
                          <span className="bg-purple-100 text-purple-700 px-2 py-1 rounded text-xs font-semibold">
                            {item.line_no}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={item.hs_code}
                            onChange={(e) => handleItemChange(index, 'hs_code', e.target.value)}
                            className="w-full px-2 py-1.5 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={item.item_name}
                            onChange={(e) => handleItemChange(index, 'item_name', e.target.value)}
                            className="w-full px-2 py-1.5 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            value={item.approved_quantity}
                            onChange={(e) => handleItemChange(index, 'approved_quantity', parseFloat(e.target.value) || 0)}
                            className="w-full px-2 py-1.5 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-right"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={item.uom}
                            onChange={(e) => handleItemChange(index, 'uom', e.target.value)}
                            className="w-full px-2 py-1.5 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            value={item.station_split?.PORT_KLANG || 0}
                            onChange={(e) => handleStationSplitChange(index, 'PORT_KLANG', parseFloat(e.target.value) || 0)}
                            className="w-full px-2 py-1.5 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-right"
                            title="Port Klang Quantity"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            value={item.station_split?.KLIA || 0}
                            onChange={(e) => handleStationSplitChange(index, 'KLIA', parseFloat(e.target.value) || 0)}
                            className="w-full px-2 py-1.5 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-right"
                            title="KLIA Quantity"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            value={item.station_split?.BUKIT_KAYU_HITAM || 0}
                            onChange={(e) => handleStationSplitChange(index, 'BUKIT_KAYU_HITAM', parseFloat(e.target.value) || 0)}
                            className="w-full px-2 py-1.5 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm text-right"
                            title="Bukit Kayu Hitam Quantity"
                          />
                        </td>
                        <td className="px-3 py-2 text-center">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRemoveItem(index)}
                            className="text-red-600 hover:bg-red-50"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                    {editedData.items.length === 0 && (
                      <tr>
                        <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                          No items added yet. Click "Add Item" to add certificate items.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Preview Modal */}
      <Modal
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        title="Certificate Preview"
        size="xl"
      >
        {editedData && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Certificate No:</span>
                <p className="font-semibold">{editedData.mida_no}</p>
              </div>
              <div>
                <span className="text-gray-500">Company:</span>
                <p className="font-semibold">{editedData.company_name}</p>
              </div>
              <div>
                <span className="text-gray-500">Validity:</span>
                <p className="font-semibold">
                  {formatDate(editedData.exemption_start)} - {formatDate(editedData.exemption_end)}
                </p>
              </div>
              <div>
                <span className="text-gray-500">Model Number:</span>
                <p className="font-semibold">{editedData.model_number || '-'}</p>
              </div>
            </div>

            <div className="border-t pt-4">
              <h4 className="font-semibold mb-3">Items ({editedData.items.length})</h4>
              <div className="overflow-x-auto max-h-96 overflow-y-auto border border-gray-200 rounded">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-gray-100">
                    <tr>
                      <th className="px-3 py-2 text-left">#</th>
                      <th className="px-3 py-2 text-left">HS Code</th>
                      <th className="px-3 py-2 text-left">Item Name</th>
                      <th className="px-3 py-2 text-right">Quantity</th>
                      <th className="px-3 py-2 text-left">UOM</th>
                      <th className="px-3 py-2 text-right">Port Klang</th>
                      <th className="px-3 py-2 text-right">KLIA</th>
                      <th className="px-3 py-2 text-right">BKH</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {editedData.items.map((item, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-3 py-2">{item.line_no}</td>
                        <td className="px-3 py-2 font-mono">{item.hs_code}</td>
                        <td className="px-3 py-2">{item.item_name}</td>
                        <td className="px-3 py-2 text-right">{formatNumber(item.approved_quantity)}</td>
                        <td className="px-3 py-2">{item.uom}</td>
                        <td className="px-3 py-2 text-right">{formatNumber(item.station_split?.PORT_KLANG || 0)}</td>
                        <td className="px-3 py-2 text-right">{formatNumber(item.station_split?.KLIA || 0)}</td>
                        <td className="px-3 py-2 text-right">{formatNumber(item.station_split?.BUKIT_KAYU_HITAM || 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
