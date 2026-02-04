import { useState, useEffect, useMemo } from 'react';
import { AlertTriangle, Search, Check, Package } from 'lucide-react';
import { Modal, Button, Input, Badge } from '@/components/ui';
import { certificateService } from '@/services';
import { Certificate, CertificateItem, ClassificationItem, Port } from '@/types';
import { cn, formatNumber } from '@/utils';

interface MidaCertificateSelectorProps {
  isOpen: boolean;
  onClose: () => void;
  /** The invoice item being matched */
  item: ClassificationItem;
  /** The certificates available for selection (already selected for matching) */
  availableCertificates: Certificate[];
  /** The currently selected port */
  selectedPort: Port;
  /** Callback when a manual match is confirmed */
  onConfirmMatch: (
    item: ClassificationItem,
    certificate: Certificate,
    certificateItem: CertificateItem
  ) => void;
}

/**
 * Calculate similarity score between two strings using token-based matching.
 * This mirrors the backend's matching logic for consistency.
 */
function calculateSimilarity(text1: string, text2: string): number {
  if (!text1 || !text2) return 0;

  // Normalize both strings
  const normalize = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

  const norm1 = normalize(text1);
  const norm2 = normalize(text2);

  if (norm1 === norm2) return 1.0;

  // Token-based similarity (Jaccard)
  const tokens1 = new Set(norm1.split(' '));
  const tokens2 = new Set(norm2.split(' '));

  const intersection = [...tokens1].filter((t) => tokens2.has(t)).length;
  const union = new Set([...tokens1, ...tokens2]).size;

  return union > 0 ? intersection / union : 0;
}

/**
 * Get remaining balance for a specific port from certificate item
 */
function getPortBalance(
  item: CertificateItem,
  port: Port
): number {
  switch (port) {
    case 'port_klang':
      return item.remaining_port_klang ?? item.port_klang_qty ?? 0;
    case 'klia':
      return item.remaining_klia ?? item.klia_qty ?? 0;
    case 'bukit_kayu_hitam':
      return item.remaining_bukit_kayu_hitam ?? item.bukit_kayu_hitam_qty ?? 0;
    default:
      return 0;
  }
}

