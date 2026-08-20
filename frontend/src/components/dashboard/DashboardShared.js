/**
 * Componentes partilhados para Dashboards (Consultor e Mediador)
 * Elimina código duplicado entre ConsultorDashboard e MediadorDashboard
 */
import { useState, useEffect, useMemo } from "react";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import {
  FileText, Search, ArrowRight, Calendar, Sparkles, FolderOpen
} from "lucide-react";
import { toast } from "sonner";
import { differenceInDays } from "date-fns";
import { safeDateStr, safeParseISO, formatDate as formatDateUtil, formatDateTime } from "../../lib/utils";
import {
  getProcesses, getStats, getUpcomingExpiries, getWorkflowStatuses,
  createDocumentExpiry, getClientS3Files, analyzeOneDriveDocument,
  getProcessAiAnalysis, generateProcessAiAnalysis, getProcessAiAgentAnalysis,
} from "../../services/api";
import { StatCard as SharedStatCard } from "../shared/StatCard";
import { StatusBadge as SharedStatusBadge } from "../shared/StatusBadge";
import { Spinner, LoadingSpinner as SharedLoadingSpinner } from "../ui/Spinner";
import { Skeleton } from "../ui/skeleton";
import { EmptyState } from "../ui/EmptyState";
import { sanitizeHtml } from "../../utils/sanitize";
import { markdownToHtml } from "../../utils/markdown";
import { findProcessBySelectValue, resolveProcessId } from "../../utils/processAuditHistory";

// ====================================================================
// HELPERS
// ====================================================================

/**
 * Safely extracts a string label from a value that may be an object {value, label}.
 * The backend sometimes returns workflow status labels as objects instead of strings,
 * which causes React error #31 when rendered directly as a child.
 */
export const safeLabel = (label, fallback = "") => {
  if (label == null) return fallback;
  if (typeof label === "string") return label;
  if (typeof label === "object") return label.label || label.value || String(label);
  return String(label);
};

/**
 * Safely converts any value to a string for React rendering.
 * Handles objects like {value: "x", label: "Y"} that the backend sometimes returns.
 * Prevents React error #31 (objects as React children).
 */
export const safeString = (val, fallback = "") => {
  if (val == null) return fallback;
  if (typeof val === "string") return val;
  if (typeof val === "object") return val.label || val.value || String(val);
  return String(val);
};

/**
 * Safely converts any value to a valid number.
 * Returns fallback (default 0) for NaN results.
 */
export const safeNumber = (val, fallback = 0) => {
  const n = Number(val);
  return isNaN(n) ? fallback : n;
};

// ====================================================================
// CONSTANTES PARTILHADAS
// ====================================================================
export const TYPE_LABELS = {
  credito: "Crédito",
  imobiliaria: "Imobiliária",
  ambos: "Crédito + Imobiliária",
};

export const DOCUMENT_TYPES_CONSULTOR = [
  { type: "cc", name: "Cartão de Cidadão" },
  { type: "passaporte", name: "Passaporte" },
  { type: "carta_conducao", name: "Carta de Condução" },
  { type: "contrato_trabalho", name: "Contrato de Trabalho" },
  { type: "declaracao_irs", name: "Declaração de IRS" },
  { type: "comprovativo_morada", name: "Comprovativo de Morada" },
  { type: "outro", name: "Outro" },
];

export const DOCUMENT_TYPES_MEDIADOR = [
  { type: "cc", name: "Cartão de Cidadão" },
  { type: "passaporte", name: "Passaporte" },
  { type: "comprovativo_iban", name: "Comprovativo IBAN" },
  { type: "recibo_vencimento", name: "Recibo de Vencimento" },
  { type: "declaracao_irs", name: "Declaração de IRS" },
  { type: "nota_liquidacao", name: "Nota de Liquidação IRS" },
  { type: "contrato_trabalho", name: "Contrato de Trabalho" },
  { type: "mapa_responsabilidades", name: "Mapa Responsabilidades BP" },
  { type: "outro", name: "Outro" },
];

