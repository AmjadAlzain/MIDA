import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  ArrowLeft,
  Package,
  Plus,
  FileText,
  Edit2,
  Trash2,
  Save,
} from 'lucide-react';
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  Input,
  Badge,
  Breadcrumb,
  Modal,
  Alert,
  Select,
  ConfirmModal,
} from '@/components/ui';
import { importService, certificateService } from '@/services';
import { UpdateImportRequest } from '@/services/importService';
import {
  ImportRecord,
  ImportRecordsResponse,
  Certificate,
  CertificateItemBalance,
  CertificateItemsResponse,
  Port,
  PORT_DISPLAY_NAMES,
  PORTS,
} from '@/types';
import { formatNumber, formatDate, getTodayISO } from '@/utils';

export function ItemImports() {
  const { certId, itemId } = useParams<{ certId: string; itemId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // State
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingImport, setEditingImport] = useState<ImportRecord | null>(null);
  const [deleteImportId, setDeleteImportId] = useState<string | null>(null);
  const [newImport, setNewImport] = useState({
    import_date: getTodayISO(),
    invoice_number: '',
    invoice_line: '1',
    declaration_form_reg_no: '',
    quantity_imported: '',
    port: 'port_klang' as Port,
    remarks: '',
  });
  const [editForm, setEditForm] = useState({
    import_date: '',
    invoice_number: '',
    invoice_line: '',
    declaration_form_reg_no: '',
    quantity_imported: '',
    port: 'port_klang' as Port,
    remarks: '',
  });

  // Fetch certificate
  const { data: certificate } = useQuery<Certificate>({
    queryKey: ['certificate', certId],
    queryFn: () => certificateService.getById(certId!),
    enabled: !!certId,
  });

  // Fetch item balances to get current item details
  const { data: balancesResponse, isLoading: isLoadingBalances } = useQuery<CertificateItemsResponse>({
    queryKey: ['certificate-balances', certId],
    queryFn: () => certificateService.getItemBalances(certId!),
    enabled: !!certId,
    staleTime: 0, // Always refetch balance data to ensure up-to-date values
    refetchOnMount: 'always', // Always refetch when component mounts
  });

  // Find current item from balances (includes remaining quantities)
  const currentItem: CertificateItemBalance | undefined = balancesResponse?.items?.find(
    (item) => item.item_id === itemId
  );

  // Fetch imports for this item
  const {
    data: importsResponse,
    isLoading,
  } = useQuery<ImportRecordsResponse>({
    queryKey: ['imports', itemId],
    queryFn: () => importService.getByItemId(itemId!),
    enabled: !!itemId,
  });

  const imports = importsResponse?.imports ?? [];

  // Add import mutation
  const addMutation = useMutation({
    mutationFn: (data: typeof newImport) =>
      importService.createBulk({
        records: [
          {
            certificate_item_id: itemId!,
            import_date: data.import_date,
            invoice_number: data.invoice_number,
            invoice_line: parseInt(data.invoice_line) || 1,
            declaration_form_reg_no: data.declaration_form_reg_no || undefined,
            quantity_imported: parseFloat(data.quantity_imported),
            port: data.port,
            remarks: data.remarks || undefined,
          },
        ],
      }),
    onSuccess: () => {
      toast.success('Import record added successfully');
      queryClient.invalidateQueries({ queryKey: ['imports', itemId] });
      queryClient.invalidateQueries({ queryKey: ['certificate-balances', certId] });
      setShowAddModal(false);
      setNewImport({
        import_date: getTodayISO(),
        invoice_number: '',
        invoice_line: '1',
        declaration_form_reg_no: '',
        quantity_imported: '',
        port: 'port_klang',
        remarks: '',
      });
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to add import record');
    },
  });

  // Update import mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateImportRequest }) =>
      importService.update(id, data),
    onSuccess: () => {
      toast.success('Import record updated successfully');
      queryClient.invalidateQueries({ queryKey: ['imports', itemId] });
      queryClient.invalidateQueries({ queryKey: ['certificate-balances', certId] });
      setEditingImport(null);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update import record');
    },
  });

  // Delete import mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => importService.delete(id),
    onSuccess: () => {
      toast.success('Import record deleted successfully');
      queryClient.invalidateQueries({ queryKey: ['imports', itemId] });
      queryClient.invalidateQueries({ queryKey: ['certificate-balances', certId] });
      setDeleteImportId(null);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to delete import record');
    },
  });

  // Handle add import
  const handleAddImport = () => {
    if (!newImport.quantity_imported || !newImport.invoice_number) {
      toast.error('Quantity and Invoice Number are required');
      return;
    }

    const quantity = parseFloat(newImport.quantity_imported);
    if (isNaN(quantity) || quantity <= 0) {
      toast.error('Please enter a valid quantity');
      return;
    }

    addMutation.mutate(newImport);
  };

  // Handle start editing
  const handleStartEdit = (imp: ImportRecord) => {
    setEditingImport(imp);
    setEditForm({
      import_date: imp.import_date,
      invoice_number: imp.invoice_number,
      invoice_line: imp.invoice_line?.toString() || '',
      declaration_form_reg_no: imp.declaration_form_reg_no || '',
      quantity_imported: imp.quantity_imported.toString(),
      port: imp.port as Port,
      remarks: imp.remarks || '',
    });
  };

  // Handle save edit
  const handleSaveEdit = () => {
    if (!editingImport) return;

    const data: UpdateImportRequest = {};
    
    if (editForm.import_date !== editingImport.import_date) {
      data.import_date = editForm.import_date;
    }
    if (editForm.invoice_number !== editingImport.invoice_number) {
      data.invoice_number = editForm.invoice_number;
    }
    if (editForm.invoice_line !== (editingImport.invoice_line?.toString() || '')) {
      data.invoice_line = parseInt(editForm.invoice_line) || undefined;
    }
    if (editForm.declaration_form_reg_no !== (editingImport.declaration_form_reg_no || '')) {
      data.declaration_form_reg_no = editForm.declaration_form_reg_no || undefined;
    }
    if (parseFloat(editForm.quantity_imported) !== editingImport.quantity_imported) {
      data.quantity_imported = parseFloat(editForm.quantity_imported);
    }
    if (editForm.port !== editingImport.port) {
      data.port = editForm.port;
    }
    if (editForm.remarks !== (editingImport.remarks || '')) {
      data.remarks = editForm.remarks || undefined;
    }

    updateMutation.mutate({ id: editingImport.id, data });
  };

  // Handle delete confirmation
  const handleConfirmDelete = () => {
    if (deleteImportId) {
      deleteMutation.mutate(deleteImportId);
    }
  };

  // Port options for select
  const portOptions = PORTS.map((p) => ({
    value: p.value,
    label: p.label,
  }));

  // Show loading spinner while data is being fetched
  if (isLoadingBalances || !certificate) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  // Show error message if item not found after data has loaded
  if (!currentItem) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <Package className="h-12 w-12 text-gray-400" />
        <p className="text-gray-600">Item not found</p>
        <Button variant="outline" onClick={() => navigate(`/database/certificates/${certId}`)}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Certificate
        </Button>
      </div>
    );
  }

  const remainingBalance = currentItem.remaining_quantity;

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { label: 'Database', href: '/database' },
          {
            label: certificate.certificate_number,
            href: `/database/certificates/${certId}`,
          },
          { label: `Item #${currentItem.line_no}` },
        ]}
      />

      {/* Item Summary */}
      <Card>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <Badge variant="purple">Line #{currentItem.line_no}</Badge>
              <span className="font-mono text-blue-600 text-lg">{currentItem.hs_code}</span>
            </div>
            <p className="text-gray-700 mb-3">{currentItem.item_name}</p>
            <div className="flex items-center gap-6 text-sm mb-4">
              <span className="text-gray-500">
                Approved: <strong>{formatNumber(currentItem.approved_quantity)}</strong>{' '}
                {currentItem.uom}
              </span>
              <span className={remainingBalance > 0 ? 'text-green-600' : 'text-red-600'}>
                Remaining: <strong>{formatNumber(remainingBalance)}</strong> {currentItem.uom}
              </span>
            </div>
            
            {/* Port Allocation Breakdown */}
            <div className="bg-gray-50 rounded-lg p-3 mt-2">
              <p className="text-xs font-semibold text-gray-600 mb-2">Port Allocation (Approved / Remaining)</p>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div className="flex flex-col">
                  <span className="text-gray-500 text-xs">Port Klang</span>
                  <span>
                    <span className="text-gray-700">{formatNumber(currentItem.port_klang_qty ?? 0)}</span>
                    <span className="text-gray-400 mx-1">/</span>
                    <span className={(currentItem.remaining_port_klang ?? 0) > 0 ? 'text-green-600 font-medium' : (currentItem.remaining_port_klang ?? 0) < 0 ? 'text-red-600 font-medium' : 'text-gray-500'}>
                      {formatNumber(currentItem.remaining_port_klang ?? 0)}
                    </span>
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-gray-500 text-xs">KLIA</span>
                  <span>
                    <span className="text-gray-700">{formatNumber(currentItem.klia_qty ?? 0)}</span>
                    <span className="text-gray-400 mx-1">/</span>
                    <span className={(currentItem.remaining_klia ?? 0) > 0 ? 'text-green-600 font-medium' : (currentItem.remaining_klia ?? 0) < 0 ? 'text-red-600 font-medium' : 'text-gray-500'}>
                      {formatNumber(currentItem.remaining_klia ?? 0)}
                    </span>
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-gray-500 text-xs">Bukit Kayu Hitam</span>
                  <span>
                    <span className="text-gray-700">{formatNumber(currentItem.bukit_kayu_hitam_qty ?? 0)}</span>
                    <span className="text-gray-400 mx-1">/</span>
                    <span className={(currentItem.remaining_bukit_kayu_hitam ?? 0) > 0 ? 'text-green-600 font-medium' : (currentItem.remaining_bukit_kayu_hitam ?? 0) < 0 ? 'text-red-600 font-medium' : 'text-gray-500'}>
                      {formatNumber(currentItem.remaining_bukit_kayu_hitam ?? 0)}
                    </span>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 ml-4">
            <Button
              variant="secondary"
              onClick={() => navigate(`/database/certificates/${certId}`)}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
            <Button variant="primary" onClick={() => setShowAddModal(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Add Import
            </Button>
          </div>
        </div>
      </Card>

      {/* Import Records */}
      <Card>
        <CardHeader>
          <CardTitle icon={<FileText className="w-5 h-5 text-green-600" />}>
            Import Records
            <Badge variant="info" className="ml-2">
              {imports.length}
            </Badge>
          </CardTitle>
        </CardHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin h-6 w-6 border-4 border-blue-600 border-t-transparent rounded-full" />
          </div>
        ) : imports.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-4 py-3 text-left font-semibold">Date</th>
                  <th className="px-4 py-3 text-left font-semibold">Invoice #</th>
                  <th className="px-4 py-3 text-left font-semibold">Line</th>
                  <th className="px-4 py-3 text-left font-semibold">Form Reg No</th>
                  <th className="px-4 py-3 text-left font-semibold">Port</th>
                  <th className="px-4 py-3 text-right font-semibold">Quantity</th>
                  <th className="px-4 py-3 text-right font-semibold">Balance After</th>
                  <th className="px-4 py-3 text-left font-semibold">Remarks</th>
                  <th className="px-4 py-3 text-center font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {imports.map((imp: ImportRecord) => (
                  <tr key={imp.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">{formatDate(imp.import_date)}</td>
                    <td className="px-4 py-3 font-medium">{imp.invoice_number}</td>
                    <td className="px-4 py-3">{imp.invoice_line}</td>
                    <td className="px-4 py-3">{imp.declaration_form_reg_no || '-'}</td>
                    <td className="px-4 py-3">{PORT_DISPLAY_NAMES[imp.port]}</td>
                    <td className="px-4 py-3 text-right">{formatNumber(imp.quantity_imported)}</td>
                    <td className="px-4 py-3 text-right font-semibold">
                      {formatNumber(imp.balance_after)}
                    </td>
                    <td className="px-4 py-3 text-gray-500 max-w-xs truncate" title={imp.remarks || ''}>
                      {imp.remarks || '-'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleStartEdit(imp)}
                          title="Edit"
                        >
                          <Edit2 className="w-4 h-4 text-blue-600" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteImportId(imp.id)}
                          title="Delete"
                          className="text-red-600 hover:bg-red-50"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No import records yet</p>
            <Button variant="primary" onClick={() => setShowAddModal(true)} className="mt-4">
              Add First Import
            </Button>
          </div>
        )}
      </Card>

      {/* Add Import Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="Add Import Record"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button
              variant="success"
              onClick={handleAddImport}
              isLoading={addMutation.isPending}
            >
              Add Import
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Alert variant="info">
            Remaining balance: <strong>{formatNumber(remainingBalance)}</strong> {currentItem.uom}
          </Alert>

          <div className="grid md:grid-cols-2 gap-4">
            <Input
              label="Import Date"
              type="date"
              value={newImport.import_date}
              onChange={(e) => setNewImport({ ...newImport, import_date: e.target.value })}
              required
            />
            <Input
              label="Invoice Number"
              value={newImport.invoice_number}
              onChange={(e) => setNewImport({ ...newImport, invoice_number: e.target.value })}
              placeholder="e.g., INV-2024-001"
              required
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <Input
              label="Invoice Line"
              type="number"
              value={newImport.invoice_line}
              onChange={(e) => setNewImport({ ...newImport, invoice_line: e.target.value })}
              placeholder="1"
            />
            <Input
              label="Declaration Form Reg No"
              value={newImport.declaration_form_reg_no}
              onChange={(e) =>
                setNewImport({ ...newImport, declaration_form_reg_no: e.target.value })
              }
              placeholder="Optional"
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <Input
              label={`Quantity (${currentItem.uom})`}
              type="number"
              value={newImport.quantity_imported}
              onChange={(e) => setNewImport({ ...newImport, quantity_imported: e.target.value })}
              placeholder="0"
              required
            />
            <Select
              label="Port"
              value={newImport.port}
              onChange={(e) => setNewImport({ ...newImport, port: e.target.value as Port })}
              options={portOptions}
            />
          </div>

          <Input
            label="Remarks"
            value={newImport.remarks}
            onChange={(e) => setNewImport({ ...newImport, remarks: e.target.value })}
            placeholder="Optional notes..."
          />
        </div>
      </Modal>

      {/* Edit Import Modal */}
      <Modal
        isOpen={editingImport !== null}
        onClose={() => setEditingImport(null)}
        title="Edit Import Record"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditingImport(null)}>
              Cancel
            </Button>
            <Button
              variant="success"
              onClick={handleSaveEdit}
              isLoading={updateMutation.isPending}
            >
              <Save className="w-4 h-4 mr-2" />
              Save Changes
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Input
              label="Import Date"
              type="date"
              value={editForm.import_date}
              onChange={(e) => setEditForm({ ...editForm, import_date: e.target.value })}
              required
            />
            <Input
              label="Invoice Number"
              value={editForm.invoice_number}
              onChange={(e) => setEditForm({ ...editForm, invoice_number: e.target.value })}
              placeholder="e.g., INV-2024-001"
              required
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <Input
              label="Invoice Line"
              type="number"
              value={editForm.invoice_line}
              onChange={(e) => setEditForm({ ...editForm, invoice_line: e.target.value })}
              placeholder="1"
            />
            <Input
              label="Declaration Form Reg No"
              value={editForm.declaration_form_reg_no}
              onChange={(e) => setEditForm({ ...editForm, declaration_form_reg_no: e.target.value })}
              placeholder="Optional"
            />
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <Input
              label={`Quantity (${currentItem.uom})`}
              type="number"
              value={editForm.quantity_imported}
              onChange={(e) => setEditForm({ ...editForm, quantity_imported: e.target.value })}
              placeholder="0"
              required
            />
            <Select
              label="Port"
              value={editForm.port}
              onChange={(e) => setEditForm({ ...editForm, port: e.target.value as Port })}
              options={portOptions}
            />
          </div>

          <Input
            label="Remarks"
            value={editForm.remarks}
            onChange={(e) => setEditForm({ ...editForm, remarks: e.target.value })}
            placeholder="Optional notes..."
          />
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={deleteImportId !== null}
        onClose={() => setDeleteImportId(null)}
        onConfirm={handleConfirmDelete}
        title="Delete Import Record"
        message="Are you sure you want to delete this import record? This action cannot be undone and may affect balance calculations."
        confirmText="Delete"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
