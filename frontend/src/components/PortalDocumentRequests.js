/**
 * PortalDocumentRequests — Gerir pedidos de documentos do portal do cliente.
 *
 * Permite ao admin/consultor:
 * - Solicitar documentos específicos ao cliente (aparecem como "pendentes" no portal)
 * - Marcar documentos como "recebidos" (desaparecem dos pendentes no portal)
 * - Reativar pedidos (voltam a aparecer como pendentes)
 * - Remover pedidos
 *
 * Integra-se na página de detalhes do processo (ProcessDetails.js).
 */
import { useState, useEffect, useCallback } from "react";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";


import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import {
  FileUp,
  Plus,
  Check,
  CheckCircle,
  Clock,
  Trash2,
  RotateCcw,
  Loader2,
  FileText,
  FileCheck,
  Eye,
  User,
  FolderOpen,
} from "lucide-react";
import { toast } from "sonner";
import { formatDateTime } from "../lib/utils";
import {
  getPortalDocRequests,
  createPortalDocRequest,
  updatePortalDocRequest,
  deletePortalDocRequest,
} from "../services/api";

const DOCUMENT_CATEGORIES = [
  { value: "Cartao_Cidadao", label: "Cartão de Cidadão", icon: "🪪" },
  { value: "IRS", label: "Declaração de IRS", icon: "📋" },
  { value: "Recibo_Vencimento", label: "Recibo de Vencimento", icon: "💰" },
  { value: "Comprovativo_IBAN", label: "Comprovativo de IBAN", icon: "🏦" },
  { value: "Certidao_Nascimento", label: "Certidão de Nascimento", icon: "📄" },
  { value: "Atestado_Trabalho", label: "Atestado de Trabalho", icon: "🏢" },
  { value: "Mapa_Creditos", label: "Mapa de Créditos", icon: "📊" },
  { value: "Declaracao_Imposto_Renda", label: "Declaração de Imposto de Renda", icon: "📑" },
  { value: "Certidao_Permanente", label: "Certidão Permanente", icon: "📜" },
  { value: "Contrato_Promessa", label: "Contrato de Promessa", icon: "📝" },
  { value: "Plantas_Casa", label: "Plantas da Casa", icon: "🏠" },
  { value: "Certificado_Energetico", label: "Certificado Energético", icon: "⚡" },
  { value: "Outros", label: "Outro Documento", icon: "📎" },
];

/**
 * Safely extracts a string from a value that may be an object {value, label}.
 * The backend sometimes returns values as objects instead of strings,
 * which causes React error #31 when rendered directly as a child.
 */
function safeString(val, fallback = "") {
  if (val == null) return fallback;
  if (typeof val === "string") return val;
  if (typeof val === "object") return val.label || val.value || String(val);
  return String(val);
}

function getCategoryInfo(categoryKey) {
  const key = safeString(categoryKey, categoryKey);
  return DOCUMENT_CATEGORIES.find(c => c.value === key) || { value: key, label: key, icon: "📎" };
}

const SOURCE_LABELS = {
  client_portal: "Portal do Cliente",
  admin_request: "Pedido da equipa",
  auto_default: "Checklist automática",
};