// ====================================================================
// FUNÇÕES UTILITÁRIAS
// ====================================================================

/**
 * Obtém a cor e label para urgência de expiração
 */
export const getExpiryUrgency = (expiryDate) => {
  try {
    const safeStr = safeDateStr(expiryDate);
    if (!safeStr) return { color: "text-gray-600 bg-gray-50", label: "N/D" };
    const days = differenceInDays(safeParseISO(safeStr) || new Date(), new Date());
    if (days < 0) return { color: "text-red-600 bg-red-50", label: "Expirado" };
    if (days <= 7) return { color: "text-red-600 bg-red-50", label: `${days} dias` };
    if (days <= 30) return { color: "text-orange-600 bg-orange-50", label: `${days} dias` };
    return { color: "text-green-600 bg-green-50", label: `${days} dias` };
  } catch {
    return { color: "text-gray-600 bg-gray-50", label: "N/D" };
  }
};

/**
 * Formata data para exibição — seguro em Safari/iOS
 */
export const formatDate = (dateString) => {
  return formatDateUtil(dateString);
};

// ====================================================================
// COMPONENTES PARTILHADOS
// ====================================================================

/** @deprecated Import from `components/shared/StatCard` — re-export for back-compat */
export const StatCard = SharedStatCard;

/** @deprecated Import from `components/shared/StatusBadge` — re-export for back-compat */
export const StatusBadge = SharedStatusBadge;

/**
 * Filtros de pesquisa e estado
 */
