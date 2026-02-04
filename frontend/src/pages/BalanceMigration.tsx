import { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ArrowLeft,
  ArrowRight,
  Upload,
  CheckCircle,
  AlertTriangle,
  XCircle,
  FileSpreadsheet,
  RefreshCw,
  Check,
  X,
} from 'lucide-react';
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  FileUpload,
  Select,
  Alert,
  Badge,
  Breadcrumb,
} from '@/components/ui';
import { migrationService } from '@/services';
import {
  MigrationPreviewResponse,
  MigrationApplyResponse,
  ConflictResolution,
  ItemResolution,
  PORTS,
  Port,
} from '@/types';
import { cn, formatNumber } from '@/utils';

type WizardStep = 'upload' | 'certificate' | 'items' | 'apply' | 'summary';

export function BalanceMigration() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const preselectedCertificate = searchParams.get('certificate');

  // Wizard state
  const [currentStep, setCurrentStep] = useState<WizardStep>('upload');
  
  // Upload step state
  const [file, setFile] = useState<File | null>(null);
  const [port, setPort] = useState<Port>('port_klang');
  
  // Preview state
  const [preview, setPreview] = useState<MigrationPreviewResponse | null>(null);
  
  // Item resolutions state
  const [resolutions, setResolutions] = useState<Map<number, ConflictResolution>>(new Map());
  
  // Apply result state
  const [applyResult, setApplyResult] = useState<MigrationApplyResponse | null>(null);

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('No file selected');
      return migrationService.previewMigration(file, port);
    },
    onSuccess: (data) => {
      setPreview(data);
      
      // Initialize resolutions for mismatch items with default "keep_db_name"
      const initialResolutions = new Map<number, ConflictResolution>();
      data.items.forEach(item => {
        if (item.status === 'name_mismatch') {
          initialResolutions.set(item.line_no, 'keep_db_name');
        }
      });
      setResolutions(initialResolutions);
      
      // Move to certificate step
      setCurrentStep('certificate');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to preview migration');
    },
  });

  // Apply mutation
  const applyMutation = useMutation({
    mutationFn: () => {
      if (!preview || !preview.db_certificate_id) {
        throw new Error('No certificate found');
      }
      
      // Build resolutions array
      const resolutionsArray: ItemResolution[] = [];
      resolutions.forEach((resolution, lineNo) => {
        resolutionsArray.push({ line_no: lineNo, resolution });
      });
      
      return migrationService.applyMigration({
        certificate_id: preview.db_certificate_id,
        port: port,
        resolutions: resolutionsArray,
        items: preview.items,
      });
    },
    onSuccess: (data) => {
      setApplyResult(data);
      setCurrentStep('summary');
      
      // Invalidate cache to refresh balance data everywhere
      if (preview?.db_certificate_id) {
        queryClient.invalidateQueries({ queryKey: ['certificate-balances', preview.db_certificate_id] });
        queryClient.invalidateQueries({ queryKey: ['certificate', preview.db_certificate_id] });
      }
      
      if (data.success) {
        toast.success(`Migration completed! ${data.total_records_created} records created.`);
      } else {
        toast.error(`Migration completed with ${data.items_failed} failures.`);
      }
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to apply migration');
    },
  });

  // Items that need resolution (name_mismatch)
  const mismatchItems = useMemo(() => {
    return preview?.items.filter(item => item.status === 'name_mismatch') || [];
  }, [preview]);

  // Check if all mismatches have resolutions
  const allResolved = useMemo(() => {
    return mismatchItems.every(item => resolutions.has(item.line_no));
  }, [mismatchItems, resolutions]);

  const handleBack = () => {
    switch (currentStep) {
      case 'certificate':
        setCurrentStep('upload');
        break;
      case 'items':
        setCurrentStep('certificate');
        break;
      case 'apply':
        setCurrentStep('items');
        break;
      default:
        break;
    }
  };

  const handleNext = () => {
    switch (currentStep) {
      case 'upload':
        previewMutation.mutate();
        break;
      case 'certificate':
        if (preview?.certificate_found) {
          if (preview.mismatch_count > 0) {
            setCurrentStep('items');
          } else {
            setCurrentStep('apply');
          }
        }
        break;
      case 'items':
        setCurrentStep('apply');
        break;
      case 'apply':
        applyMutation.mutate();
        break;
      default:
        break;
    }
  };

  const handleResolutionChange = (lineNo: number, resolution: ConflictResolution) => {
    setResolutions(prev => new Map(prev).set(lineNo, resolution));
  };

  const getStepNumber = (step: WizardStep): number => {
    const steps: WizardStep[] = ['upload', 'certificate', 'items', 'apply', 'summary'];
    return steps.indexOf(step) + 1;
  };

  const isStepCompleted = (step: WizardStep): boolean => {
    const currentNum = getStepNumber(currentStep);
    const stepNum = getStepNumber(step);
    return stepNum < currentNum;
  };

  const renderStepIndicator = () => {
    const steps = [
      { key: 'upload', label: 'Upload' },
      { key: 'certificate', label: 'Verify' },
      { key: 'items', label: 'Review' },
      { key: 'apply', label: 'Apply' },
      { key: 'summary', label: 'Summary' },
    ];

    return (
      <div className="flex items-center justify-center mb-8">
        {steps.map((step, index) => (
          <div key={step.key} className="flex items-center">
            <div
              className={cn(
                'flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium',
                currentStep === step.key
                  ? 'bg-blue-600 text-white'
                  : isStepCompleted(step.key as WizardStep)
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-200 text-gray-600'
              )}
            >
              {isStepCompleted(step.key as WizardStep) ? (
                <Check className="w-4 h-4" />
              ) : (
                index + 1
              )}
            </div>
            <span
              className={cn(
                'ml-2 text-sm',
                currentStep === step.key ? 'font-semibold text-blue-600' : 'text-gray-500'
              )}
            >
              {step.label}
            </span>
            {index < steps.length - 1 && (
              <div className="w-12 h-0.5 mx-3 bg-gray-200" />
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderUploadStep = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="w-5 h-5" />
          Upload Balance Sheet
        </CardTitle>
      </CardHeader>
      <div className="p-6 space-y-6">
        <FileUpload
          label="Balance Sheet File (XLSX)"
          accept=".xlsx,.xlsm"
          value={file}
          onChange={setFile}
          helperText="Upload the company's balance sheet XLSX file with one sheet per item"
        />

        <Select
          label="Import Port"
          value={port}
          onChange={(e) => setPort(e.target.value as Port)}
          options={PORTS}
          helperText="All invoice records will be assigned to this port"
          required
        />

        {preselectedCertificate && (
          <Alert variant="info">
            Pre-selected certificate: <strong>{preselectedCertificate}</strong>
          </Alert>
        )}
      </div>
    </Card>
  );

  const renderCertificateStep = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileSpreadsheet className="w-5 h-5" />
          Certificate Verification
        </CardTitle>
      </CardHeader>
      <div className="p-6 space-y-6">
        {preview && (
          <>
            {/* XLSX Info */}
            <div className="bg-gray-50 rounded-lg p-4 space-y-2">
              <h3 className="font-semibold text-gray-700 mb-3">Extracted from XLSX:</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Certificate Number:</span>
                  <p className="font-medium">{preview.xlsx_certificate_number}</p>
                </div>
                <div>
                  <span className="text-gray-500">Company:</span>
                  <p className="font-medium">{preview.xlsx_company_name || '-'}</p>
                </div>
                <div>
                  <span className="text-gray-500">Validity Period:</span>
                  <p className="font-medium">{preview.xlsx_validity_period || '-'}</p>
                </div>
                <div>
                  <span className="text-gray-500">Import Port:</span>
                  <p className="font-medium">{PORTS.find(p => p.value === port)?.label}</p>
                </div>
              </div>
            </div>

            {/* Match Status */}
            {preview.certificate_found ? (
              <Alert variant="success" className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5" />
                Certificate found in database: <strong>{preview.db_certificate_number}</strong>
              </Alert>
            ) : (
              <Alert variant="error" className="flex items-center gap-2">
                <XCircle className="w-5 h-5" />
                Certificate not found in database. Please upload the certificate first.
              </Alert>
            )}

            {/* Summary Stats */}
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-blue-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-blue-600">{preview.total_items}</div>
                <div className="text-sm text-gray-600">Total Items</div>
              </div>
              <div className="bg-green-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-green-600">{preview.matched_count}</div>
                <div className="text-sm text-gray-600">Matched</div>
              </div>
              <div className="bg-yellow-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-yellow-600">{preview.mismatch_count}</div>
                <div className="text-sm text-gray-600">Name Mismatch</div>
              </div>
              <div className="bg-red-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-red-600">{preview.not_found_count}</div>
                <div className="text-sm text-gray-600">Not Found</div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-50 rounded-lg p-4 text-center">
                <div className="text-xl font-bold text-gray-700">{preview.total_invoices}</div>
                <div className="text-sm text-gray-600">Total Invoice Records</div>
              </div>
              <div className="bg-orange-50 rounded-lg p-4 text-center">
                <div className="text-xl font-bold text-orange-600">{preview.total_duplicates}</div>
                <div className="text-sm text-gray-600">Duplicate Invoices</div>
              </div>
            </div>
          </>
        )}
      </div>
    </Card>
  );

  const renderItemsStep = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-yellow-600" />
          Resolve Name Mismatches
        </CardTitle>
      </CardHeader>
      <div className="p-6 space-y-4">
        <Alert variant="warning">
          The following items have different names in the XLSX file compared to the database.
          Please choose how to handle each mismatch.
        </Alert>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">Line #</th>
                <th className="px-4 py-3 text-left font-semibold">XLSX Name</th>
                <th className="px-4 py-3 text-left font-semibold">Database Name</th>
                <th className="px-4 py-3 text-left font-semibold">Invoices</th>
                <th className="px-4 py-3 text-left font-semibold">Resolution</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {mismatchItems.map((item) => (
                <tr key={item.line_no} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{item.line_no}</td>
                  <td className="px-4 py-3">
                    <span className="text-yellow-700 bg-yellow-50 px-2 py-1 rounded">
                      {item.xlsx_item_name}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-blue-700 bg-blue-50 px-2 py-1 rounded">
                      {item.db_item_name}
                    </span>
                  </td>
                  <td className="px-4 py-3">{item.invoice_count}</td>
                  <td className="px-4 py-3">
                    <select
                      value={resolutions.get(item.line_no) || 'keep_db_name'}
                      onChange={(e) => handleResolutionChange(item.line_no, e.target.value as ConflictResolution)}
                      className="text-sm border rounded px-2 py-1"
                    >
                      <option value="keep_db_name">Keep DB name</option>
                      <option value="rename_db">Rename to XLSX name</option>
                      <option value="skip">Skip this item</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );

  const renderApplyStep = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RefreshCw className="w-5 h-5" />
          Confirm Migration
        </CardTitle>
      </CardHeader>
      <div className="p-6 space-y-6">
        <Alert variant="info">
          Review the migration summary below. Click "Apply Migration" to create the import records.
        </Alert>

        {preview && (
          <div className="space-y-4">
            <h3 className="font-semibold">Items to Process:</h3>
            <div className="overflow-x-auto max-h-96">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold">Line #</th>
                    <th className="px-4 py-3 text-left font-semibold">Item Name</th>
                    <th className="px-4 py-3 text-left font-semibold">Status</th>
                    <th className="px-4 py-3 text-right font-semibold">Invoices</th>
                    <th className="px-4 py-3 text-right font-semibold">Duplicates</th>
                    <th className="px-4 py-3 text-left font-semibold">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {preview.items.map((item) => {
                    const resolution = resolutions.get(item.line_no);
                    let action = 'Import';
                    if (item.status === 'not_found') action = 'Skip (not found)';
                    else if (resolution === 'skip') action = 'Skip (user choice)';
                    else if (resolution === 'rename_db') action = 'Import + Rename';

                    return (
                      <tr key={item.line_no} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium">{item.line_no}</td>
                        <td className="px-4 py-3">{item.xlsx_item_name}</td>
                        <td className="px-4 py-3">
                          {item.status === 'matched' && (
                            <Badge variant="success">Matched</Badge>
                          )}
                          {item.status === 'name_mismatch' && (
                            <Badge variant="warning">Mismatch</Badge>
                          )}
                          {item.status === 'not_found' && (
                            <Badge variant="danger">Not Found</Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">{item.invoice_count}</td>
                        <td className="px-4 py-3 text-right">
                          {item.duplicate_invoices.length > 0 ? (
                            <span className="text-orange-600">{item.duplicate_invoices.length}</span>
                          ) : (
                            <span className="text-gray-400">0</span>
                          )}
                        </td>
                        <td className="px-4 py-3">{action}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </Card>
  );

  const renderSummaryStep = () => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {applyResult?.success ? (
            <CheckCircle className="w-5 h-5 text-green-600" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-yellow-600" />
          )}
          Migration Summary
        </CardTitle>
      </CardHeader>
      <div className="p-6 space-y-6">
        {applyResult && (
          <>
            {/* Overall Result */}
            <Alert variant={applyResult.success ? 'success' : 'warning'}>
              {applyResult.success
                ? 'Migration completed successfully!'
                : `Migration completed with ${applyResult.items_failed} failures.`}
            </Alert>

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-green-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-green-600">
                  {applyResult.total_records_created}
                </div>
                <div className="text-sm text-gray-600">Records Created</div>
              </div>
              <div className="bg-blue-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-blue-600">
                  {applyResult.total_items_processed}
                </div>
                <div className="text-sm text-gray-600">Items Processed</div>
              </div>
              <div className="bg-gray-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-gray-600">
                  {applyResult.items_skipped}
                </div>
                <div className="text-sm text-gray-600">Items Skipped</div>
              </div>
              <div className="bg-orange-50 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-orange-600">
                  {applyResult.total_duplicates_skipped}
                </div>
                <div className="text-sm text-gray-600">Duplicates Skipped</div>
              </div>
            </div>

            {/* Per-Item Results */}
            <div className="space-y-2">
              <h3 className="font-semibold">Item Results:</h3>
              <div className="overflow-x-auto max-h-64">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-2 text-left">Line #</th>
                      <th className="px-4 py-2 text-left">Item Name</th>
                      <th className="px-4 py-2 text-left">Status</th>
                      <th className="px-4 py-2 text-right">Records</th>
                      <th className="px-4 py-2 text-right">Duplicates</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {applyResult.results.map((result) => (
                      <tr key={result.line_no}>
                        <td className="px-4 py-2">{result.line_no}</td>
                        <td className="px-4 py-2">
                          {result.item_name}
                          {result.name_updated && (
                            <span className="ml-2 text-xs text-blue-600">(renamed)</span>
                          )}
                        </td>
                        <td className="px-4 py-2">
                          {result.status === 'success' && (
                            <Badge variant="success">Success</Badge>
                          )}
                          {result.status === 'skipped' && (
                            <Badge variant="default">Skipped</Badge>
                          )}
                          {result.status === 'error' && (
                            <Badge variant="danger">Error</Badge>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right">{result.records_created}</td>
                        <td className="px-4 py-2 text-right">{result.duplicates_skipped}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Flagged Duplicates */}
            {applyResult.flagged_duplicates.length > 0 && (
              <div className="space-y-2">
                <h3 className="font-semibold text-orange-700">
                  Flagged Duplicates (Manual Review Required):
                </h3>
                <div className="bg-orange-50 rounded-lg p-4 max-h-48 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-orange-800">
                        <th className="pb-2">Item</th>
                        <th className="pb-2">Invoice #</th>
                        <th className="pb-2">Date</th>
                        <th className="pb-2 text-right">Quantity</th>
                      </tr>
                    </thead>
                    <tbody className="text-orange-700">
                      {applyResult.flagged_duplicates.map((dup, idx) => (
                        <tr key={idx}>
                          <td className="py-1">{dup.item_name} (#{dup.line_no})</td>
                          <td className="py-1">{dup.invoice_number}</td>
                          <td className="py-1">{dup.import_date}</td>
                          <td className="py-1 text-right">{formatNumber(dup.quantity)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  );

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 'upload':
        return renderUploadStep();
      case 'certificate':
        return renderCertificateStep();
      case 'items':
        return renderItemsStep();
      case 'apply':
        return renderApplyStep();
      case 'summary':
        return renderSummaryStep();
      default:
        return null;
    }
  };

  const canProceed = (): boolean => {
    switch (currentStep) {
      case 'upload':
        return !!file && !!port;
      case 'certificate':
        return preview?.certificate_found === true;
      case 'items':
        return allResolved;
      case 'apply':
        return true;
      default:
        return false;
    }
  };

  return (
    <div className="max-w-5xl mx-auto py-6 px-4 space-y-6">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { label: 'Database', href: '/database' },
          { label: 'Balance Sheet Migration' },
        ]}
      />

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">
          Balance Sheet Migration
        </h1>
        <Button variant="ghost" onClick={() => navigate('/database')}>
          <X className="w-4 h-4 mr-2" />
          Cancel
        </Button>
      </div>

      {/* Step Indicator */}
      {renderStepIndicator()}

      {/* Current Step Content */}
      {renderCurrentStep()}

      {/* Navigation Buttons */}
      <div className="flex justify-between pt-4">
        <Button
          variant="outline"
          onClick={handleBack}
          disabled={currentStep === 'upload' || currentStep === 'summary'}
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>

        {currentStep !== 'summary' ? (
          <Button
            onClick={handleNext}
            disabled={!canProceed() || previewMutation.isPending || applyMutation.isPending}
          >
            {previewMutation.isPending || applyMutation.isPending ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Processing...
              </>
            ) : currentStep === 'apply' ? (
              <>
                Apply Migration
                <Check className="w-4 h-4 ml-2" />
              </>
            ) : (
              <>
                Next
                <ArrowRight className="w-4 h-4 ml-2" />
              </>
            )}
          </Button>
        ) : (
          <Button onClick={() => navigate('/database')}>
            <Check className="w-4 h-4 mr-2" />
            Done
          </Button>
        )}
      </div>
    </div>
  );
}
