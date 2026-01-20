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
} from 'lucide-react';
import { Button, Card, CardHeader, CardTitle, FileUpload, Badge, Select, Input } from '@/components/ui';
import { classificationService, companyService, certificateService } from '@/services';
import { ClassificationResponse, ClassificationItem, Company, K1ExportItem, Certificate, COUNTRIES } from '@/types';
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
  const [activeTab, setActiveTab] = useState<ConverterTab>('formd');
  const [selectedItems, setSelectedItems] = useState<Record<string, Set<number>>>({
    formd: new Set(),
    mida: new Set(),
    duties: new Set(),
  });
  const [isExporting, setIsExporting] = useState(false);
  const [selectedCertificateIds, setSelectedCertificateIds] = useState<string[]>([]);

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
      setClassificationResult(result);
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
        description: item.description,
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
      
      classificationService.downloadBlob(blob, `K1_Export_${exportType}.xlsx`);
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
              </div>
              
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

            {/* Items Table */}
            {currentItems.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>No items in this category</p>
              </div>
            ) : (
              <div className="overflow-x-auto border border-gray-200 rounded-lg">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="w-10 px-4 py-3"></th>
                      <th className="px-4 py-3 text-left font-semibold">Line</th>
                      <th className="px-4 py-3 text-left font-semibold">HS Code</th>
                      <th className="px-4 py-3 text-left font-semibold">Description</th>
                      <th className="px-4 py-3 text-right font-semibold">Quantity</th>
                      <th className="px-4 py-3 text-left font-semibold">UOM</th>
                      <th className="px-4 py-3 text-right font-semibold">Amount</th>
                      <th className="px-4 py-3 text-center font-semibold">SST</th>
                      {activeTab === 'mida' && (
                        <>
                          <th className="px-4 py-3 text-left font-semibold">Certificate</th>
                          <th className="px-4 py-3 text-right font-semibold">Balance</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {currentItems.map((item, index) => (
                      <tr
                        key={item.id || index}
                        className={cn(
                          'hover:bg-gray-50 transition-colors',
                          currentSelection.has(index) && 'bg-blue-50'
                        )}
                      >
                        <td className="px-4 py-3 text-center">
                          <input
                            type="checkbox"
                            checked={currentSelection.has(index)}
                            onChange={() => toggleItemSelection(index)}
                            className="rounded border-gray-300"
                          />
                        </td>
                        <td className="px-4 py-3">{item.line_no}</td>
                        <td className="px-4 py-3 font-mono text-blue-600">{item.hs_code}</td>
                        <td className="px-4 py-3 max-w-xs truncate" title={item.description}>
                          {item.description}
                        </td>
                        <td className="px-4 py-3 text-right">{formatNumber(item.quantity)}</td>
                        <td className="px-4 py-3">{item.uom}</td>
                        <td className="px-4 py-3 text-right">
                          {item.amount ? formatNumber(item.amount) : '-'}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {item.sst_exempted ? (
                            <Badge variant="success">Exempt</Badge>
                          ) : (
                            <Badge variant="default">Taxable</Badge>
                          )}
                        </td>
                        {activeTab === 'mida' && (
                          <>
                            <td className="px-4 py-3">
                              <span className="text-purple-600 font-medium">
                                {item.mida_certificate_number || '-'}
                              </span>
                            </td>
                            <td className={cn('px-4 py-3 text-right font-semibold', getQtyStatusClass(item))}>
                              {item.remaining_qty !== undefined ? formatNumber(item.remaining_qty) : '-'}
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