export const SearchFilters = ({ searchTerm, setSearchTerm, statusFilter, setStatusFilter, workflowStatuses }) => (
  <div className="flex flex-col sm:flex-row gap-2">
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      <Input
        placeholder="Pesquisar..."
        className="pl-10 w-full sm:w-64"
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />
    </div>
    <Select value={statusFilter} onValueChange={setStatusFilter}>
      <SelectTrigger className="w-full sm:w-40">
        <SelectValue placeholder="Estado" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">Todos</SelectItem>
        {workflowStatuses.map((s) => (
          <SelectItem key={s.name} value={s.name}>{safeLabel(s.label)}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  </div>
);

/**
 * Tabela de processos/clientes
 */
export const ProcessTable = ({ processes, columns, renderRow, emptyMessage = "Nenhum processo encontrado" }) => (
  <div className="rounded-md border overflow-x-auto">
    <Table>
      <TableHeader>
        <TableRow>
          {columns.map((col) => (
            <TableHead key={col.key} className={col.className}>{col.label}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {processes.length === 0 ? (
          <TableRow>
            <TableCell colSpan={columns.length} className="text-center py-8 text-muted-foreground">
              {emptyMessage}
            </TableCell>
          </TableRow>
        ) : (
          processes.map((process) => renderRow(process))
        )}
      </TableBody>
    </Table>
  </div>
);

/**
 * Lista de documentos a expirar
 */
export const ExpiringDocumentsList = ({ expiries, onNavigate }) => {
  if (expiries.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Calendar className="h-12 w-12 mx-auto mb-4 opacity-50" />
        <p>Nenhum documento a expirar nos próximos 60 dias</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {expiries.map((doc) => {
        const urgency = getExpiryUrgency(doc.expiry_date);
        return (
          <div key={doc.id} className={`flex items-center justify-between p-4 rounded-lg ${urgency.color}`}>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <p className="font-medium">{safeString(doc.document_name)}</p>
                <Badge variant="outline" className="text-xs">{safeString(doc.document_type)}</Badge>
              </div>
              <p className="text-sm">
                Cliente: {safeString(doc.client_name)} • {safeString(doc.client_email)}
              </p>
              <p className="text-sm">
                Expira: {formatDate(doc.expiry_date)}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="font-mono">
                {urgency.label}
              </Badge>
              <Button variant="ghost" size="icon" onClick={() => onNavigate(doc.process_id)}>
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
};

/**
 * Diálogo para adicionar data de validade
 */
export const AddExpiryDialog = ({ isOpen, onClose, formData, setFormData, onSubmit, loading, documentTypes }) => (
  <Dialog open={isOpen} onOpenChange={onClose}>
    <DialogContent className="sm:max-w-md w-[calc(100vw-2rem)]">
      <DialogHeader>
        <DialogTitle>Adicionar Data de Validade de Documento</DialogTitle>
        <DialogDescription>
          Adicione uma data de validade para monitorização.
        </DialogDescription>
      </DialogHeader>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label>Tipo de Documento</Label>
          <Select
            value={formData.document_type}
            onValueChange={(v) => setFormData(prev => ({ ...prev, document_type: v }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Selecione" />
            </SelectTrigger>
            <SelectContent>
              {documentTypes.map((dt) => (
                <SelectItem key={dt.type} value={dt.type}>{dt.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Nome do Documento</Label>
          <Input
            value={formData.document_name}
            onChange={(e) => setFormData(prev => ({ ...prev, document_name: e.target.value }))}
            placeholder="Ex: CC João Silva"
            required
          />
        </div>
        <div className="space-y-2">
          <Label>Data de Validade</Label>
          <Input
            type="date"
            value={formData.expiry_date}
            onChange={(e) => setFormData(prev => ({ ...prev, expiry_date: e.target.value }))}
            required
          />
        </div>
        <div className="space-y-2">
          <Label>Notas (opcional)</Label>
          <Input
            value={formData.notes}
            onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
            placeholder="Notas adicionais..."
          />
        </div>
        <DialogFooter>
          <Button type="submit" disabled={loading}>
            {loading ? <Spinner size="sm" /> : "Adicionar"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
);

/** @deprecated Import from `components/ui/Spinner` — re-export for back-compat */
export const LoadingSpinner = SharedLoadingSpinner;

function formatAgentAnalysisMarkdown(data) {
  if (!data || typeof data !== "object") return "";
  const recs = Array.isArray(data.recommendations) ? data.recommendations : [];
  const metrics = data.metrics || {};
  const lines = [
    `# Análise IA — ${data.client_name || "Processo"}`,
    "",
    `**Estado:** ${data.status || "—"}`,
    `**Nível de risco:** ${data.risk_level || "—"}`,
    `**Dias no sistema:** ${metrics.days_in_system ?? "—"}`,
    `**Dias sem atualização:** ${metrics.days_since_update ?? "—"}`,
  ];
  if (metrics.estimated_completion) {
    lines.push(`**Conclusão estimada:** ${metrics.estimated_completion}`);
  }
  if (recs.length) {
    lines.push("", "## Recomendações");
    recs.forEach((item) => {
      const action = item.action ? ` — ${item.action}` : "";
      lines.push(`- **${item.type || "nota"}:** ${item.message || ""}${action}`);
    });
  } else {
    lines.push("", "Sem recomendações urgentes neste momento.");
  }
  return lines.join("\n");
}

/**
 * Tab de análise IA - seleção de cliente dispara GET/POST da análise.
 */
export const AIAnalysisTab = ({
  processes,
  selectedClient,
  onSelectClient,
  oneDriveFiles,
  isAnalyzing,
  isLoadingFiles,
  onAnalyzeDocument,
  analysisResult,
  aiSummary,
  aiAnalysisDate,
  aiError,
  onRefreshAnalysis,
}) => (
  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="dashboard-ai-analysis">
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          Análise IA
        </CardTitle>
        <CardDescription>
          Selecione um cliente para gerar (ou carregar) a análise do processo
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="dashboard-ai-client">Selecione um cliente</Label>
            <Select
              value={selectedClient?.id || undefined}
              onValueChange={(value) => {
                const process = findProcessBySelectValue(processes, value);
                onSelectClient(process, value);
              }}
            >
              <SelectTrigger data-testid="dashboard-ai-client-select" id="dashboard-ai-client">
                <SelectValue placeholder="Escolha um cliente" />
              </SelectTrigger>
              <SelectContent>
                {(processes || []).filter((p) => p?.id).map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {safeString(p.client_name) || safeString(p.process_number) || p.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedClient && (
            <div className="p-4 bg-muted/50 rounded-lg">
              <p className="font-medium mb-1">Cliente: {safeString(selectedClient.client_name)}</p>
              {selectedClient.process_number && (
                <p className="text-sm text-muted-foreground">Processo #{safeString(selectedClient.process_number)}</p>
              )}
              {aiAnalysisDate && (
                <p className="text-xs text-muted-foreground mt-1">
                  Última análise: {formatDateTime(aiAnalysisDate)}
                </p>
              )}
            </div>
          )}

          {isAnalyzing && (
            <div className="space-y-3" data-testid="dashboard-ai-loading" role="status" aria-label="A carregar análise IA">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner size="sm" className="text-primary" />
                A carregar análise IA...
              </div>
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-24 w-full" />
            </div>
          )}

          {!isAnalyzing && aiError && (
            <p className="text-sm text-destructive">{aiError}</p>
          )}

          {!isAnalyzing && aiSummary && (
            <div
              className="p-4 rounded-lg border border-border bg-muted/30 max-h-[420px] overflow-y-auto"
              data-testid="dashboard-ai-result"
            >
              <div
                className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed"
                dangerouslySetInnerHTML={{ __html: sanitizeHtml(markdownToHtml(aiSummary)) }}
              />
              {onRefreshAnalysis && (
                <Button variant="outline" size="sm" className="mt-3" onClick={onRefreshAnalysis}>
                  Atualizar análise
                </Button>
              )}
            </div>
          )}

          {!selectedClient && !isAnalyzing && (
            <EmptyState
              icon={Sparkles}
              title="Sem cliente selecionado"
              message="Escolha um cliente no seletor para ver a análise IA."
              className="py-8"
            />
          )}

          {analysisResult && !isAnalyzing && (
            <div className="p-4 bg-muted/50 rounded-lg border border-border">
              <p className="font-medium mb-2">
                Dados extraídos: {analysisResult.fileName}
              </p>
              <div className="text-sm space-y-1">
                {analysisResult.mapped?.financial_data && (
                  <>
                    <p><strong>Salário Líquido:</strong> €{safeString(analysisResult.mapped.financial_data.monthly_income, "N/D")}</p>
                    <p><strong>Empresa:</strong> {safeString(analysisResult.mapped.financial_data.employer_name, "N/D")}</p>
                    <p><strong>Tipo Contrato:</strong> {safeString(analysisResult.mapped.financial_data.employment_type, "N/D")}</p>
                  </>
                )}
                {analysisResult.mapped?.personal_data && (
                  <>
                    <p><strong>NIF:</strong> {safeString(analysisResult.mapped.personal_data.nif, "N/D")}</p>
                    <p><strong>Data Nascimento:</strong> {safeString(analysisResult.mapped.personal_data.birth_date, "N/D")}</p>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>

    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <FolderOpen className="h-5 w-5" />
          Ficheiros do cliente
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!selectedClient ? (
          <EmptyState
            icon={FolderOpen}
            message="Selecione um cliente para ver os ficheiros"
            className="py-8"
          />
        ) : isLoadingFiles ? (
          <div className="space-y-2" role="status" aria-label="A carregar ficheiros">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : oneDriveFiles.length === 0 ? (
          <EmptyState message="Nenhum ficheiro disponível nesta pasta" className="py-8" />
        ) : (
          <div className="space-y-2">
            {oneDriveFiles.map((file) => {
              const fileKey = file.path || file.id || file.name;
              const fileName = file.name || file.filename || file.path;
              return (
                <div key={fileKey} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg gap-2">
                  <div className="flex items-center gap-3 min-w-0">
                    <FileText className="h-5 w-5 text-muted-foreground shrink-0" />
                    <span className="text-sm truncate">{fileName}</span>
                  </div>
                  <Select onValueChange={(docType) => onAnalyzeDocument(fileName, docType)}>
                    <SelectTrigger className="w-40 shrink-0">
                      <SelectValue placeholder="Analisar como..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cc">Cartão Cidadão</SelectItem>
                      <SelectItem value="recibo_vencimento">Recibo Vencimento</SelectItem>
                      <SelectItem value="irs">Declaração IRS</SelectItem>
                      <SelectItem value="outro">Outro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              );
            })}
            {isAnalyzing && (
              <div className="flex items-center justify-center py-4 gap-2">
                <Spinner size="sm" className="text-primary" />
                <span>A analisar documento...</span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  </div>
);

// ====================================================================
// HOOK PERSONALIZADO PARA DADOS DO DASHBOARD
// ====================================================================

/**
 * Hook personalizado para gerir estado do dashboard
 */
export const useDashboardData = () => {
  const [processes, setProcesses] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [upcomingExpiries, setUpcomingExpiries] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [processesRes, statsRes, expiriesRes, statusesRes] = await Promise.all([
        getProcesses({ view_mode: "all", size: 100 }),
        getStats(),
        getUpcomingExpiries(60).catch(() => ({ data: [] })),
        getWorkflowStatuses()
      ]);
      // processes API returns paginated response: { items: [...], total, page, size, pages }
      const processesData = processesRes.data;
      setProcesses(Array.isArray(processesData) ? processesData : (processesData?.items || []));
      setStats(statsRes.data || {});
      setUpcomingExpiries(Array.isArray(expiriesRes.data) ? expiriesRes.data : []);
      setWorkflowStatuses(Array.isArray(statusesRes.data) ? statusesRes.data : []);
    } catch (error) {
      console.error("Error fetching data:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  };

  const filteredProcesses = useMemo(() => {
    if (!Array.isArray(processes)) return [];
    return processes.filter(process => {
      const matchesSearch =
        (process.client_name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
        (process.client_email || "").toLowerCase().includes(searchTerm.toLowerCase());
      const matchesStatus = statusFilter === "all" || process.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [processes, searchTerm, statusFilter]);

  return {
    processes,
    filteredProcesses,
    workflowStatuses,
    upcomingExpiries,
    stats,
    loading,
    searchTerm,
    setSearchTerm,
    statusFilter,
    setStatusFilter,
    fetchData
  };
};

/**
 * Hook para gestão de documentos e análise IA
 */
export const useDocumentManagement = (fetchData) => {
  const [isAddExpiryOpen, setIsAddExpiryOpen] = useState(false);
  const [selectedProcessId, setSelectedProcessId] = useState("");
  const [expiryFormData, setExpiryFormData] = useState({
    document_type: "",
    document_name: "",
    expiry_date: "",
    notes: ""
  });
  const [formLoading, setFormLoading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [oneDriveFiles, setOneDriveFiles] = useState([]);
  const [selectedClient, setSelectedClient] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [aiSummary, setAiSummary] = useState(null);
  const [aiAnalysisDate, setAiAnalysisDate] = useState(null);
  const [aiError, setAiError] = useState(null);

  const handleAddExpiry = async (e) => {
    e.preventDefault();
    if (!selectedProcessId) return;

    setFormLoading(true);
    try {
      await createDocumentExpiry({
        process_id: selectedProcessId,
        ...expiryFormData
      });
      toast.success("Data de documento adicionada");
      setIsAddExpiryOpen(false);
      setExpiryFormData({ document_type: "", document_name: "", expiry_date: "", notes: "" });
      fetchData();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao adicionar"));
    } finally {
      setFormLoading(false);
    }
  };

  const openAddExpiryDialog = (processId) => {
    setSelectedProcessId(processId);
    setIsAddExpiryOpen(true);
  };

  const loadClientFiles = async (process) => {
    setIsLoadingFiles(true);
    try {
      const processId = resolveProcessId(process);
      if (!processId) {
        setOneDriveFiles([]);
        return;
      }
      const res = await getClientS3Files(processId);
      const allFiles = [];
      if (res.data?.files) {
        Object.values(res.data.files).forEach(categoryFiles => {
          if (Array.isArray(categoryFiles)) {
            allFiles.push(...categoryFiles);
          }
        });
      }
      setOneDriveFiles(allFiles);
    } catch (error) {
      console.error("Error loading S3 files:", error);
      setOneDriveFiles([]);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const fetchProcessAiAnalysis = async (process, { force = false } = {}) => {
    const processId = resolveProcessId(process);
    if (!processId) return;

    setIsAnalyzing(true);
    setAiError(null);
    if (!force) setAiSummary(null);

    try {
      let summary = "";
      let date = null;

      if (!force) {
        try {
          const cached = await getProcessAiAnalysis(processId);
          summary = cached.data?.ai_executive_summary || "";
          date = cached.data?.ai_analysis_date || null;
        } catch {
          summary = "";
        }
      }

      if (!summary || force) {
        try {
          const generated = await generateProcessAiAnalysis(processId, force);
          summary = generated.data?.ai_executive_summary || summary;
          date = generated.data?.ai_analysis_date || date;
        } catch (genErr) {
          const status = genErr.response?.status;
          if (status !== 503 && status !== 409) {
            throw genErr;
          }
        }
      }

      if (!summary) {
        const agent = await getProcessAiAgentAnalysis(processId);
        summary = formatAgentAnalysisMarkdown(agent.data);
        date = agent.data?.analyzed_at || date;
      }

      setAiSummary(summary || "");
      setAiAnalysisDate(date);
      if (!summary) {
        setAiError("A IA não devolveu conteúdo para este processo.");
      }
    } catch (error) {
      const msg = extractErrorMessage(
        error.response?.data?.detail,
        "Erro ao gerar análise IA",
      );
      setAiError(msg);
      toast.error(msg);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const loadClientAndAnalyze = async (process) => {
    if (!process) return;
    setSelectedClient(process);
    setAnalysisResult(null);
    await Promise.all([
      loadClientFiles(process),
      fetchProcessAiAnalysis(process),
    ]);
  };

  const analyzeDocumentWithAI = async (fileName, docType) => {
    if (!selectedClient) return;

    setIsAnalyzing(true);
    setAnalysisResult(null);
    try {
      const res = await analyzeOneDriveDocument({
        client_folder: selectedClient.client_name,
        file_name: fileName,
        document_type: docType
      });

      if (res.data.success) {
        toast.success("Documento analisado com sucesso!");
        setAnalysisResult({
          fileName,
          docType,
          extracted: res.data.extracted_data,
          mapped: res.data.mapped_data
        });

        const extracted = res.data.extracted_data;
        if (extracted.data_validade) {
          setExpiryFormData(prev => ({
            ...prev,
            document_type: docType,
            expiry_date: extracted.data_validade,
            document_name: fileName
          }));
        }
      }
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao analisar documento"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  return {
    isAddExpiryOpen,
    setIsAddExpiryOpen,
    expiryFormData,
    setExpiryFormData,
    formLoading,
    handleAddExpiry,
    openAddExpiryDialog,
    isAnalyzing,
    isLoadingFiles,
    oneDriveFiles,
    selectedClient,
    analysisResult,
    aiSummary,
    aiAnalysisDate,
    aiError,
    loadClientFiles,
    loadClientAndAnalyze,
    refreshAiAnalysis: () => selectedClient && fetchProcessAiAnalysis(selectedClient, { force: true }),
    analyzeDocumentWithAI
  };
};
