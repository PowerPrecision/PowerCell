/**
 * Componentes partilhados para Dashboards (Consultor e Mediador)
 * Elimina código duplicado entre ConsultorDashboard e MediadorDashboard
 */
import React, { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
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
  FileText, Search, Clock, ArrowRight, Eye,
  AlertTriangle, Calendar, Plus, Loader2, Sparkles, FolderOpen
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, differenceInDays } from "date-fns";
import { pt } from "date-fns/locale";
import { getProcesses, getStats, getUpcomingExpiries, getWorkflowStatuses, createDocumentExpiry, getClientS3Files, analyzeOneDriveDocument } from "../../services/api";

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
  const days = differenceInDays(parseISO(expiryDate), new Date());
  if (days < 0) return { color: "text-red-600 bg-red-50", label: "Expirado" };
  if (days <= 7) return { color: "text-red-600 bg-red-50", label: `${days} dias` };
  if (days <= 30) return { color: "text-orange-600 bg-orange-50", label: `${days} dias` };
  return { color: "text-green-600 bg-green-50", label: `${days} dias` };
};

/**
 * Formata data para exibição
 */
export const formatDate = (dateString) => {
  return format(parseISO(dateString), "dd/MM/yyyy", { locale: pt });
};

// ====================================================================
// COMPONENTES PARTILHADOS
// ====================================================================

/**
 * Card de estatísticas do dashboard
 */
export const StatCard = ({ icon: Icon, iconColor, bgColor, value, label, onClick }) => (
  <Card
    className={`border-border ${onClick ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}`}
    {...(onClick ? { onClick } : {})}
  >
    <CardContent className="pt-6">
      <div className="flex items-center gap-4">
        <div className={`p-3 ${bgColor} rounded-lg`}>
          <Icon className={`h-6 w-6 ${iconColor}`} />
        </div>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-sm text-muted-foreground">{label}</p>
        </div>
      </div>
    </CardContent>
  </Card>
);

/**
 * Badge de estado do workflow
 */
export const StatusBadge = ({ status, workflowStatuses }) => {
  const statusInfo = workflowStatuses.find(s => s.name === status);
  if (!statusInfo) return <Badge variant="outline">{status}</Badge>;
  
  const colorClasses = {
    yellow: "bg-yellow-100 text-yellow-800",
    blue: "bg-blue-100 text-blue-800",
    orange: "bg-orange-100 text-orange-800",
    green: "bg-green-100 text-green-800",
    red: "bg-red-100 text-red-800",
    purple: "bg-purple-100 text-purple-800",
  };
  
  // Safely extract label — it should be a string but may be an object {value, label}
  const label = typeof statusInfo.label === 'object' && statusInfo.label !== null
    ? (statusInfo.label.label || statusInfo.label.value || String(statusInfo.label))
    : (statusInfo.label || status);
  
  return (
    <Badge className={`${colorClasses[statusInfo.color] || "bg-gray-100 text-gray-800"} border`}>
      {statusInfo.order || ''} - {label}
    </Badge>
  );
};

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
                <p className="font-medium">{doc.document_name}</p>
                <Badge variant="outline" className="text-xs">{doc.document_type}</Badge>
              </div>
              <p className="text-sm">
                Cliente: {doc.client_name} • {doc.client_email}
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
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Adicionar"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
);

/**
 * Componente de loading
 */
export const LoadingSpinner = () => (
  <div className="flex items-center justify-center h-64">
    <Loader2 className="h-8 w-8 animate-spin text-primary" />
  </div>
);

/**
 * Tab de análise IA - seleção de cliente
 */
export const AIAnalysisTab = ({
  processes,
  selectedClient,
  onSelectClient,
  oneDriveFiles,
  isAnalyzing,
  onAnalyzeDocument,
  analysisResult
}) => (
  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-purple-500" />
          Análise de Documentos com IA
        </CardTitle>
        <CardDescription>
          Selecione um cliente e um documento do Drive para extrair dados automaticamente
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Selecione um cliente</Label>
            <Select onValueChange={onSelectClient}>
              <SelectTrigger>
                <SelectValue placeholder="Escolha um cliente" />
              </SelectTrigger>
              <SelectContent>
                {processes.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.client_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedClient && (
            <div className="p-4 bg-muted/50 rounded-lg">
              <p className="font-medium mb-2">Cliente: {selectedClient.client_name}</p>
              <p className="text-sm text-muted-foreground">Pasta Drive: {selectedClient.client_name}</p>
            </div>
          )}

          {analysisResult && (
            <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
              <p className="font-medium text-green-800 dark:text-green-200 mb-2">
                ✓ Dados Extraídos: {analysisResult.fileName}
              </p>
              <div className="text-sm space-y-1">
                {analysisResult.mapped?.financial_data && (
                  <>
                    <p><strong>Salário Líquido:</strong> €{analysisResult.mapped.financial_data.monthly_income || "N/D"}</p>
                    <p><strong>Empresa:</strong> {analysisResult.mapped.financial_data.employer_name || "N/D"}</p>
                    <p><strong>Tipo Contrato:</strong> {analysisResult.mapped.financial_data.employment_type || "N/D"}</p>
                  </>
                )}
                {analysisResult.mapped?.personal_data && (
                  <>
                    <p><strong>NIF:</strong> {analysisResult.mapped.personal_data.nif || "N/D"}</p>
                    <p><strong>Data Nascimento:</strong> {analysisResult.mapped.personal_data.birth_date || "N/D"}</p>
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
          Ficheiros do Drive
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!selectedClient ? (
          <div className="text-center py-8 text-muted-foreground">
            <FolderOpen className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Selecione um cliente para ver os ficheiros</p>
          </div>
        ) : oneDriveFiles.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>Nenhum ficheiro disponível nesta pasta</p>
          </div>
        ) : (
          <div className="space-y-2">
            {oneDriveFiles.map((file) => (
              <div key={file.id} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                  <span className="text-sm">{file.name}</span>
                </div>
                <Select onValueChange={(docType) => onAnalyzeDocument(file.name, docType)}>
                  <SelectTrigger className="w-40">
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
            ))}
            {isAnalyzing && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
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
  const [oneDriveFiles, setOneDriveFiles] = useState([]);
  const [selectedClient, setSelectedClient] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);

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
      toast.error(error.response?.data?.detail || "Erro ao adicionar");
    } finally {
      setFormLoading(false);
    }
  };

  const openAddExpiryDialog = (processId) => {
    setSelectedProcessId(processId);
    setIsAddExpiryOpen(true);
  };

  const loadClientFiles = async (process) => {
    setSelectedClient(process);
    setAnalysisResult(null);
    try {
      const res = await getClientS3Files(process.id);
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
    }
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
      toast.error(error.response?.data?.detail || "Erro ao analisar documento");
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
    oneDriveFiles,
    selectedClient,
    analysisResult,
    loadClientFiles,
    analyzeDocumentWithAI
  };
};
