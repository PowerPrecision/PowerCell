/**
 * UnifiedLogsPage - Página Unificada de Logs
 * Combina Logs do Sistema e Logs de Importação IA numa única interface
 */
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { ScrollArea } from "../components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  AlertCircle,
  AlertTriangle,
  Info,
  XCircle,
  Check,
  CheckCircle,
  Eye,
  Trash2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Clock,
  Server,
  Activity,
  FileText,
  Upload,
  User,
  Users,
  Home,
  Banknote,
  MoreHorizontal,
  TrendingUp,
  Loader2,
  CheckSquare,
  List,
} from "lucide-react";
import { Checkbox } from "../components/ui/checkbox";
import { toast } from "sonner";
import { formatDateTime } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

// ============== CONFIGURAÇÕES ==============
const severityConfig = {
  info: { icon: Info, color: "bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 border-blue-200 dark:border-blue-800", label: "Info" },
  warning: { icon: AlertTriangle, color: "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800", label: "Aviso" },
  error: { icon: AlertCircle, color: "bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800", label: "Erro" },
  critical: { icon: XCircle, color: "bg-red-200 dark:bg-red-900/50 text-red-900 dark:text-red-200 border-red-300 dark:border-red-700", label: "Crítico" },
};

const documentTypeConfig = {
  cc: { label: "Cartão de Cidadão", icon: "🪪" },
  irs: { label: "Declaração IRS", icon: "📄" },
  recibo_vencimento: { label: "Recibo de Vencimento", icon: "💰" },
  contrato_trabalho: { label: "Contrato de Trabalho", icon: "📝" },
  extrato_bancario: { label: "Extrato Bancário", icon: "🏦" },
  caderneta_predial: { label: "Caderneta Predial", icon: "🏠" },
  outro: { label: "Outro Documento", icon: "📎" },
};

const categoryConfig = {
  dados_pessoais: { label: "Dados Pessoais", icon: User, color: "text-blue-600" },
  imovel: { label: "Imóvel", icon: Home, color: "text-green-600" },
  financiamento: { label: "Financiamento", icon: Banknote, color: "text-purple-600" },
  outros: { label: "Outros", icon: MoreHorizontal, color: "text-gray-600" },
};

// ============== COMPONENTES ==============
const SeverityBadge = ({ severity }) => {
  const config = severityConfig[severity] || severityConfig.info;
  const Icon = config.icon;
  return (
    <Badge variant="outline" className={`${config.color} gap-1`}>
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  );
};

const CategorizedDataView = ({ categorizedData }) => {
  if (!categorizedData || Object.keys(categorizedData).length === 0) {
    return (
      <div className="text-center py-4 text-muted-foreground">
        Sem dados extraídos
      </div>
    );
  }

  const availableCategories = Object.keys(categorizedData).filter(
    (key) => Object.keys(categorizedData[key]).length > 0
  );

  if (availableCategories.length === 0) {
    return (
      <div className="text-center py-4 text-muted-foreground">
        Sem dados para mostrar
      </div>
    );
  }

  return (
    <Tabs defaultValue={availableCategories[0]} className="w-full">
      <TabsList className="grid w-full" style={{ gridTemplateColumns: `repeat(${availableCategories.length}, 1fr)` }}>
        {availableCategories.map((category) => {
          const config = categoryConfig[category] || categoryConfig.outros;
          const Icon = config.icon;
          const count = Object.keys(categorizedData[category]).length;
          return (
            <TabsTrigger key={category} value={category} className="gap-2">
              <Icon className={`h-4 w-4 ${config.color}`} />
              <span className="hidden sm:inline">{config.label}</span>
              <Badge variant="secondary" className="ml-1 text-xs">{count}</Badge>
            </TabsTrigger>
          );
        })}
      </TabsList>

      {availableCategories.map((category) => (
        <TabsContent key={category} value={category} className="mt-4">
          <div className="grid gap-3">
            {Object.entries(categorizedData[category]).map(([key, value]) => (
              <div key={key} className="flex justify-between items-start p-3 bg-muted/30 rounded-lg">
                <span className="text-sm font-medium text-muted-foreground capitalize">
                  {key.replace(/_/g, " ")}
                </span>
                <span className="text-sm font-semibold text-right max-w-[60%] break-words">
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </span>
              </div>
            ))}
          </div>
        </TabsContent>
      ))}
    </Tabs>
  );
};

