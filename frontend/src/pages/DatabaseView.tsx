import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { certificateService } from '@/services';
import { Certificate, CertificateListResponse } from '@/types';
import { Button, Input, Table, Tabs, StatusBadge, ConfirmModal } from '@/components/ui';
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  Trash2,
  RotateCcw,
  AlertTriangle,
  Search,
  Database,
} from 'lucide-react';

const PAGE_SIZE = 20;

// Helper to format dates
const formatDate = (dateString: string): string => {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return dateString;
  }
};

export function DatabaseView() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'active' | 'deleted'>('active');
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [permanentDeleteDialogOpen, setPermanentDeleteDialogOpen] = useState(false);
  const [selectedCertificate, setSelectedCertificate] = useState<Certificate | null>(null);

  // Calculate offset from page
  const offset = (currentPage - 1) * PAGE_SIZE;

  // Fetch active certificates
  const {
    data: activeCerts,
    isLoading: activeLoading,
    error: activeError,
  } = useQuery<CertificateListResponse>({
    queryKey: ['certificates', 'active', offset],
    queryFn: () => certificateService.getAll({ limit: PAGE_SIZE, offset }),
    enabled: activeTab === 'active',
  });

  // Fetch deleted certificates
  const {
    data: deletedCerts,
    isLoading: deletedLoading,
    error: deletedError,
  } = useQuery<CertificateListResponse>({
    queryKey: ['certificates', 'deleted', offset],
    queryFn: () => certificateService.getDeleted({ limit: PAGE_SIZE, offset }),
    enabled: activeTab === 'deleted',
  });

  // Soft delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => certificateService.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certificates'] });
      setDeleteDialogOpen(false);
      setSelectedCertificate(null);
    },
  });

  // Restore mutation
  const restoreMutation = useMutation({
    mutationFn: (id: string) => certificateService.restore(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certificates'] });
    },
  });

  // Permanent delete mutation
  const permanentDeleteMutation = useMutation({
    mutationFn: (id: string) => certificateService.permanentDelete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certificates'] });
      setPermanentDeleteDialogOpen(false);
      setSelectedCertificate(null);
    },
  });

  const handleDelete = (cert: Certificate) => {
    setSelectedCertificate(cert);
    setDeleteDialogOpen(true);
  };

  const handlePermanentDelete = (cert: Certificate) => {
    setSelectedCertificate(cert);
    setPermanentDeleteDialogOpen(true);
  };

  const handleRestore = (cert: Certificate) => {
    restoreMutation.mutate(cert.id);
  };

  const confirmDelete = () => {
    if (selectedCertificate) {
      deleteMutation.mutate(selectedCertificate.id);
    }
  };

  const confirmPermanentDelete = () => {
    if (selectedCertificate) {
      permanentDeleteMutation.mutate(selectedCertificate.id);
    }
  };

  const handleTabChange = (tabId: string) => {
    setActiveTab(tabId as 'active' | 'deleted');
    setCurrentPage(1);
    setSearchQuery('');
  };

  // Filter certificates by search query
  const filterCertificates = (certs: Certificate[] | undefined) => {
    if (!certs) return [];
    if (!searchQuery.trim()) return certs;
    const query = searchQuery.toLowerCase();
    return certs.filter(
      (cert) =>
        cert.certificate_number.toLowerCase().includes(query) ||
        cert.company_name.toLowerCase().includes(query)
    );
  };

  const currentData = activeTab === 'active' ? activeCerts : deletedCerts;
  const isLoading = activeTab === 'active' ? activeLoading : deletedLoading;
  const error = activeTab === 'active' ? activeError : deletedError;
  const filteredCerts = filterCertificates(currentData?.items);
  const totalItems = currentData?.total ?? 0;
  const totalPages = Math.ceil(totalItems / PAGE_SIZE);

  const tabs = [
    { id: 'active', label: 'Active Certificates', count: activeCerts?.total, color: 'blue' as const },
    { id: 'deleted', label: 'Deleted Certificates', count: deletedCerts?.total, color: 'orange' as const },
  ];

  // Table columns for certificates
  const tableColumns = [
    {
      key: 'certificate_number',
      header: 'Certificate Number',
      cell: (cert: Certificate) => (
        <span className="font-medium text-blue-600">{cert.certificate_number}</span>
      ),
    },
    {
      key: 'company_name',
      header: 'Company',
      cell: (cert: Certificate) => cert.company_name,
    },
    {
      key: 'validity',
      header: 'Validity Period',
      cell: (cert: Certificate) => (
        <span>
          {formatDate(cert.exemption_start_date)} - {formatDate(cert.exemption_end_date)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      cell: (cert: Certificate) => <StatusBadge status={cert.status} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      headerClassName: 'text-right',
      cell: (cert: Certificate) => (
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(`/database/certificates/${cert.id}`)}
          >
            <Eye className="h-4 w-4 mr-1" />
            View
          </Button>
          {activeTab === 'deleted' && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleRestore(cert)}
              disabled={restoreMutation.isPending}
            >
              <RotateCcw className="h-4 w-4 mr-1" />
              Restore
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => activeTab === 'deleted' ? handlePermanentDelete(cert) : handleDelete(cert)}
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <Trash2 className="h-4 w-4 mr-1" />
            {activeTab === 'deleted' ? 'Delete Forever' : 'Delete'}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Database className="h-8 w-8 text-blue-600" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Certificate Database</h1>
            <p className="text-gray-500">
              Manage MIDA certificates and their exemption records
            </p>
          </div>
        </div>
        <Link to="/certificate-parser">
          <Button>Upload New Certificate</Button>
        </Link>
      </div>

      {/* Tabs and Search */}
      <div className="flex items-center justify-between">
        <Tabs tabs={tabs} activeTab={activeTab} onTabChange={handleTabChange} />
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <Input
            placeholder="Search certificates..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            <span>Error loading certificates: {(error as Error).message}</span>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <Table
          columns={tableColumns}
          data={filteredCerts}
          keyExtractor={(cert) => cert.id}
          isLoading={isLoading}
          emptyState={
            <div className="text-center py-12 text-gray-500">
              <Database className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No certificates found</p>
            </div>
          }
          onRowClick={(cert) => navigate(`/database/certificates/${cert.id}`)}
        />
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-500">
            Showing {offset + 1} to {Math.min(offset + PAGE_SIZE, totalItems)} of {totalItems} certificates
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <span className="text-sm text-gray-500">
              Page {currentPage} of {totalPages}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Soft Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={confirmDelete}
        title="Delete Certificate"
        message={
          <>
            Are you sure you want to delete certificate{' '}
            <strong>{selectedCertificate?.certificate_number}</strong>? This will move it to the
            deleted certificates list where it can be restored later.
          </>
        }
        confirmText="Delete"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />

      {/* Permanent Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={permanentDeleteDialogOpen}
        onClose={() => setPermanentDeleteDialogOpen(false)}
        onConfirm={confirmPermanentDelete}
        title="Permanently Delete Certificate"
        message={
          <>
            <strong className="text-red-600">This action cannot be undone.</strong> Are you
            sure you want to permanently delete certificate{' '}
            <strong>{selectedCertificate?.certificate_number}</strong>? All associated import
            records will also be deleted.
          </>
        }
        confirmText="Permanently Delete"
        variant="danger"
        isLoading={permanentDeleteMutation.isPending}
      />
    </div>
  );
}
