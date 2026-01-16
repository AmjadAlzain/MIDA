import { useState } from 'react';
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
      const newItem: CertificateItem = {
        id: `temp-${Date.now()}`,
        line_no: items.length + 1,
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
      const items = prev.items.filter((_, i) => i !== index);
      // Re-number items
      return {
        ...prev,
        items: items.map((item, i) => ({ ...item, line_no: i + 1 })),
      };
    });
    setDeleteItemIndex(null);
  };

  // Get balance for an item
  const getItemBalance = (itemId: string): CertificateItemBalance | undefined => {
    return itemBalances.find((b) => b.item_id === itemId);
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
                <Button variant="secondary" onClick={handleCancelEdit}>
                  <X className="w-4 h-4 mr-2" />
                  Cancel
                </Button>
                <Button
                  variant="success"
                  onClick={handleSave}
                  isLoading={updateMutation.isPending}
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
                  <Button variant="primary" onClick={handleStartEdit}>
                    <Edit2 className="w-4 h-4 mr-2" />
                    Edit
                  </Button>
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
            />
            <Input
              label="Company Name"
              value={currentData.company_name}
              onChange={(e) => handleFieldChange('company_name', e.target.value)}
            />
            <Input
              label="Model Number"
              value={currentData.model_number || ''}
              onChange={(e) => handleFieldChange('model_number', e.target.value)}
            />
            <Input
              label="Exemption Start"
              type="date"
              value={currentData.exemption_start_date?.split('T')[0] || ''}
              onChange={(e) => handleFieldChange('exemption_start_date', e.target.value)}
            />
            <Input
              label="Exemption End"
              type="date"
              value={currentData.exemption_end_date?.split('T')[0] || ''}
              onChange={(e) => handleFieldChange('exemption_end_date', e.target.value)}
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
            isEditing && (
              <Button
                variant="secondary"
                size="sm"
                onClick={handleAddItem}
                leftIcon={<Plus className="w-4 h-4" />}
              >
                Add Item
              </Button>
            )
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
                  <th className="px-3 py-3 text-left font-semibold">HS Code</th>
                  <th className="px-3 py-3 text-left font-semibold">Item Name</th>
                  <th className="px-3 py-3 text-right font-semibold w-32">Approved Qty</th>
                  <th className="px-3 py-3 text-left font-semibold w-24">UOM</th>
                  <th className="px-3 py-3 text-center font-semibold w-20">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {editedCertificate.items.map((item, index) => (
                  <tr key={item.id || index} className="hover:bg-gray-50">
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