// ============== TAB: LOGS DO SISTEMA ==============
const SystemLogsTab = ({ token }) => {
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [severityFilter, setSeverityFilter] = useState("");
  const [componentFilter, setComponentFilter] = useState("");
  const [resolvedFilter, setResolvedFilter] = useState("");
  const [daysFilter, setDaysFilter] = useState("7");
  const [selectedLog, setSelectedLog] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [resolveNotes, setResolveNotes] = useState("");
  const [resolving, setResolving] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);

  const fetchLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      params.append("page", page);
      params.append("limit", "25");
      params.append("days", daysFilter);
      if (severityFilter) params.append("severity", severityFilter);
      if (componentFilter) params.append("component", componentFilter);
      if (resolvedFilter !== "") params.append("resolved", resolvedFilter === "true");

      const response = await fetch(`${API_URL}/api/admin/system-logs?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setLogs(data.errors || []);
        setTotalPages(data.pages || 1);
        setTotal(data.total || 0);
      }
    } catch (error) {
      console.error("Erro:", error);
    } finally {
      setLoading(false);
    }
  }, [token, page, severityFilter, componentFilter, resolvedFilter, daysFilter]);

  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/system-logs/stats?days=${daysFilter}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error("Erro ao carregar estatísticas:", error);
    }
  };

  useEffect(() => {
    fetchLogs();
    fetchStats();
  }, [fetchLogs]);


  const handleBulkResolve = async () => {
    if (selectedIds.length === 0) return;
    try {
      const response = await fetch(`${API_URL}/api/admin/system-logs/bulk-resolve`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ error_ids: selectedIds }),
      });
      if (response.ok) {
        const data = await response.json();
        toast.success(`${data.resolved_count || selectedIds.length} logs marcados como resolvidos`);
        setSelectedIds([]);
        fetchLogs();
        fetchStats();
      }
    } catch {
      toast.error("Erro ao resolver em massa");
    }
  };

  const handleResolveAll = async () => {
    if (!window.confirm("Tem a certeza que quer marcar TODOS os erros como resolvidos?")) {
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/admin/system-logs/resolve-all`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message || "Todos os erros foram resolvidos");
        setSelectedIds([]);
        fetchLogs();
        fetchStats();
      }
    } catch {
      toast.error("Erro ao resolver todos os erros");
    }
  };

  const toggleSelectAll = () => {
    const unresolvedIds = logs.filter(log => !log.resolved).map(log => log.id);
    if (selectedIds.length === unresolvedIds.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(unresolvedIds);
    }
  };

  const toggleSelectLog = (logId) => {
    setSelectedIds(prev => 
      prev.includes(logId) 
        ? prev.filter(id => id !== logId) 
        : [...prev, logId]
    );
  };

  const handleResolve = async () => {
    if (!selectedLog) return;
    setResolving(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/system-logs/${selectedLog.id}/resolve`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ notes: resolveNotes }),
      });
      if (response.ok) {
        toast.success("Erro marcado como resolvido");
        setShowDetails(false);
        setResolveNotes("");
        fetchLogs();
        fetchStats();
      }
    } catch {
      toast.error("Erro ao resolver");
    } finally {
      setResolving(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "—";
    return formatDateTime(dateStr);
  };

  const openDetails = (log) => {
    setSelectedLog(log);
    setResolveNotes("");
    setShowDetails(true);
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[1,2,3,4,5].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-lg" />)}
        </div>
        <div className="h-10 bg-muted animate-pulse rounded" />
        <div className="space-y-2">
          {[1,2,3,4,5].map(i => <div key={i} className="h-14 bg-muted animate-pulse rounded" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <Activity className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Total</p>
                  <p className="text-2xl font-bold">{stats.total}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Não Lidos</p>
                  <p className="text-2xl font-bold">{stats.unread}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-100 dark:bg-orange-900/30 rounded-lg">
                  <Clock className="h-5 w-5 text-orange-600 dark:text-orange-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Por Resolver</p>
                  <p className="text-2xl font-bold">{stats.unresolved}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className={stats.critical > 0 ? "border-red-500 dark:border-red-400" : ""}>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${stats.critical > 0 ? "bg-red-100 dark:bg-red-900/30" : "bg-gray-100 dark:bg-gray-800"}`}>
                  <XCircle className={`h-5 w-5 ${stats.critical > 0 ? "text-red-600 dark:text-red-400" : "text-gray-400"}`} />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Críticos</p>
                  <p className={`text-2xl font-bold ${stats.critical > 0 ? "text-red-600 dark:text-red-400" : ""}`}>
                    {stats.critical}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
                  <Server className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Componentes</p>
                  <p className="text-2xl font-bold">{Object.keys(stats.by_component || {}).length}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filtros */}
      <Card>
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div>
              <Label className="text-xs">Severidade</Label>
              <Select value={severityFilter || "all"} onValueChange={(v) => setSeverityFilter(v === "all" ? "" : v)}>
                <SelectTrigger>
                  <SelectValue placeholder="Todas" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todas</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="warning">Aviso</SelectItem>
                  <SelectItem value="error">Erro</SelectItem>
                  <SelectItem value="critical">Crítico</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Componente</Label>
              <Input
                placeholder="Ex: scraper"
                value={componentFilter}
                onChange={(e) => setComponentFilter(e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs">Estado</Label>
              <Select value={resolvedFilter || "all"} onValueChange={(v) => setResolvedFilter(v === "all" ? "" : v)}>
                <SelectTrigger>
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="false">Por Resolver</SelectItem>
                  <SelectItem value="true">Resolvidos</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Período</Label>
              <Select value={daysFilter} onValueChange={setDaysFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="7 dias" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">Últimas 24h</SelectItem>
                  <SelectItem value="7">Últimos 7 dias</SelectItem>
                  <SelectItem value="30">Últimos 30 dias</SelectItem>
                  <SelectItem value="90">Últimos 90 dias</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button
                variant="outline"
                className="w-full"
                onClick={() => {
                  setSeverityFilter("");
                  setComponentFilter("");
                  setResolvedFilter("");
                  setDaysFilter("7");
                  setPage(1);
                }}
              >
                Limpar
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Barra de Acções em Massa */}
      {selectedIds.length > 0 && (
        <Card className="border-primary bg-primary/5">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <CheckSquare className="h-5 w-5 text-primary" />
                <span className="font-medium">
                  {selectedIds.length} {selectedIds.length === 1 ? 'log seleccionado' : 'logs seleccionados'}
                </span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedIds([])}
                >
                  Limpar Selecção
                </Button>
                <Button
                  size="sm"
                  onClick={handleBulkResolve}
                  className="bg-green-600 hover:bg-green-700"
                >
                  <Check className="h-4 w-4 mr-2" />
                  Marcar como Resolvidos
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleResolveAll}
                  data-testid="resolve-all-errors-btn"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Limpar Todos os Erros
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabela */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">
                  <Checkbox
                    checked={selectedIds.length > 0 && selectedIds.length === logs.filter(l => !l.resolved).length}
                    onCheckedChange={toggleSelectAll}
                    aria-label="Seleccionar todos"
                  />
                </TableHead>
                <TableHead className="w-32">Severidade</TableHead>
                <TableHead className="w-32">Componente</TableHead>
                <TableHead>Mensagem</TableHead>
                <TableHead className="w-40">Data</TableHead>
                <TableHead className="w-24">Estado</TableHead>
                <TableHead className="w-20">Acções</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {logs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                    Nenhum log encontrado
                  </TableCell>
                </TableRow>
              ) : (
                logs.map((log) => (
                  <TableRow
                    key={log.id}
                    className={`cursor-pointer hover:bg-muted/50 ${!log.read ? "bg-yellow-50/50 dark:bg-yellow-900/10" : ""} ${selectedIds.includes(log.id) ? "bg-primary/10" : ""}`}
                  >
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds.includes(log.id)}
                        onCheckedChange={() => toggleSelectLog(log.id)}
                        disabled={log.resolved}
                        aria-label={`Seleccionar log ${log.id}`}
                      />
                    </TableCell>
                    <TableCell onClick={() => openDetails(log)}>
                      <SeverityBadge severity={log.severity} />
                    </TableCell>
                    <TableCell onClick={() => openDetails(log)}>
                      <span className="text-xs font-mono bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">
                        {log.component || "geral"}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-md truncate" onClick={() => openDetails(log)}>{log.message}</TableCell>
                    <TableCell className="text-sm text-muted-foreground" onClick={() => openDetails(log)}>
                      {formatDate(log.timestamp)}
                    </TableCell>
                    <TableCell onClick={() => openDetails(log)}>
                      {log.resolved ? (
                        <Badge variant="outline" className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300">
                          <Check className="h-3 w-3 mr-1" />
                          Resolvido
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300">
                          Pendente
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); openDetails(log); }}>
                        <Eye className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Paginação */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Página {page} de {totalPages} ({total} registos)
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Dialog de Detalhes */}
      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedLog && <SeverityBadge severity={selectedLog.severity} />}
              Detalhes do Erro
            </DialogTitle>
            <DialogDescription>
              {selectedLog?.type} em {selectedLog?.component || "geral"}
            </DialogDescription>
          </DialogHeader>

          {selectedLog && (
            <div className="space-y-4">
              <div>
                <Label className="text-xs text-muted-foreground">Mensagem</Label>
                <p className="p-3 bg-muted rounded-lg text-sm">{selectedLog.message}</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs text-muted-foreground">Componente</Label>
                  <p className="font-mono text-sm">{selectedLog.component || "geral"}</p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Data</Label>
                  <p className="text-sm">{formatDate(selectedLog.timestamp)}</p>
                </div>
              </div>

              {selectedLog.details && Object.keys(selectedLog.details).length > 0 && (
                <div>
                  <Label className="text-xs text-muted-foreground">Detalhes</Label>
                  <ScrollArea className="h-40 rounded-lg border p-3">
                    <pre className="text-xs font-mono whitespace-pre-wrap">
                      {JSON.stringify(selectedLog.details, null, 2)}
                    </pre>
                  </ScrollArea>
                </div>
              )}

              {!selectedLog.resolved && (
                <div>
                  <Label className="text-xs text-muted-foreground">Notas de Resolução</Label>
                  <Textarea
                    placeholder="Descreva como resolveu o problema..."
                    value={resolveNotes}
                    onChange={(e) => setResolveNotes(e.target.value)}
                    rows={3}
                  />
                </div>
              )}
            </div>
          )}

          <DialogFooter className="gap-2">
            {!selectedLog?.resolved && (
              <Button onClick={handleResolve} disabled={resolving}>
                {resolving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Check className="h-4 w-4 mr-2" />}
                Marcar como Resolvido
              </Button>
            )}
            <Button variant="ghost" onClick={() => setShowDetails(false)}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ============== TAB: LOGS DE IMPORTAÇÃO IA ==============
const ImportLogsTab = ({ token }) => {
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [clientFilter, setClientFilter] = useState("");
  const [docTypeFilter, setDocTypeFilter] = useState("");
  const [daysFilter, setDaysFilter] = useState("7");
  const [selectedLog, setSelectedLog] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [viewMode, setViewMode] = useState("list"); // "list" or "grouped"
  const [groupedData, setGroupedData] = useState(null);
  const [expandedClients, setExpandedClients] = useState(new Set());

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append("page", page);
      params.append("limit", "25");
      params.append("days", daysFilter);
      if (statusFilter) params.append("status", statusFilter);
      if (clientFilter) params.append("client_name", clientFilter);
      if (docTypeFilter) params.append("document_type", docTypeFilter);

      const response = await fetch(`${API_URL}/api/admin/ai-import-logs-v2?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setLogs(data.logs || []);
        setTotalPages(data.pagination?.total_pages || 1);
        setTotal(data.pagination?.total || 0);
        setStats(data.stats || null);
      }
    } catch (error) {
      console.error("Erro:", error);
    } finally {
      setLoading(false);
    }
  }, [token, page, statusFilter, clientFilter, docTypeFilter, daysFilter]);

  useEffect(() => {
    if (viewMode === "list") {
      fetchLogs();
    }
  }, [fetchLogs, viewMode]);

  const fetchGroupedLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append("days", daysFilter);
      if (statusFilter) params.append("status", statusFilter);

      const response = await fetch(`${API_URL}/api/admin/ai-import-logs-v2/grouped?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setGroupedData(data);
        setStats(data.stats);
      }
    } catch (error) {
      console.error("Erro ao carregar logs agrupados:", error);
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter, daysFilter]);

  useEffect(() => {
    if (viewMode === "grouped") {
      fetchGroupedLogs();
    }
  }, [viewMode, fetchGroupedLogs]);

  const toggleSelectAll = () => {
    const unresolvedIds = logs.filter(log => log.status === "error" && !log.resolved).map(log => log.id);
    if (selectedIds.length === unresolvedIds.length && unresolvedIds.length > 0) {
      setSelectedIds([]);
    } else {
      setSelectedIds(unresolvedIds);
    }
  };

  const toggleSelectLog = (logId) => {
    setSelectedIds(prev => 
      prev.includes(logId) 
        ? prev.filter(id => id !== logId) 
        : [...prev, logId]
    );
  };

  const handleBulkResolve = async () => {
    if (selectedIds.length === 0) return;
    try {
      const response = await fetch(`${API_URL}/api/admin/ai-import-logs/bulk-resolve`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ log_ids: selectedIds }),
      });
      if (response.ok) {
        const data = await response.json();
        toast.success(`${data.resolved_count || selectedIds.length} logs marcados como resolvidos`);
        setSelectedIds([]);
        fetchLogs();
      }
    } catch {
      toast.error("Erro ao resolver em massa");
    }
  };

  const toggleClientExpand = (clientName) => {
    setExpandedClients(prev => {
      const newSet = new Set(prev);
      if (newSet.has(clientName)) {
        newSet.delete(clientName);
      } else {
        newSet.add(clientName);
      }
      return newSet;
    });
  };

  const handleMarkResolved = async (logId) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/ai-import-logs/${logId}/resolve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        toast.success("Log marcado como resolvido");
        fetchLogs();
        if (selectedLog?.id === logId) {
          setSelectedLog({ ...selectedLog, resolved: true });
        }
      }
    } catch {
      toast.error("Erro ao marcar como resolvido");
    }
  };

  const openDetails = async (log) => {
    setSelectedLog(log);
    setShowDetails(true);
    if (!log.categorized_data) {
      setLoadingDetail(true);
      try {
        const response = await fetch(`${API_URL}/api/admin/ai-import-logs-v2/${log.id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const detail = await response.json();
          setSelectedLog(detail);
        }
      } catch (error) {
        console.error("Erro ao carregar detalhes:", error);
      } finally {
        setLoadingDetail(false);
      }
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "—";
    return formatDateTime(dateStr);
  };

  const getDocTypeConfig = (type) => documentTypeConfig[type] || documentTypeConfig.outro;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <FileText className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">
                    {viewMode === "grouped" ? "Documentos" : "Total"}
                  </p>
                  <p className="text-2xl font-bold">
                    {viewMode === "grouped" ? (stats.total_docs || 0) : stats.total}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          {viewMode === "grouped" && (
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
                    <Users className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Clientes</p>
                    <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                      {stats.total_clients || 0}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                  <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Sucesso</p>
                  <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                    {viewMode === "grouped" ? (stats.total_success || 0) : stats.success}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
                  <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Erros</p>
                  <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                    {viewMode === "grouped" ? (stats.total_errors || 0) : stats.error}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
                  <TrendingUp className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Campos</p>
                  <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                    {viewMode === "grouped" ? (stats.total_fields || 0) : stats.fields_updated}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filtros */}
      <Card>
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <div>
              <Label className="text-xs">Vista</Label>
              <div className="flex gap-1 mt-1">
                <Button
                  variant={viewMode === "list" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setViewMode("list")}
                  className="flex-1"
                >
                  <List className="h-4 w-4 mr-1" />
                  Lista
                </Button>
                <Button
                  variant={viewMode === "grouped" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setViewMode("grouped")}
                  className="flex-1"
                >
                  <Users className="h-4 w-4 mr-1" />
                  Clientes
                </Button>
              </div>
            </div>
            <div>
              <Label className="text-xs">Estado</Label>
              <Select value={statusFilter || "all"} onValueChange={(v) => { setStatusFilter(v === "all" ? "" : v); setPage(1); }}>
                <SelectTrigger>
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="success">Sucesso</SelectItem>
                  <SelectItem value="error">Erro</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Tipo Doc.</Label>
              <Select value={docTypeFilter || "all"} onValueChange={(v) => { setDocTypeFilter(v === "all" ? "" : v); setPage(1); }} disabled={viewMode === "grouped"}>
                <SelectTrigger>
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="cc">CC</SelectItem>
                  <SelectItem value="irs">IRS</SelectItem>
                  <SelectItem value="recibo_vencimento">Recibo</SelectItem>
                  <SelectItem value="contrato_trabalho">Contrato</SelectItem>
                  <SelectItem value="extrato_bancario">Extrato</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Cliente</Label>
              <Input
                placeholder="Nome do cliente"
                value={clientFilter}
                onChange={(e) => setClientFilter(e.target.value)}
                disabled={viewMode === "grouped"}
              />
            </div>
            <div>
              <Label className="text-xs">Período</Label>
              <Select value={daysFilter} onValueChange={(v) => { setDaysFilter(v); setPage(1); }}>
                <SelectTrigger>
                  <SelectValue placeholder="7 dias" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">Últimas 24h</SelectItem>
                  <SelectItem value="7">Últimos 7 dias</SelectItem>
                  <SelectItem value="30">Últimos 30 dias</SelectItem>
                  <SelectItem value="90">Últimos 90 dias</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button
                variant="outline"
                className="w-full"
                onClick={() => {
                  setStatusFilter("");
                  setClientFilter("");
                  setDocTypeFilter("");
                  setDaysFilter("7");
                  setPage(1);
                  setSelectedIds([]);
                }}
              >
                Limpar
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Barra de Acções em Massa */}
      {selectedIds.length > 0 && (
        <Card className="border-primary bg-primary/5">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <CheckSquare className="h-5 w-5 text-primary" />
                <span className="font-medium">
                  {selectedIds.length} {selectedIds.length === 1 ? 'log seleccionado' : 'logs seleccionados'}
                </span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedIds([])}
                >
                  Limpar Selecção
                </Button>
                <Button
                  size="sm"
                  onClick={handleBulkResolve}
                  className="bg-green-600 hover:bg-green-700"
                >
                  <Check className="h-4 w-4 mr-2" />
                  Marcar como Resolvidos
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Vista Agrupada por Cliente */}
      {viewMode === "grouped" && groupedData && (
        <div className="space-y-3">
          {groupedData.groups?.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Nenhum log de importação encontrado no período seleccionado
              </CardContent>
            </Card>
          ) : (
            groupedData.groups?.map((group) => (
              <Card key={group.client_name} className="overflow-hidden">
                <div 
                  className="p-4 cursor-pointer hover:bg-muted/50 flex items-center justify-between"
                  onClick={() => toggleClientExpand(group.client_name)}
                >
                  <div className="flex items-center gap-3">
                    <User className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <p className="font-semibold">{group.client_name || "Sem cliente"}</p>
                      <p className="text-sm text-muted-foreground">
                        Última importação: {formatDate(group.last_import)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
                        {group.total_docs} docs
                      </Badge>
                      {group.success_count > 0 && (
                        <Badge variant="outline" className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300">
                          <CheckCircle className="h-3 w-3 mr-1" />
                          {group.success_count}
                        </Badge>
                      )}
                      {group.error_count > 0 && (
                        <Badge variant="outline" className="bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300">
                          <XCircle className="h-3 w-3 mr-1" />
                          {group.error_count}
                        </Badge>
                      )}
                      <Badge variant="outline" className="bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300">
                        {group.fields_updated} campos
                      </Badge>
                    </div>
                    {expandedClients.has(group.client_name) ? (
                      <ChevronUp className="h-5 w-5 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-5 w-5 text-muted-foreground" />
                    )}
                  </div>
                </div>
                
                {expandedClients.has(group.client_name) && (
                  <div className="border-t overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-24">Estado</TableHead>
                          <TableHead className="w-28">Tipo Doc.</TableHead>
                          <TableHead>Ficheiro</TableHead>
                          <TableHead className="w-20">Campos</TableHead>
                          <TableHead className="w-40">Data</TableHead>
                          <TableHead className="w-20">Acções</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {group.logs.map((log) => {
                          const docConfig = getDocTypeConfig(log.document_type);
                          return (
                            <TableRow key={log.id} className="cursor-pointer hover:bg-muted/50">
                              <TableCell>
                                {log.status === "success" ? (
                                  <Badge variant="outline" className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 gap-1">
                                    <CheckCircle className="h-3 w-3" />
                                    OK
                                  </Badge>
                                ) : (
                                  <Badge variant="outline" className="bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 gap-1">
                                    <XCircle className="h-3 w-3" />
                                    Erro
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell>
                                <span className="text-sm">{docConfig.icon} {docConfig.label.split(" ")[0]}</span>
                              </TableCell>
                              <TableCell className="max-w-xs truncate text-sm text-muted-foreground">
                                {log.filename}
                              </TableCell>
                              <TableCell>
                                {log.fields_count > 0 ? (
                                  <Badge variant="secondary">{log.fields_count}</Badge>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </TableCell>
                              <TableCell className="text-sm text-muted-foreground">
                                {formatDate(log.timestamp)}
                              </TableCell>
                              <TableCell>
                                <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); openDetails({...log, client_name: group.client_name}); }}>
                                  <Eye className="h-4 w-4" />
                                </Button>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </Card>
            ))
          )}
        </div>
      )}

      {/* Tabela (apenas em modo lista) */}
      {viewMode === "list" && (
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <Checkbox
                      checked={selectedIds.length > 0 && selectedIds.length === logs.filter(l => l.status === "error" && !l.resolved).length}
                      onCheckedChange={toggleSelectAll}
                      aria-label="Seleccionar todos"
                    />
                  </TableHead>
                  <TableHead className="w-24">Estado</TableHead>
                  <TableHead className="w-28">Tipo Doc.</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Ficheiro</TableHead>
                  <TableHead className="w-20">Campos</TableHead>
                  <TableHead className="w-40">Data</TableHead>
                  <TableHead className="w-20">Acções</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                      Nenhum log de importação encontrado
                    </TableCell>
                  </TableRow>
                ) : (
                  logs.map((log) => {
                    const docConfig = getDocTypeConfig(log.document_type);
                    const canSelect = log.status === "error" && !log.resolved;
                    return (
                      <TableRow
                        key={log.id}
                        className={`cursor-pointer hover:bg-muted/50 ${selectedIds.includes(log.id) ? "bg-primary/10" : ""}`}
                      >
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={selectedIds.includes(log.id)}
                            onCheckedChange={() => toggleSelectLog(log.id)}
                            disabled={!canSelect}
                            aria-label={`Seleccionar log ${log.id}`}
                          />
                        </TableCell>
                        <TableCell onClick={() => openDetails(log)}>
                          {log.status === "success" ? (
                            <Badge variant="outline" className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 gap-1">
                              <CheckCircle className="h-3 w-3" />
                              OK
                            </Badge>
                          ) : (
                            <Badge variant="outline" className={`gap-1 ${log.resolved ? "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300" : "bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300"}`}>
                              <XCircle className="h-3 w-3" />
                              {log.resolved ? "Resolvido" : "Erro"}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell onClick={() => openDetails(log)}>
                          <span className="text-sm">{docConfig.icon} {docConfig.label.split(" ")[0]}</span>
                        </TableCell>
                        <TableCell className="font-medium" onClick={() => openDetails(log)}>{log.client_name}</TableCell>
                        <TableCell className="max-w-xs truncate text-sm text-muted-foreground" onClick={() => openDetails(log)}>
                          {log.filename}
                        </TableCell>
                        <TableCell onClick={() => openDetails(log)}>
                          {log.fields_count > 0 ? (
                            <Badge variant="secondary">{log.fields_count}</Badge>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground" onClick={() => openDetails(log)}>
                          {formatDate(log.timestamp)}
                        </TableCell>
                        <TableCell>
                          <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); openDetails(log); }}>
                            <Eye className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Paginação (apenas em modo lista) */}
      {viewMode === "list" && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Página {page} de {totalPages} ({total} registos)
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Dialog de Detalhes */}
      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedLog?.status === "success" ? (
                <CheckCircle className="h-5 w-5 text-green-600" />
              ) : (
                <XCircle className="h-5 w-5 text-red-600" />
              )}
              Detalhes da Importação
            </DialogTitle>
            <DialogDescription>
              {selectedLog?.filename} - {selectedLog?.client_name}
            </DialogDescription>
          </DialogHeader>

          {loadingDetail ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : selectedLog && (
            <div className="space-y-6">
              {/* Info básica */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <Label className="text-xs text-muted-foreground">Estado</Label>
                  <div className="mt-1">
                    {selectedLog.status === "success" ? (
                      <Badge className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300">Sucesso</Badge>
                    ) : (
                      <Badge className="bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300">Erro</Badge>
                    )}
                  </div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Tipo</Label>
                  <p className="mt-1 text-sm font-medium">
                    {getDocTypeConfig(selectedLog.document_type).label}
                  </p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Data</Label>
                  <p className="mt-1 text-sm">{formatDate(selectedLog.timestamp)}</p>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Campos</Label>
                  <p className="mt-1 text-sm font-bold text-purple-600 dark:text-purple-400">
                    {selectedLog.fields_count || 0}
                  </p>
                </div>
              </div>

              {/* Erro */}
              {selectedLog.error && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
                    <div>
                      <p className="font-medium text-red-800">Erro</p>
                      <p className="text-sm text-red-700 mt-1">{selectedLog.error}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Campos actualizados */}
              {selectedLog.updated_fields && selectedLog.updated_fields.length > 0 && (
                <div>
                  <Label className="text-xs text-muted-foreground mb-2 block">Campos Actualizados</Label>
                  <div className="flex flex-wrap gap-2">
                    {selectedLog.updated_fields.map((field, idx) => (
                      <Badge key={idx} variant="outline" className="bg-green-50 text-green-700">
                        {field}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Dados categorizados */}
              {selectedLog.categorized_data && (
                <div>
                  <Label className="text-xs text-muted-foreground mb-3 block">
                    Dados Guardados por Categoria
                  </Label>
                  <Card>
                    <CardContent className="pt-4">
                      <CategorizedDataView categorizedData={selectedLog.categorized_data} />
                    </CardContent>
                  </Card>
                </div>
              )}
            </div>
          )}

          <DialogFooter className="gap-2">
            {selectedLog && selectedLog.status === "error" && !selectedLog.resolved && (
              <Button variant="outline" onClick={() => handleMarkResolved(selectedLog.id)}>
                <CheckCircle className="h-4 w-4 mr-2" />
                Marcar como Resolvido
              </Button>
            )}
            <Button variant="ghost" onClick={() => setShowDetails(false)}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// ============== PÁGINA PRINCIPAL ==============
const UnifiedLogsPage = ({ embedded = false }) => {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState("system");

  const pageContent = (
    <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold" data-testid="unified-logs-title">
              Logs do Sistema
            </h1>
            <p className="text-muted-foreground">
              Monitorize erros da aplicação e importações IA
            </p>
          </div>
        </div>

        {/* Tabs principais */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="system" className="gap-2">
              <Server className="h-4 w-4" />
              Erros do Sistema
            </TabsTrigger>
            <TabsTrigger value="import" className="gap-2">
              <Upload className="h-4 w-4" />
              Importações IA
            </TabsTrigger>
          </TabsList>

          <TabsContent value="system">
            <SystemLogsTab token={token} />
          </TabsContent>

          <TabsContent value="import">
            <ImportLogsTab token={token} />
          </TabsContent>
        </Tabs>
      </div>
  );

  return embedded ? pageContent : <DashboardLayout title="Logs do Sistema">{pageContent}</DashboardLayout>;
};

export default UnifiedLogsPage;