export function MidaCertificateSelector({
  isOpen,
  onClose,
  item,
  availableCertificates,
  selectedPort,
  onConfirmMatch,
}: MidaCertificateSelectorProps) {
  // State
  const [step, setStep] = useState<'certificate' | 'item'>('certificate');
  const [selectedCertificate, setSelectedCertificate] = useState<Certificate | null>(null);
  const [selectedCertItem, setSelectedCertItem] = useState<CertificateItem | null>(null);
  const [certificateItems, setCertificateItems] = useState<CertificateItem[]>([]);
  const [isLoadingItems, setIsLoadingItems] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showMismatchWarning, setShowMismatchWarning] = useState(false);
  
  // Name similarity threshold for warning (0.6 = 60% match)
  const SIMILARITY_THRESHOLD = 0.6;

  // Reset state when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setStep('certificate');
      setSelectedCertificate(null);
      setSelectedCertItem(null);
      setCertificateItems([]);
      setSearchQuery('');
      setShowMismatchWarning(false);
    }
  }, [isOpen]);

  // Load certificate items when a certificate is selected
  useEffect(() => {
    if (selectedCertificate) {
      loadCertificateItems(selectedCertificate.id);
    }
  }, [selectedCertificate]);

  const loadCertificateItems = async (certificateId: string) => {
    setIsLoadingItems(true);
    try {
      const cert = await certificateService.getById(certificateId);
      // The items returned include remaining balances
      setCertificateItems(cert.items || []);
    } catch (error) {
      console.error('Failed to load certificate items:', error);
      setCertificateItems([]);
    } finally {
      setIsLoadingItems(false);
    }
  };

  // Filter items based on search query
  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) return certificateItems;
    const query = searchQuery.toLowerCase();
    return certificateItems.filter(
      (ci) =>
        ci.item_name.toLowerCase().includes(query) ||
        ci.line_no.toString().includes(query) ||
        ci.hs_code.includes(query)
    );
  }, [certificateItems, searchQuery]);

  // Handle certificate selection
  const handleSelectCertificate = (cert: Certificate) => {
    setSelectedCertificate(cert);
    setStep('item');
  };

  // Handle item selection
  const handleSelectItem = (certItem: CertificateItem) => {
    setSelectedCertItem(certItem);
    
    // Check for name mismatch
    const similarity = calculateSimilarity(item.description, certItem.item_name);
    if (similarity < SIMILARITY_THRESHOLD) {
      setShowMismatchWarning(true);
    } else {
      // No warning needed, proceed directly
      handleConfirm(certItem);
    }
  };

  // Handle confirmation (with or without warning)
  const handleConfirm = (certItem?: CertificateItem) => {
    const itemToUse = certItem || selectedCertItem;
    if (!selectedCertificate || !itemToUse) return;
    
    onConfirmMatch(item, selectedCertificate, itemToUse);
    onClose();
  };

  // Handle going back to certificate selection
  const handleBack = () => {
    setStep('certificate');
    setSelectedCertItem(null);
    setSearchQuery('');
    setShowMismatchWarning(false);
  };

  // Port display names
  const portDisplayNames: Record<Port, string> = {
    port_klang: 'Port Klang',
    klia: 'KLIA',
    bukit_kayu_hitam: 'BKH',
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={step === 'certificate' ? 'Select MIDA Certificate' : 'Select Certificate Item'}
      size="lg"
    >
      {/* Mismatch Warning Dialog */}
      {showMismatchWarning && selectedCertItem && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30" onClick={() => setShowMismatchWarning(false)} />
          <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6 animate-fade-in">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-yellow-100 rounded-full">
                <AlertTriangle className="w-6 h-6 text-yellow-600" />
              </div>
              <div>
                <h4 className="font-semibold text-gray-900">Name Mismatch Warning</h4>
                <p className="text-sm text-gray-600 mt-1">
                  The selected item name doesn't closely match the invoice item description.
                </p>
              </div>
            </div>
            
            <div className="bg-gray-50 rounded-lg p-3 space-y-2 text-sm mb-4">
              <div>
                <span className="text-gray-500">Invoice Item:</span>
                <p className="font-medium text-gray-900 truncate">{item.description}</p>
              </div>
              <div>
                <span className="text-gray-500">Selected MIDA Item:</span>
                <p className="font-medium text-gray-900 truncate">{selectedCertItem.item_name}</p>
              </div>
            </div>
            
            <p className="text-sm text-gray-600 mb-4">
              Are you sure you want to match this invoice item to the selected MIDA item?
            </p>
            
            <div className="flex gap-3 justify-end">
              <Button variant="outline" onClick={() => setShowMismatchWarning(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={() => handleConfirm()}>
                Proceed Anyway
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Current Item Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4">
        <div className="text-xs text-blue-600 font-medium mb-1">Invoice Item (Line {item.line_no})</div>
        <div className="text-sm font-medium text-gray-900 truncate" title={item.description}>
          {item.description}
        </div>
        <div className="flex items-center gap-4 mt-1 text-xs text-gray-600">
          <span>Qty: {formatNumber(item.quantity)} {item.uom}</span>
          {item.mida_certificate_number && (
            <span>Current: {item.mida_certificate_number} (Line {item.mida_line_no})</span>
          )}
        </div>
      </div>

      {/* Step 1: Certificate Selection */}
      {step === 'certificate' && (
        <div className="space-y-2">
          <p className="text-sm text-gray-600 mb-3">
            Select a MIDA certificate to match this item against:
          </p>
          
          {availableCertificates.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Package className="w-10 h-10 mx-auto mb-2 opacity-50" />
              <p>No certificates available for selection.</p>
              <p className="text-xs mt-1">Please select certificates before classifying the invoice.</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {availableCertificates.map((cert) => (
                <button
                  key={cert.id}
                  onClick={() => handleSelectCertificate(cert)}
                  className={cn(
                    'w-full text-left p-3 rounded-lg border transition-colors',
                    'hover:bg-purple-50 hover:border-purple-300',
                    item.mida_certificate_id === cert.id
                      ? 'bg-purple-100 border-purple-300'
                      : 'bg-white border-gray-200'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-purple-700">{cert.certificate_number}</span>
                    {item.mida_certificate_id === cert.id && (
                      <Badge variant="info" className="text-xs">Current</Badge>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {cert.model_number || 'N/A'} | {cert.item_count ?? cert.items?.length ?? 0} items | 
                    Expires: {cert.exemption_end_date}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Step 2: Item Selection */}
      {step === 'item' && selectedCertificate && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <button
                onClick={handleBack}
                className="text-sm text-blue-600 hover:text-blue-800 underline"
              >
                ← Back to certificates
              </button>
              <p className="text-sm text-gray-600 mt-1">
                Certificate: <span className="font-medium text-purple-700">{selectedCertificate.certificate_number}</span>
              </p>
            </div>
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Search by item name, line no, or HS code..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Items list */}
          {isLoadingItems ? (
            <div className="text-center py-8 text-gray-500">Loading items...</div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              {searchQuery ? 'No items match your search.' : 'No items in this certificate.'}
            </div>
          ) : (
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {filteredItems.map((certItem) => {
                const portBalance = getPortBalance(certItem, selectedPort);
                const isCurrentMatch = 
                  item.mida_certificate_id === selectedCertificate.id && 
                  item.mida_item_id === certItem.id;
                const similarity = calculateSimilarity(item.description, certItem.item_name);
                const hasLowSimilarity = similarity < SIMILARITY_THRESHOLD;
                
                return (
                  <button
                    key={certItem.id}
                    onClick={() => handleSelectItem(certItem)}
                    className={cn(
                      'w-full text-left p-3 rounded-lg border transition-colors',
                      'hover:bg-blue-50 hover:border-blue-300',
                      isCurrentMatch
                        ? 'bg-green-50 border-green-300'
                        : 'bg-white border-gray-200'
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm bg-gray-100 px-2 py-0.5 rounded">
                          Line {certItem.line_no}
                        </span>
                        {isCurrentMatch && (
                          <Check className="w-4 h-4 text-green-600" />
                        )}
                        {hasLowSimilarity && !isCurrentMatch && (
                          <span title="Low name similarity">
                            <AlertTriangle className="w-4 h-4 text-yellow-500" />
                          </span>
                        )}
                      </div>
                      <div className="text-right">
                        <div className={cn(
                          'text-sm font-semibold',
                          portBalance <= 0 ? 'text-red-600' : portBalance < item.quantity ? 'text-yellow-600' : 'text-green-600'
                        )}>
                          {formatNumber(portBalance)} {certItem.uom}
                        </div>
                        <div className="text-xs text-gray-500">
                          {portDisplayNames[selectedPort]} Balance
                        </div>
                      </div>
                    </div>
                    <div className="mt-1">
                      <p className="text-sm text-gray-900 truncate" title={certItem.item_name}>
                        {certItem.item_name}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        HS: {certItem.hs_code} | UOM: {certItem.uom}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
