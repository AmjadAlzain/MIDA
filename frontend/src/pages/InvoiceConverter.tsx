import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  FileText,
  Upload,
  Download,
  Package,
  DollarSign,
  CheckCircle,
  ArrowRightLeft,
  RotateCcw,
} from 'lucide-react';
import { Button, Card, CardHeader, CardTitle, FileUpload, Badge, Select, Input, Modal } from '@/components/ui';
import { classificationService, companyService, certificateService, importService } from '@/services';
import { ClassificationResponse, ClassificationItem, Company, K1ExportItem, Certificate, COUNTRIES, ImportPreviewResponse } from '@/types';
import { cn, formatNumber, getTodayISO } from '@/utils';

// Tab types for the Invoice Converter
type ConverterTab = 'formd' | 'mida' | 'duties';

export function InvoiceConverter() {
  // State
  const [file, setFile] = useState<File | null>(null);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>('');
  const [selectedCountry, setSelectedCountry] = useState<string>('JP');
  const [selectedPort, setSelectedPort] = useState<string>('port_klang');
  const [importDate, setImportDate] = useState<string>(getTodayISO());
  const [isProcessing, setIsProcessing] = useState(false);
  const [classificationResult, setClassificationResult] = useState<ClassificationResponse | null>(null);
  const [originalResult, setOriginalResult] = useState<ClassificationResponse | null>(null);
  const [activeTab, setActiveTab] = useState<ConverterTab>('formd');
  const [selectedItems, setSelectedItems] = useState<Record<string, Set<number>>>({
    formd: new Set(),
    mida: new Set(),
    duties: new Set(),
  });
  const [isExporting, setIsExporting] = useState(false);
  const [selectedCertificateIds, setSelectedCertificateIds] = useState<string[]>([]);
  
  // MIDA Balance Update State
  const [declarationRefNo, setDeclarationRefNo] = useState('');
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewData, setPreviewData] = useState<ImportPreviewResponse | null>(null);
  const [isUpdatingBalance, setIsUpdatingBalance] = useState(false);

  // Fetch companies
  const { data: companies = [] } = useQuery<Company[]>({
    queryKey: ['companies'],
    queryFn: companyService.getAll,
  });

  // Get selected company name for certificate fetch
  const selectedCompany = companies.find((c) => c.id === selectedCompanyId);

  // Fetch certificates for selected company
  const { data: companyCertificates = [], isLoading: isLoadingCertificates } = useQuery<Certificate[]>({
    queryKey: ['certificates', 'company', selectedCompany?.name],
    queryFn: async () => {
      if (!selectedCompany?.name) return [];
      const result = await certificateService.getByCompany(selectedCompany.name, 'active');
      return result.certificates;
    },
    enabled: !!selectedCompany?.name,
  });

  // Country options - all countries with code in brackets
  const countryOptions = COUNTRIES.map((c) => ({
    value: c.code,
    label: `${c.name} (${c.code})`,
  }));

  // Port options
  const portOptions = [
    { value: 'port_klang', label: 'Port Klang' },
    { value: 'klia', label: 'KLIA' },
    { value: 'bukit_kayu_hitam', label: 'Bukit Kayu Hitam' },
  ];

  // Check for manual changes
  const hasChanges = useMemo(() => {
    if (!classificationResult) return false;
    const allItems = [
      ...classificationResult.form_d_items,
      ...classificationResult.mida_items,
      ...classificationResult.duties_payable_items
    ];
    return allItems.some(i => i.manually_moved || i.sst_manually_changed);
  }, [classificationResult]);

  // Computed data
  const tabData = useMemo((): Record<ConverterTab, ClassificationItem[]> => {
    if (!classificationResult) return { formd: [], mida: [], duties: [] };
    
    return {
      formd: classificationResult.form_d_items || [],
      mida: classificationResult.mida_items || [],
      duties: classificationResult.duties_payable_items || [],
    };
  }, [classificationResult]);

  const currentItems = tabData[activeTab];
  const currentSelection = selectedItems[activeTab];

  // Handle file upload and classification
  const handleClassify = async () => {
    if (!file) {
      toast.error('Please select a file first');
      return;
    }
    if (!selectedCompanyId) {
      toast.error('Please select a company');
      return;
    }
    if (!importDate) {
      toast.error('Please select an import date');
      return;
    }

    setIsProcessing(true);
    try {
      const result = await classificationService.classifyInvoice({
        file,
        companyId: selectedCompanyId,
        country: selectedCountry,
        port: selectedPort,
        importDate: importDate,
        certificateIds: selectedCertificateIds.length > 0 ? selectedCertificateIds : undefined,
      });

      // Assign unique IDs to items if missing (backend response doesn't always include them)
      const assignIds = (items: ClassificationItem[]) => {
        items.forEach((item) => {
          if (!item.id) {
            item.id = `item-${item.line_no}-${Math.random().toString(36).substring(2, 9)}`;
          }
        });
      };
      assignIds(result.form_d_items);
      assignIds(result.mida_items);
      assignIds(result.duties_payable_items);

      setClassificationResult(result);
      setOriginalResult(JSON.parse(JSON.stringify(result)));
      toast.success('Invoice classified successfully!');
      
      // Reset selections
      setSelectedItems({
        formd: new Set(),
        mida: new Set(),
        duties: new Set(),
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to classify invoice';
      toast.error(message);
    } finally {
      setIsProcessing(false);
    }
  };

  // Handle item selection
  const toggleItemSelection = (index: number) => {
    setSelectedItems((prev) => {
      const currentSet = new Set(prev[activeTab]);
      if (currentSet.has(index)) {
        currentSet.delete(index);
      } else {
        currentSet.add(index);
      }
      return { ...prev, [activeTab]: currentSet };
    });
  };

  const toggleSelectAll = () => {
    setSelectedItems((prev) => {
      const allSelected = currentItems.length > 0 && currentItems.every((_, i) => prev[activeTab].has(i));
      if (allSelected) {
        return { ...prev, [activeTab]: new Set<number>() };
      } else {
        return { ...prev, [activeTab]: new Set(currentItems.map((_, i) => i)) };
      }
    });
  };

  // Handle moving items between tables
  const handleMoveItem = (item: ClassificationItem, targetTable: ConverterTab) => {
    if (!classificationResult) return;

    const newResult = JSON.parse(JSON.stringify(classificationResult)) as ClassificationResponse;
    
    // Get source list
    let sourceList: ClassificationItem[];
    if (activeTab === 'formd') sourceList = newResult.form_d_items;
    else if (activeTab === 'mida') sourceList = newResult.mida_items;
    else sourceList = newResult.duties_payable_items;
    
    // Get target list
    let targetList: ClassificationItem[];
    if (targetTable === 'formd') targetList = newResult.form_d_items;
    else if (targetTable === 'mida') targetList = newResult.mida_items;
    else targetList = newResult.duties_payable_items;

    // Find index in the source list
    const itemIndex = sourceList.findIndex((i) => i.id === item.id);
    if (itemIndex === -1) return;
    
    const [movedItem] = sourceList.splice(itemIndex, 1);
    
    // Update properties
    const newTable = targetTable === 'formd' ? 'form_d' : targetTable === 'mida' ? 'mida' : 'duties_payable';
    movedItem.current_table = newTable;
    movedItem.manually_moved = newTable !== movedItem.original_table;

    // Use mida_hs_code if available and moving from MIDA
    if (activeTab === 'mida' && movedItem.mida_hs_code) {
      // Remove all dots from the HSCODE for non-MIDA tables
      movedItem.hs_code = movedItem.mida_hs_code.replace(/\./g, '');
    }
    
    // Update SST rules
    const isHicom = newResult.company.sst_default_behavior === 'all_on';
    if (isHicom) {
      movedItem.sst_exempted = true;
    } else {
      if (targetTable === 'mida') {
        movedItem.sst_exempted = true;
      } else {
        movedItem.sst_exempted = false;
      }
    }
    movedItem.sst_manually_changed = false; // Reset manual flag
    
    // Add to target (top of list)
    targetList.unshift(movedItem);
    
    setClassificationResult(newResult);
    
    // Clear selection
    setSelectedItems({
      formd: new Set(),
      mida: new Set(),
      duties: new Set(),
    });
    
    toast.success(`Moved to ${targetTable === 'formd' ? 'Form-D' : targetTable === 'mida' ? 'MIDA' : 'Duties Payable'}`);
  };

  // Handle SST toggle
  const handleToggleSST = (itemId: string) => {
    if (!classificationResult) return;
    
    setClassificationResult((prev) => {
      if (!prev) return prev;
      const newResult = JSON.parse(JSON.stringify(prev)) as ClassificationResponse;
      const list = activeTab === 'formd' ? newResult.form_d_items : activeTab === 'mida' ? newResult.mida_items : newResult.duties_payable_items;
      
      const targetItem = list.find((i) => i.id === itemId);
      if (targetItem) {
        targetItem.sst_exempted = !targetItem.sst_exempted;
        targetItem.sst_manually_changed = true;
      }
      return newResult;
    });
  };

  // Handle SST toggle for ALL items in current tab
  const handleToggleAllSST = (setExempted: boolean) => {
    if (!classificationResult) return;
    
    setClassificationResult((prev) => {
      if (!prev) return prev;
      const newResult = JSON.parse(JSON.stringify(prev)) as ClassificationResponse;
      const list = activeTab === 'formd' ? newResult.form_d_items : activeTab === 'mida' ? newResult.mida_items : newResult.duties_payable_items;
      
      list.forEach((item) => {
        item.sst_exempted = setExempted;
        item.sst_manually_changed = true;
      });
      return newResult;
    });
    
    toast.success(`All items set to SST ${setExempted ? 'Exempt' : 'Taxable'}`);
  };

  // Handle Update Balance (Step 1: Preview)
  const handleUpdateBalance = async () => {
    if (!declarationRefNo.trim()) {
      toast.error('Please enter Declaration Ref/Reg No.');
      return;
    }

    const midaItems = classificationResult?.mida_items || [];
    if (midaItems.length === 0) {
      toast.error('No MIDA items to update.');
      return;
    }

    // Check if any MIDA items are selected
    const selectedMidaIndices = selectedItems.mida;
    if (selectedMidaIndices.size === 0) {
      toast.error('Please select at least one item to update balance.');
      return;
    }

    // Filter items that have a deduction quantity and certificate item ID AND are selected
    const validItems = midaItems.filter(
      (item, index) => 
        selectedMidaIndices.has(index) && 
        item.mida_item_id && 
        (item.deduction_quantity || item.quantity) > 0
    );

    if (validItems.length === 0) {
      toast.error('No valid selected MIDA items with deduction quantity found.');
      return;
    }

    setIsUpdatingBalance(true);
    try {
      const preview = await importService.previewBulk({
        records: validItems.map(item => ({
          certificate_item_id: item.mida_item_id!,
          import_date: importDate,
          declaration_form_reg_no: declarationRefNo,
          invoice_number: file?.name || 'Unknown Invoice', // Using filename as invoice number for now
          invoice_line: item.line_no,
          quantity_imported: item.deduction_quantity || item.quantity,
          port: selectedPort,
          remarks: `Batch update from invoice classification`,
        }))
      });

      setPreviewData(preview);
      setShowPreviewModal(true);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to preview balance update';
      toast.error(message);
    } finally {
      setIsUpdatingBalance(false);
    }
  };

  // Handle Confirm Update (Step 2: Commit)
  const handleConfirmUpdate = async () => {
    if (!previewData) return;

    setIsUpdatingBalance(true);
    try {
      const midaItems = classificationResult?.mida_items || [];
      const selectedMidaIndices = selectedItems.mida;
      
      const validItems = midaItems.filter(
        (item, index) => 
          selectedMidaIndices.has(index) &&
          item.mida_item_id && 
          (item.deduction_quantity || item.quantity) > 0
      );

      await importService.createBulk({
        records: validItems.map(item => ({
          certificate_item_id: item.mida_item_id!,
          import_date: importDate,
          declaration_form_reg_no: declarationRefNo,
          invoice_number: file?.name || 'Unknown Invoice',
          invoice_line: item.line_no,
          quantity_imported: item.deduction_quantity || item.quantity,
          port: selectedPort,
          remarks: `Batch update from invoice classification`,
        }))
      });

      toast.success('Balances updated successfully!');
      setShowPreviewModal(false);
      setPreviewData(null);
      setDeclarationRefNo(''); // Clear input
      
      // Ideally here we would refresh the certificate balances, 
      // but that requires re-fetching or updating local state
      
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to update balances';
      toast.error(message);
    } finally {
      setIsUpdatingBalance(false);
    }
  };

  // Handle Undo
  const handleUndoChanges = () => {
    if (originalResult) {
      setClassificationResult(JSON.parse(JSON.stringify(originalResult)));
      setSelectedItems({
        formd: new Set(),
        mida: new Set(),
        duties: new Set(),
      });
      toast.success('All changes reset');
    }
  };

  // Handle K1 export
  const handleK1Export = async () => {
    const tabKey = activeTab;
    const selectedIndices = Array.from(selectedItems[tabKey]);
    if (selectedIndices.length === 0) {
      toast.error('Please select items to export');
      return;
    }

    setIsExporting(true);
    try {
      const items = selectedIndices.map((i) => tabData[tabKey][i]);
      const exportType = tabKey === 'formd' ? 'form_d' : tabKey === 'mida' ? 'mida' : 'duties_payable';
      
      const k1Items: K1ExportItem[] = items.map((item) => ({
        hs_code: item.hs_code,
        description: (tabKey === 'mida' && item.mida_item_name && item.mida_line_no)
          ? `${item.mida_item_name} (${item.mida_line_no})` 
          : item.description,
        quantity: item.quantity,
        uom: item.uom,
        amount: item.amount,
        net_weight_kg: item.net_weight_kg,
        sst_exempted: item.sst_exempted,
      }));

      const blob = await classificationService.exportK1({
        items: k1Items,
        export_type: exportType,
        country: selectedCountry,
      });
      
      classificationService.downloadBlob(blob, `K1_Export_${exportType}.xls`);
      toast.success('K1 export downloaded successfully!');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to export K1';
      toast.error(message);
    } finally {
      setIsExporting(false);
    }
  };

  // Get quantity status class
  const getQtyStatusClass = (item: ClassificationItem): string => {
    if (!item.remaining_qty) return '';
    if (item.remaining_qty <= 0) return 'text-red-600 font-bold';
    if (item.remaining_qty < item.quantity) return 'text-yellow-600';
    return 'text-green-600';
  };

  // Tab configuration
  const tabs = [
    { id: 'formd' as const, label: 'Form-D', count: tabData.formd.length, color: 'green', icon: CheckCircle },
    { id: 'mida' as const, label: 'MIDA', count: tabData.mida.length, color: 'blue', icon: Package },
    { id: 'duties' as const, label: 'Duties Payable', count: tabData.duties.length, color: 'orange', icon: DollarSign },
  ];

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      <Card>
        <CardHeader>
          <CardTitle icon={<FileText className="w-5 h-5 text-blue-600" />}>
            Invoice Classification
          </CardTitle>
        </CardHeader>
        
        <div className="grid md:grid-cols-2 gap-6 mb-6">
          <FileUpload
            accept=".csv,.xlsx,.xls"
            label="Upload Invoice File"
            helperText="CSV or Excel format"
            value={file}
            onChange={setFile}
          />
          
          <div className="space-y-4">
            <Select
              label="Company"
              value={selectedCompanyId}
              onChange={(e) => {
                setSelectedCompanyId(e.target.value);
                setSelectedCertificateIds([]); // Reset certificate selection when company changes
              }}
              options={companies.map((c) => ({ value: c.id, label: c.name }))}
              placeholder="Select Company"
              required
            />
            
            {/* MIDA Certificate Selection */}
            {selectedCompanyId && (
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700">
                  MIDA Certificates <span className="text-gray-400">(for MIDA matching)</span>
                </label>
                {isLoadingCertificates ? (
                  <div className="border border-gray-300 rounded-lg p-4 bg-gray-50 text-center text-sm text-gray-500">
                    Loading certificates...
                  </div>
                ) : companyCertificates.length === 0 ? (
                  <div className="border border-gray-300 rounded-lg p-4 bg-gray-50 text-center text-sm text-gray-500">
                    No active MIDA certificates found for this company
                  </div>
                ) : (
                  <>
                    <div className="max-h-32 overflow-y-auto border border-gray-300 rounded-lg p-2 bg-white space-y-1">
                      {companyCertificates.map((cert) => (
                        <label
                          key={cert.id}
                          className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={selectedCertificateIds.includes(cert.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedCertificateIds((prev) => [...prev, cert.id]);
                              } else {
                                setSelectedCertificateIds((prev) => prev.filter((id) => id !== cert.id));
                              }
                            }}
                            className="rounded border-gray-300 text-blue-600"
                          />
                          <span className="text-sm font-medium text-purple-600">{cert.certificate_number}</span>
                          <span className="text-xs text-gray-500">
                            ({cert.exemption_start_date} - {cert.exemption_end_date})
                          </span>
                        </label>
                      ))}
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>{selectedCertificateIds.length} of {companyCertificates.length} selected</span>
                      {companyCertificates.length > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            if (selectedCertificateIds.length === companyCertificates.length) {
                              setSelectedCertificateIds([]);
                            } else {
                              setSelectedCertificateIds(companyCertificates.map((c) => c.id));
                            }
                          }}
                          className="text-blue-600 hover:text-blue-800 underline"
                        >
                          {selectedCertificateIds.length === companyCertificates.length ? 'Deselect All' : 'Select All'}
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
            
            <div className="grid grid-cols-3 gap-4">
              <Input
                label="Import Date"
                type="date"
                value={importDate}
                onChange={(e) => setImportDate(e.target.value)}
                required
              />
              <Select
                label="Country"
                value={selectedCountry}
                onChange={(e) => setSelectedCountry(e.target.value)}
                options={countryOptions}
              />
              <Select
                label="Port"
                value={selectedPort}
                onChange={(e) => setSelectedPort(e.target.value)}
                options={portOptions}
              />
            </div>
          </div>
        </div>

        <Button
          onClick={handleClassify}
          isLoading={isProcessing}
          disabled={!file || !selectedCompanyId}
          size="lg"
          leftIcon={<Upload className="w-4 h-4" />}
        >
          Classify Invoice
        </Button>
        
        {classificationResult && (
          <div className="mt-4 flex items-center gap-4 text-sm text-gray-600">
            <span className="flex items-center gap-1">
              <Package className="w-4 h-4" />
              Total Items: {classificationResult.total_items}
            </span>
          </div>
        )}
      </Card>

      {/* Results Section */}
      {classificationResult && (
        <Card padding="none">
          {/* Tabs */}
          <div className="border-b border-gray-200 px-6 pt-4">
            <div className="flex gap-1">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      'flex items-center gap-2 px-4 py-3 font-semibold text-sm rounded-t-lg transition-colors -mb-px',
                      activeTab === tab.id
                        ? 'bg-white text-gray-900 border border-gray-200 border-b-white'
                        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                    )}
                  >
                    <Icon className={cn('w-4 h-4', 
                      tab.color === 'green' && 'text-green-500',
                      tab.color === 'blue' && 'text-blue-500',
                      tab.color === 'orange' && 'text-orange-500'
                    )} />
                    {tab.label}
                    <Badge variant={tab.color === 'green' ? 'success' : tab.color === 'blue' ? 'info' : 'orange'}>
                      {tab.count}
                    </Badge>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {/* Action Bar */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={currentItems.length > 0 && currentItems.every((_, i) => currentSelection.has(i))}
                    onChange={toggleSelectAll}
                    className="rounded border-gray-300"
                  />
                  Select All
                </label>
                <span className="text-sm text-gray-500">
                  {currentSelection.size} of {currentItems.length} selected
                </span>

                {/* SST Toggle All Buttons */}
                <div className="flex items-center gap-2 ml-4 pl-4 border-l border-gray-300">
                  <span className="text-sm text-gray-500">SST:</span>
                  <button
                    onClick={() => handleToggleAllSST(true)}
                    className="px-2 py-1 text-xs font-medium bg-green-100 text-green-700 rounded hover:bg-green-200 transition-colors"
                  >
                    All Exempt
                  </button>
                  <button
                    onClick={() => handleToggleAllSST(false)}
                    className="px-2 py-1 text-xs font-medium bg-yellow-100 text-yellow-700 rounded hover:bg-yellow-200 transition-colors"
                  >
                    All Taxable
                  </button>
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                {activeTab === 'mida' && (
                  <div className="flex items-center gap-2 mr-2 border-r border-gray-300 pr-4">
                    <Input
                      placeholder="Declaration Ref/Reg No."
                      value={declarationRefNo}
                      onChange={(e) => setDeclarationRefNo(e.target.value)}
                      className="w-48 py-1 h-9"
                    />
                    <Button
                      onClick={handleUpdateBalance}
                      isLoading={isUpdatingBalance}
                      disabled={!classificationResult.mida_items.length}
                      size="sm"
                      variant="primary"
                    >
                      Update Balance
                    </Button>
                  </div>
                )}
                
                {hasChanges && (
                  <Button
                    onClick={handleUndoChanges}
                    variant="outline"
                    leftIcon={<RotateCcw className="w-4 h-4" />}
                    size="sm"
                  >
                    Reset Changes
                  </Button>
                )}

                {currentSelection.size > 0 && (
                  <Button
                    onClick={handleK1Export}
                    isLoading={isExporting}
                    leftIcon={<Download className="w-4 h-4" />}
                    variant="success"
                  >
                    Export K1 ({currentSelection.size})
                  </Button>
                )}
              </div>
            </div>

            {/* Items Table */}
            {currentItems.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>No items in this category</p>
              </div>
            ) : (
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className={cn("w-full", activeTab === 'mida' ? "text-xs" : "text-sm")}>
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className={cn(activeTab === 'mida' ? "w-8 px-2 py-2" : "w-10 px-4 py-3")}></th>
                      <th className={cn("text-left font-semibold", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>Line</th>
                      <th className={cn("text-left font-semibold", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>HS Code</th>
                      <th className={cn("text-left font-semibold", activeTab === 'mida' ? "px-2 py-2 max-w-[150px]" : "px-4 py-3")}>Description</th>
                      <th className={cn("text-right font-semibold", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>Quantity</th>
                      <th className={cn("text-right font-semibold", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>Net Wt (kg)</th>
                      <th className={cn("text-left font-semibold", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>UOM</th>
                      <th className={cn("text-right font-semibold", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>Amount</th>
                      <th className={cn("text-center font-semibold", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>SST</th>
                      {activeTab === 'mida' && (
                        <>
                          <th className="px-2 py-2 text-left font-semibold">Certificate</th>
                          <th className="px-2 py-2 text-right font-semibold">Balance</th>
                        </>
                      )}
                      <th className={cn("text-center font-semibold", activeTab === 'mida' ? "px-2 py-2 w-24" : "px-4 py-3")}>Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {currentItems.map((item, index) => (
                      <tr
                        key={item.id || index}
                        className={cn(
                          'hover:bg-gray-50 transition-colors',
                          item.manually_moved ? 'bg-orange-50/50' : '',
                          currentSelection.has(index) && 'bg-blue-50'
                        )}
                      >
                        <td className={cn("text-center", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>
                          <input
                            type="checkbox"
                            checked={currentSelection.has(index)}
                            onChange={() => toggleItemSelection(index)}
                            className={cn("rounded border-gray-300", activeTab === 'mida' ? "w-3 h-3" : "")}
                          />
                        </td>
                        <td className={cn(activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>
                          <div className="flex items-center gap-1">
                            {item.line_no}
                            {item.manually_moved && (
                              <ArrowRightLeft className="w-3 h-3 text-orange-500" title="Manually moved to this table" />
                            )}
                          </div>
                        </td>
                        <td className={cn("font-mono text-blue-600", activeTab === 'mida' ? "px-2 py-2 whitespace-nowrap" : "px-4 py-3")}>
                          {activeTab === 'mida' && item.mida_hs_code ? item.mida_hs_code : item.hs_code}
                        </td>
                        <td className={cn(activeTab === 'mida' ? "px-2 py-2 max-w-[150px] truncate" : "px-4 py-3 max-w-xs truncate")} title={item.description}>
                          {activeTab === 'mida' && item.mida_item_name && item.mida_line_no 
                            ? `${item.mida_item_name} (${item.mida_line_no})`
                            : item.description}
                        </td>
                        <td className={cn("text-right", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>{formatNumber(item.quantity)}</td>
                        <td className={cn("text-right", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>{item.net_weight_kg ? formatNumber(item.net_weight_kg) : '-'}</td>
                        <td className={cn(activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>{item.uom}</td>
                        <td className={cn("text-right", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>
                          {item.amount ? formatNumber(item.amount) : '-'}
                        </td>
                        <td className={cn("text-center", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>
                          <button
                            onClick={() => handleToggleSST(item.id)}
                            className={cn(
                              "font-semibold rounded-full transition-colors cursor-pointer border",
                              item.sst_exempted
                                ? "bg-green-100 text-green-700 border-green-200 hover:bg-green-200"
                                : "bg-yellow-100 text-yellow-700 border-yellow-200 hover:bg-yellow-200",
                              activeTab === 'mida' ? "px-2 py-0.5 text-[10px]" : "px-2 py-1 text-xs"
                            )}
                          >
                            {item.sst_exempted ? 'Exempt' : 'Taxable'}
                          </button>
                        </td>
                        {activeTab === 'mida' && (
                          <>
                            <td className="px-2 py-2">
                              <span className="text-purple-600 font-medium whitespace-nowrap">
                                {item.mida_certificate_number || '-'}
                              </span>
                            </td>
                            <td className={cn('px-2 py-2 text-right font-semibold', getQtyStatusClass(item))}>
                              <div
                                title={`Port Klang: ${formatNumber(item.remaining_port_klang || 0)}\nKLIA: ${formatNumber(item.remaining_klia || 0)}\nBKH: ${formatNumber(item.remaining_bukit_kayu_hitam || 0)}\nTotal: ${formatNumber(item.remaining_qty || 0)}`}
                              >
                                {item.port_specific_remaining !== undefined ? formatNumber(item.port_specific_remaining) : '-'}
                              </div>
                            </td>
                          </>
                        )}
                        <td className={cn("text-center", activeTab === 'mida' ? "px-2 py-2" : "px-4 py-3")}>
                          <div className={cn("flex justify-center gap-1", activeTab === 'mida' ? "whitespace-nowrap" : "")}>
                            {activeTab !== 'formd' && (
                              <button
                                onClick={() => handleMoveItem(item, 'formd')}
                                className={cn(
                                  "font-medium bg-green-50 text-green-700 hover:bg-green-100 rounded border border-green-200 text-center",
                                  activeTab === 'mida' ? "w-12 px-1 py-1 text-[10px]" : "px-2 py-1 text-[10px]"
                                )}
                                title="Move to Form-D"
                              >
                                Form-D
                              </button>
                            )}
                            {activeTab !== 'mida' && (
                              <button
                                onClick={() => handleMoveItem(item, 'mida')}
                                className={cn(
                                  "font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 rounded border border-blue-200 text-center",
                                  activeTab === 'mida' ? "w-12 px-1 py-1 text-[10px]" : "px-2 py-1 text-[10px]"
                                )}
                                title="Move to MIDA"
                              >
                                MIDA
                              </button>
                            )}
                            {activeTab !== 'duties' && (
                              <button
                                onClick={() => handleMoveItem(item, 'duties')}
                                className={cn(
                                  "font-medium bg-orange-50 text-orange-700 hover:bg-orange-100 rounded border border-orange-200 text-center",
                                  activeTab === 'mida' ? "w-12 px-1 py-1 text-[10px]" : "px-2 py-1 text-[10px]"
                                )}
                                title="Move to Duties Payable"
                              >
                                Duties
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}
      {/* Import Preview Modal */}
      <Modal
        isOpen={showPreviewModal}
        onClose={() => setShowPreviewModal(false)}
        title="Balance Update Preview"
        size="xl"
        footer={
          <div className="flex justify-end gap-3">
            <Button
              variant="outline"
              onClick={() => setShowPreviewModal(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleConfirmUpdate}
              isLoading={isUpdatingBalance}
              disabled={!previewData || previewData.has_overdrawns}
            >
              Confirm Update
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="bg-blue-50 border border-blue-200 p-4 rounded-lg text-sm text-blue-800">
            <p><strong>Declaration Ref:</strong> {declarationRefNo}</p>
            <p className="mt-1">
              This will update balances for {previewData?.total_items} items.
              Please review the changes below before confirming.
            </p>
          </div>

          {previewData?.has_depletions && (
            <div className="bg-yellow-50 border border-yellow-200 p-3 rounded-lg text-sm text-yellow-800 flex flex-col gap-1">
              <strong>Wait! Some items will be fully depleted.</strong>
            </div>
          )}

          {previewData?.has_overdrawns && (
            <div className="bg-red-50 border border-red-200 p-3 rounded-lg text-sm text-red-800 flex flex-col gap-1">
              <strong>Error: Some items would be overdrawn!</strong>
              <span>You cannot proceed with negative balances. Please adjust quantities.</span>
            </div>
          )}

          <div className="border rounded-lg overflow-hidden">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 text-gray-700 font-semibold border-b">
                <tr>
                  <th className="px-4 py-3">Item / Certificate</th>
                  <th className="px-4 py-3 text-right">Current Balance</th>
                  <th className="px-4 py-3 text-right">Deduction</th>
                  <th className="px-4 py-3 text-right">New Balance</th>
                  <th className="px-4 py-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {previewData?.previews.map((item, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-2">
                      <div className="font-medium">{item.item_name}</div>
                      <div className="text-xs text-gray-500">{item.certificate_number}</div>
                    </td>
                    <td className="px-4 py-2 text-right text-gray-600">
                      {formatNumber(item.current_balance)}
                    </td>
                    <td className="px-4 py-2 text-right font-medium text-red-600">
                      -{formatNumber(item.quantity_to_import)}
                    </td>
                    <td className={cn(
                      "px-4 py-2 text-right font-bold",
                      item.will_overdraw ? "text-red-600" : 
                      item.will_deplete ? "text-orange-500" : 
                      item.will_trigger_warning ? "text-yellow-600" : "text-green-600"
                    )}>
                      {formatNumber(item.balance_after_import)}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {item.will_overdraw ? (
                        <Badge variant="danger">Overdrawn</Badge>
                      ) : item.will_deplete ? (
                        <Badge variant="warning">Depleted</Badge>
                      ) : item.will_trigger_warning ? (
                        <Badge variant="warning">Low</Badge>
                      ) : (
                        <Badge variant="success">OK</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Modal>
    </div>
  );
}