function formatFileSize(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return null;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const STATUS_CONFIG = {
  REQUESTED: { label: "Pendente", color: "bg-amber-100 text-amber-800 border-amber-200", icon: Clock },
  PENDING: { label: "Pendente", color: "bg-amber-100 text-amber-800 border-amber-200", icon: Clock },
  UPLOADED: { label: "Submetido", color: "bg-blue-100 text-blue-800 border-blue-200", icon: FileCheck },
  SUBMITTED: { label: "Submetido", color: "bg-blue-100 text-blue-800 border-blue-200", icon: FileCheck },
  RECEIVED: { label: "Recebido", color: "bg-emerald-100 text-emerald-800 border-emerald-200", icon: CheckCircle },
  received: { label: "Recebido", color: "bg-emerald-100 text-emerald-800 border-emerald-200", icon: CheckCircle },
  uploaded: { label: "Submetido", color: "bg-blue-100 text-blue-800 border-blue-200", icon: FileCheck },
  submitted: { label: "Submetido", color: "bg-blue-100 text-blue-800 border-blue-200", icon: FileCheck },
  requested: { label: "Pendente", color: "bg-amber-100 text-amber-800 border-amber-200", icon: Clock },
  pending: { label: "Pendente", color: "bg-amber-100 text-amber-800 border-amber-200", icon: Clock },
};

export default function PortalDocumentRequests({ processId, processNumber, clientName, onDocumentsChange }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null); // track which action is loading
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [newDoc, setNewDoc] = useState({ categories: [], notes: "", custom_label: "" });
  const [detailsDoc, setDetailsDoc] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null); // track which action is loading
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [newDoc, setNewDoc] = useState({ categories: [], notes: "", custom_label: "" });

  const fetchDocuments = useCallback(async () => {
    if (!processId) return;
    setLoading(true);
    try {
      const res = await getPortalDocRequests(processId);
      setDocuments(res.data?.documents || []);
    } catch (err) {
      console.error("Erro ao carregar pedidos:", err);
    } finally {
      setLoading(false);
    }
  }, [processId]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Compute already-requested categories to filter from dropdown
  // Include RECEIVED — if a doc was already received, no need to request it again
  const requestedCategoryKeys = documents
    .filter(d => {
      const s = safeString(d.status, '').toUpperCase();
      return ["REQUESTED", "PENDING", "UPLOADED", "SUBMITTED", "RECEIVED"].includes(s);
    })
    .map(d => safeString(d.category, d.category));

  const availableCategories = DOCUMENT_CATEGORIES.filter(
    cat => !requestedCategoryKeys.includes(cat.value)
  );

  const handleAddDocument = async () => {
    if (newDoc.categories.length === 0) {
      toast.error("Selecione pelo menos uma categoria");
      return;
    }
    setActionLoading("add");
    try {
      // Create a request for each selected category
      const promises = newDoc.categories.map(category =>
        createPortalDocRequest(processId, {
          category,
          notes: newDoc.notes || undefined,
          custom_label: category === "Outros" ? (newDoc.custom_label || undefined) : undefined,
        })
      );
      await Promise.all(promises);
      toast.success(
        newDoc.categories.length === 1
          ? "Documento solicitado com sucesso!"
          : `${newDoc.categories.length} documentos solicitados com sucesso!`
      );
      setNewDoc({ categories: [], notes: "", custom_label: "" });
      setShowAddDialog(false);
      fetchDocuments();
      // PACOTE BV (Fix 1): notificar o parent para refrescar a checklist/documentos
      if (onDocumentsChange) onDocumentsChange();
    } catch (err) {
      toast.error(extractErrorMessage(err.response?.data?.detail, "Erro ao solicitar documento"));
    } finally {
      setActionLoading(null);
    }
  };

  const handleMarkReceived = async (docId) => {
    setActionLoading(docId);
    try {
      await updatePortalDocRequest(processId, docId, { status: "RECEIVED" });
      toast.success("Documento marcado como recebido!");
      setDetailsDoc(null);
      fetchDocuments();
      // PACOTE BV (Fix 1): notificar o parent para refrescar a checklist/documentos
      if (onDocumentsChange) onDocumentsChange();
    } catch {
      toast.error("Erro ao atualizar estado");
    } finally {
      setActionLoading(null);
    }
  };

  const handleMarkPending = async (docId) => {
    setActionLoading(docId);
    try {
      await updatePortalDocRequest(processId, docId, { status: "REQUESTED" });
      toast.success("Pedido reativado com sucesso!");
      setDetailsDoc(null);
      fetchDocuments();
      // PACOTE BV (Fix 1): notificar o parent para refrescar a checklist/documentos
      if (onDocumentsChange) onDocumentsChange();
    } catch {
      toast.error("Erro ao atualizar estado");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (docId) => {
    if (!window.confirm("Tem a certeza que deseja remover este pedido?")) return;
    setActionLoading(docId);
    try {
      await deletePortalDocRequest(processId, docId);
      toast.success("Pedido recusado e removido");
      setDetailsDoc(null);
      fetchDocuments();
      // PACOTE BV (Fix 1): notificar o parent para refrescar a checklist/documentos
      if (onDocumentsChange) onDocumentsChange();
    } catch {
      toast.error("Erro ao remover pedido");
    } finally {
      setActionLoading(null);
    }
  };

  // Group documents by status
  const pendingDocs = documents.filter(d => {
    const s = safeString(d.status, '').toUpperCase();
    return ["REQUESTED", "PENDING"].includes(s);
  });
  const uploadedDocs = documents.filter(d => {
    const s = safeString(d.status, '').toUpperCase();
    return ["UPLOADED", "SUBMITTED"].includes(s);
  });
  const receivedDocs = documents.filter(d => {
    const s = safeString(d.status, '').toUpperCase();
    return s === "RECEIVED";
  });

  const pendingCount = pendingDocs.length;
  const uploadedCount = uploadedDocs.length;
  const receivedCount = receivedDocs.length;

  return (
    <>
    <Card className="border-teal-200">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-teal-100 rounded-lg">
              <FileUp className="h-4 w-4 text-teal-600" />
            </div>
            <div>
              <CardTitle className="text-sm font-semibold">Documentos do Portal</CardTitle>
              <p className="text-xs text-muted-foreground">
                Gerir documentos solicitados ao cliente
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {pendingCount > 0 && (
              <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200">
                {pendingCount} pendente{pendingCount !== 1 ? "s" : ""}
              </Badge>
            )}
            {uploadedCount > 0 && (
              <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-200">
                {uploadedCount} submetido{uploadedCount !== 1 ? "s" : ""}
              </Badge>
            )}
            {receivedCount > 0 && (
              <Badge variant="outline" className="text-xs bg-emerald-50 text-emerald-700 border-emerald-200">
                {receivedCount} recebido{receivedCount !== 1 ? "s" : ""}
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Add new document button */}
        <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
          <DialogTrigger asChild>
            <Button
              size="sm"
              className="w-full bg-teal-600 hover:bg-teal-700 text-white gap-2"
            >
              <Plus className="h-4 w-4" />
              Solicitar Documento ao Cliente
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Solicitar Documento</DialogTitle>
              <DialogDescription>
                Este pedido aparecerá no portal do cliente como pendente.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>Categorias * <span className="text-muted-foreground font-normal">(selecione uma ou mais)</span></Label>
                <div className="border rounded-md max-h-64 overflow-y-auto p-2 space-y-1">
                  {availableCategories.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      Todos os documentos já foram solicitados.
                    </p>
                  ) : (
                    availableCategories.map(cat => {
                      const isSelected = newDoc.categories.includes(cat.value);
                      return (
                        <label
                          key={cat.value}
                          className={`flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer transition-colors ${
                            isSelected ? 'bg-teal-50 border border-teal-200' : 'hover:bg-gray-50 border border-transparent'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={(e) => {
                              setNewDoc(prev => ({
                                ...prev,
                                categories: e.target.checked
                                  ? [...prev.categories, cat.value]
                                  : prev.categories.filter(c => c !== cat.value),
                              }));
                            }}
                            className="rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                          />
                          <span className="text-lg">{cat.icon}</span>
                          <span className="text-sm">{cat.label}</span>
                        </label>
                      );
                    })
                  )}
                </div>
                {newDoc.categories.length > 0 && (
                  <p className="text-xs text-teal-600">
                    {newDoc.categories.length} documento{newDoc.categories.length !== 1 ? 's' : ''} selecionado{newDoc.categories.length !== 1 ? 's' : ''}
                  </p>
                )}
              </div>
              {newDoc.categories.includes("Outros") && (
                <div className="space-y-2">
                  <Label>Descrição do documento</Label>
                  <Input
                    placeholder="Ex: Certidão de Casamento..."
                    value={newDoc.custom_label}
                    onChange={(e) => setNewDoc(prev => ({ ...prev, custom_label: e.target.value }))}
                  />
                </div>
              )}
              <div className="space-y-2">
                <Label>Notas (opcional)</Label>
                <Textarea
                  placeholder="Instruções adicionais para o cliente..."
                  value={newDoc.notes}
                  onChange={(e) => setNewDoc(prev => ({ ...prev, notes: e.target.value }))}
                  rows={3}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowAddDialog(false)}>
                Cancelar
              </Button>
              <Button
                onClick={handleAddDocument}
                disabled={newDoc.categories.length === 0 || actionLoading === "add"}
                className="bg-teal-600 hover:bg-teal-700 text-white"
              >
                {actionLoading === "add" ? (
                  <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> A criar...</>
                ) : (
                  <><Plus className="h-4 w-4 mr-1" /> Solicitar{newDoc.categories.length > 1 ? ` (${newDoc.categories.length})` : ''}</>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Document lists */}
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center py-6">
            <FileText className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">
              Nenhum documento solicitado via portal.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Clique em "Solicitar Documento" para começar.
            </p>
          </div>
        ) : (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {/* Pending */}
            {pendingDocs.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-amber-700 uppercase tracking-wider flex items-center gap-1.5">
                  <Clock className="h-3 w-3" />
                  Pendentes ({pendingDocs.length})
                </p>
                {pendingDocs.map(doc => (
                  <DocItem
                    key={doc.id}
                    doc={doc}
                    loading={actionLoading === doc.id}
                    onViewDetails={() => setDetailsDoc(doc)}
                    onMarkReceived={() => handleMarkReceived(doc.id)}
                    onDelete={() => handleDelete(doc.id)}
                  />
                ))}
              </div>
            )}

            {/* Uploaded by client */}
            {uploadedDocs.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-blue-700 uppercase tracking-wider flex items-center gap-1.5">
                  <FileCheck className="h-3 w-3" />
                  Submetidos pelo Cliente ({uploadedDocs.length})
                </p>
                {uploadedDocs.map(doc => (
                  <DocItem
                    key={doc.id}
                    doc={doc}
                    loading={actionLoading === doc.id}
                    onViewDetails={() => setDetailsDoc(doc)}
                    onMarkReceived={() => handleMarkReceived(doc.id)}
                    onDelete={() => handleDelete(doc.id)}
                  />
                ))}
              </div>
            )}

            {/* Received */}
            {receivedDocs.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wider flex items-center gap-1.5">
                  <CheckCircle className="h-3 w-3" />
                  Recebidos ({receivedDocs.length})
                </p>
                {receivedDocs.map(doc => (
                  <DocItem
                    key={doc.id}
                    doc={doc}
                    loading={actionLoading === doc.id}
                    onViewDetails={() => setDetailsDoc(doc)}
                    onMarkPending={() => handleMarkPending(doc.id)}
                    onDelete={() => handleDelete(doc.id)}
                    isReceived
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>

      <RequestDetailsDialog
        doc={detailsDoc}
        open={Boolean(detailsDoc)}
        onOpenChange={(open) => { if (!open) setDetailsDoc(null); }}
        processId={processId}
        processNumber={processNumber}
        clientName={clientName}
        loading={detailsDoc ? actionLoading === detailsDoc.id : false}
        onAccept={() => detailsDoc && handleMarkReceived(detailsDoc.id)}
        onReject={() => detailsDoc && handleDelete(detailsDoc.id)}
        onReactivate={() => detailsDoc && handleMarkPending(detailsDoc.id)}
      />
    </>
  );
}

// ── Individual document item ──────────────────────────────────────
function DocItem({ doc, loading, onViewDetails, onMarkReceived, onMarkPending, onDelete, isReceived }) {
  const catInfo = getCategoryInfo(doc.category);
  const statusKey = safeString(doc.status, 'REQUESTED').toUpperCase();
  const statusCfg = STATUS_CONFIG[statusKey] || STATUS_CONFIG[safeString(doc.status)] || STATUS_CONFIG.REQUESTED;
  const StatusIcon = statusCfg.icon;

  const displayName = safeString(doc.custom_label) || catInfo.label;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onViewDetails}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onViewDetails?.();
        }
      }}
      className={`flex items-center gap-2.5 p-2.5 rounded-lg border transition-colors cursor-pointer ${
        isReceived
          ? "bg-emerald-50/50 border-emerald-100"
          : "bg-background border-border hover:border-muted-foreground/30"
      }`}
      data-testid={`portal-request-row-${doc.id}`}
    >
      <span className="text-lg flex-shrink-0">{catInfo.icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{displayName}</p>
        <div className="flex items-center gap-2 mt-0.5">
          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${statusCfg.color}`}>
            <StatusIcon className="h-2.5 w-2.5" />
            {statusCfg.label}
          </span>
          {doc.notes && (
            <span className="text-[10px] text-muted-foreground truncate">{safeString(doc.notes)}</span>
          )}
          {doc.original_filename && (
            <span className="text-[10px] text-primary truncate">📎 {safeString(doc.original_filename)}</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : (
          <>
            <button
              type="button"
              onClick={onViewDetails}
              className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              title="Ver detalhes"
              data-testid={`portal-request-details-${doc.id}`}
            >
              <Eye className="h-4 w-4" />
            </button>
            {!isReceived ? (
              <>
                <button
                  type="button"
                  onClick={onMarkReceived}
                  className="p-1.5 rounded-md hover:bg-accent text-primary transition-colors"
                  title="Aceitar / marcar como recebido"
                >
                  <Check className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={onDelete}
                  className="p-1.5 rounded-md hover:bg-destructive/10 text-destructive transition-colors"
                  title="Recusar / remover pedido"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={onMarkPending}
                  className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  title="Voltar a solicitar"
                >
                  <RotateCcw className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={onDelete}
                  className="p-1.5 rounded-md hover:bg-destructive/10 text-destructive transition-colors"
                  title="Remover"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function DetailRow({ label, children }) {
  if (children == null || children === "" || children === "-") return null;
  return (
    <div className="grid grid-cols-3 gap-2 py-2 border-b border-border last:border-0">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="col-span-2 text-sm text-foreground break-words">{children}</dd>
    </div>
  );
}

function RequestDetailsDialog({
  doc,
  open,
  onOpenChange,
  processId,
  processNumber,
  clientName,
  loading,
  onAccept,
  onReject,
  onReactivate,
}) {
  if (!doc) return null;

  const catInfo = getCategoryInfo(doc.category);
  const statusKey = safeString(doc.status, "REQUESTED").toUpperCase();
  const statusCfg = STATUS_CONFIG[statusKey] || STATUS_CONFIG[safeString(doc.status)] || STATUS_CONFIG.REQUESTED;
  const StatusIcon = statusCfg.icon;
  const displayName = safeString(doc.custom_label) || catInfo.label;
  const isReceived = statusKey === "RECEIVED";
  const sourceLabel = SOURCE_LABELS[safeString(doc.source)] || safeString(doc.source, null);
  const attachedFiles = Array.isArray(doc.attached_files) ? doc.attached_files : [];
  const fileSize = formatFileSize(doc.file_size);
  const processLabel = processNumber
    ? `#${processNumber}`
    : (safeString(doc.process_id) || processId || "—");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" title="Detalhes do pedido" description="Informação completa do pedido do portal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span>{catInfo.icon}</span>
            {displayName}
          </DialogTitle>
          <DialogDescription>
            Reveja o contexto do pedido antes de aceitar ou recusar.
          </DialogDescription>
        </DialogHeader>

        <dl className="space-y-0">
          <DetailRow label="Estado">
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${statusCfg.color}`}>
              <StatusIcon className="h-3 w-3" />
              {statusCfg.label}
            </span>
          </DetailRow>
          <DetailRow label="Tipo de documento">{catInfo.label}</DetailRow>
          {safeString(doc.custom_label) ? (
            <DetailRow label="Descrição">{safeString(doc.custom_label)}</DetailRow>
          ) : null}
          <DetailRow label="Processo associado">{processLabel}</DetailRow>
          {clientName ? (
            <DetailRow label="Cliente">
              <span className="inline-flex items-center gap-1">
                <User className="h-3.5 w-3.5 text-muted-foreground" />
                {clientName}
              </span>
            </DetailRow>
          ) : null}
          <DetailRow label="Origem">{sourceLabel}</DetailRow>
          <DetailRow label="Mensagem / notas">
            {safeString(doc.notes) || (
              <span className="text-muted-foreground italic">Sem mensagem</span>
            )}
          </DetailRow>
          <DetailRow label="Ficheiro">{safeString(doc.original_filename || doc.filename)}</DetailRow>
          <DetailRow label="Tipo MIME">{safeString(doc.content_type)}</DetailRow>
          <DetailRow label="Tamanho">{fileSize}</DetailRow>
          <DetailRow label="Pedido por">{safeString(doc.requested_by_name)}</DetailRow>
          <DetailRow label="Criado em">{doc.created_at ? formatDateTime(doc.created_at) : null}</DetailRow>
          <DetailRow label="Submetido em">{doc.uploaded_at ? formatDateTime(doc.uploaded_at) : null}</DetailRow>
          <DetailRow label="Atualizado em">{doc.updated_at ? formatDateTime(doc.updated_at) : null}</DetailRow>
          {attachedFiles.length > 0 ? (
            <DetailRow label="Ficheiros anexados">
              <ul className="space-y-1">
                {attachedFiles.map((f, idx) => (
                  <li key={f.file_id || f.s3_path || idx} className="flex items-center gap-1.5 text-xs">
                    <FolderOpen className="h-3 w-3 text-muted-foreground shrink-0" />
                    <span className="truncate">{safeString(f.original_filename || f.filename, "Ficheiro")}</span>
                    {f.uploaded_at ? (
                      <span className="text-muted-foreground shrink-0">
                        {formatDateTime(f.uploaded_at)}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </DetailRow>
          ) : null}
        </dl>

        <DialogFooter className="gap-2 sm:gap-2">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : isReceived ? (
            <>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Fechar
              </Button>
              <Button type="button" variant="outline" onClick={onReactivate}>
                <RotateCcw className="h-4 w-4" />
                Voltar a solicitar
              </Button>
              <Button type="button" variant="destructive" onClick={onReject}>
                <Trash2 className="h-4 w-4" />
                Recusar
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Fechar
              </Button>
              <Button type="button" variant="destructive" onClick={onReject}>
                <Trash2 className="h-4 w-4" />
                Recusar
              </Button>
              <Button type="button" onClick={onAccept}>
                <CheckCircle className="h-4 w-4" />
                Aceitar
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
