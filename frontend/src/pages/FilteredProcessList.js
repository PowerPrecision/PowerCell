/**
 * FilteredProcessList - Lista de Processos Filtrada
 * Página para mostrar processos filtrados por status/critério
 */
import { useState, useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  ArrowLeft, Search, Eye, Loader2, Users, CheckCircle,
  XCircle, Clock, TrendingUp, AlertTriangle, FileX, FileText, Flame,
  MessageSquare, Trash2
} from "lucide-react";
import { TableSkeleton } from "../components/ui/skeletons";
import { toast } from "sonner";
import { pt } from "date-fns/locale";
import { getProcesses, getWorkflowStatuses, getCalendarDeadlines } from "../services/api";
import { safeDateStr, safeFormat } from "../lib/utils";
import { safeString } from "../utils/safeString";
// PACOTE CH — ClientDetailsModal reutilizável
import ClientDetailsModal from "../components/ClientDetailsModal";

const INACTIVE_STATUS_RE = /concluido|concluidos|desistencia|desistencias|eliminado|eliminados|cancelado|arquivo|perdido|inativo/i;

/**
 * PACOTE BI: Bolinhas de notificação silenciosas (indicadores visuais).
 * Mesmo padrão visual do Kanban (KanbanCard.jsx): azul = mensagens não lidas,
 * verde = novos documentos do portal. Renderiza apenas se houver sinal positivo.
 *
 * PACOTE BT (Fix 1): coerção booleana explícita com Boolean() para garantir
 * que undefined/null/0/"" são tratados como false. Antes, se as flags
 * chegassem como undefined (backend não as injetou), a verificação
 * !hasUnreadMessages && !hasNewDocuments podia ter comportamento inesperado.
 */
const NotificationDots = ({ hasUnreadMessages, hasNewDocuments }) => {
  const unread = Boolean(hasUnreadMessages);
  const newDocs = Boolean(hasNewDocuments);
  if (!unread && !newDocs) return null;
  return (
    <span className="inline-flex items-center gap-1 ml-1.5 align-middle" data-testid="notification-dots">
      {unread && (
        <span
          className="relative flex h-2.5 w-2.5"
          title="Mensagens não lidas do cliente"
          role="img"
          aria-label="Mensagens não lidas"
        >
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
        </span>
      )}
      {newDocs && (
        <span
          className="relative flex h-2.5 w-2.5"
          title="Novos documentos do cliente"
          role="img"
          aria-label="Novos documentos"
        >
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
        </span>
      )}
    </span>
  );
};

const filterConfig = {
  active: {
    title: "Processos Ativos",
    description: "Processos em curso (excluindo concluídos e desistências)",
    icon: TrendingUp,
    color: "text-blue-600",
    bgColor: "bg-blue-50",
    filter: (p) => !INACTIVE_STATUS_RE.test(p.status)
  },
  concluded: {
    title: "Processos Concluídos",
    description: "Processos finalizados com sucesso",
    icon: CheckCircle,
    color: "text-emerald-600",
    bgColor: "bg-emerald-50",
    filter: (p) => p.status === "concluidos"
  },
  dropped: {
    title: "Desistências",
    description: "Processos cancelados ou desistidos",
    icon: XCircle,
    color: "text-red-600",
    bgColor: "bg-red-50",
    filter: (p) => p.status === "desistencias"
  },
  eliminado: {
    title: "Eliminados",
    description: "Processos eliminados (recuperação administrativa)",
    icon: Trash2,
    color: "text-gray-700",
    bgColor: "bg-gray-100",
    filter: (p) => p.status === "eliminados" || p.is_deleted === true
  },
  pending_deadlines: {
    title: "Prazos Pendentes",
    description: "Processos com prazos a aproximar-se ou vencidos",
    icon: Clock,
    color: "text-orange-600",
    bgColor: "bg-orange-50",
    filter: null, // Filtro especial via deadlines
    showDeadlineInfo: true
  },
  indexacao: {
    title: "Indexação",
    description: "Processos com atribuição de Indexação",
    icon: FileText,
    color: "text-gray-600",
    bgColor: "bg-gray-50",
    filter: (p) => !!p.assigned_indexacao_id
  },
  no_indexacao: {
    title: "Sem Indexação",
    description: "Processos sem indexação atribuída",
    icon: FileX,
    color: "text-rose-600",
    bgColor: "bg-rose-50",
    filter: (p) => !p.assigned_indexacao_id && !INACTIVE_STATUS_RE.test(p.status)
  },
  waiting: {
    title: "Clientes em Espera",
    description: "Processos no estado inicial de espera",
    icon: Users,
    color: "text-amber-600",
    bgColor: "bg-amber-50",
    filter: (p) => p.status === "clientes_espera"
  },
  waiting_long: {
    title: "Em Espera Há Muito Tempo",
    description: "Processos em espera há mais de 15 dias",
    icon: AlertTriangle,
    color: "text-red-600",
    bgColor: "bg-red-50",
    filter: (p) => {
      if (p.status !== "clientes_espera") return false;
      const created = new Date(safeDateStr(p.created_at));
      const now = new Date();
      const days = Math.floor((now - created) / (1000 * 60 * 60 * 24));
      return days >= 15;
    }
  }
};

const FilteredProcessList = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const filterType = searchParams.get("filter") || "active";

  // PACOTE CA — Persist Table Filters in URL Params
  // searchTerm lido do URL (default ""). Quando o utilizador pesquisa,
  // o valor é escrito no URL em tempo real via setSearchParams. Assim,
  // ao navegar para os detalhes de um processo e clicar em "Voltar",
  // o browser restaura exatamente a vista pretendida (filtros + pesquisa).
  const searchTerm = searchParams.get("search") || "";

  // Handler para atualizar a pesquisa no URL
  const handleSearchChange = (value) => {
    setSearchParams(prev => {
      if (value) {
        prev.set("search", value);
      } else {
        prev.delete("search");
      }
      return prev;
    }, { replace: true });
  };

  const [loading, setLoading] = useState(true);
  const [processes, setProcesses] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  // PACOTE CH — estado para ClientDetailsModal
  const [clientDetailsModal, setClientDetailsModal] = useState({ open: false, clientId: null });

  const config = filterConfig[filterType] || filterConfig.active;
  const IconComponent = config.icon;

  useEffect(() => {
    fetchData();
    // PACOTE BZ: fetchData depende de searchTerm (passa search à API)
    // PACOTE CA: searchTerm agora vem do URL — navegação Back/Forward restaura a vista
  }, [filterType, searchTerm]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchData = async () => {
    try {
      setLoading(true);
      // PACOTE BT (Fix 2): view_mode dinâmico conforme o filterType.
      // PACOTE BZ (Fix): TODOS os filtros passados como Query Params ao Backend.
      // Antes, a API era chamada sem 'search' e a filtragem era feita localmente
      // com .filter(), causando tamanhos de página irregulares.
      const HISTORICAL_FILTERS = ["concluded", "dropped"];
      // PACOTE CW: "eliminado" usa view_mode=deleted para que o backend
      // desligue o filtro padrão de ativos e traga apenas eliminados.
      let viewMode = "active_only";
      if (HISTORICAL_FILTERS.includes(filterType)) viewMode = "historical";
      else if (filterType === "eliminado") viewMode = "deleted";

      // PACOTE BZ: passar search como query param (>= 2 chars) para o backend filtrar
      const searchParam = searchTerm.length >= 2 ? searchTerm : undefined;

      // PACOTE BZ: mapear filterType para status param quando aplicável
      let statusParam = undefined;
      if (filterType === "concluded") statusParam = "concluidos";
      else if (filterType === "dropped") statusParam = "desistencias";
      else if (filterType === "waiting") statusParam = "clientes_espera";
      // Nota: "eliminado" usa apenas view_mode=deleted (sem status param) —
      // o backend já faz a query is_deleted: True quando view_mode=deleted.

      const [processesRes, statusesRes, deadlinesRes] = await Promise.all([
        getProcesses({
          view_mode: viewMode,
          show_all: true,
          size: 100,
          search: searchParam,
          ...(statusParam ? { status: statusParam } : {}),
        }),
        getWorkflowStatuses(),
        getCalendarDeadlines()
      ]);
      setProcesses(Array.isArray(processesRes.data) ? processesRes.data : (processesRes.data?.items || []));
      setWorkflowStatuses(Array.isArray(statusesRes.data) ? statusesRes.data : []);
      setDeadlines(Array.isArray(deadlinesRes.data) ? deadlinesRes.data : []);
    } catch (error) {
      console.error("Erro ao carregar dados:", error);
      toast.error("Erro ao carregar processos");
    } finally {
      setLoading(false);
    }
  };

  // PACOTE BZ: Filtragem delegada ao Backend. Apenas ordenação local (apresentação).
  // Removidas as .filter() locais (config.filter, searchTerm) que causavam
  // tamanhos de página irregulares — o backend já filtra via query params.
  // Exceção: pending_deadlines precisa de cruzar com deadlines (não há endpoint
  // de filtro por prazo no backend), pelo que mantém filtragem local desse subset.
  const getFilteredProcesses = () => {
    let filtered = processes;

    // Filtro especial para prazos pendentes (cruzamento com deadlines — não há
    // endpoint de backend para isto, pelo que é filtragem local legítima)
    if (filterType === "pending_deadlines") {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const upcomingDeadlines = deadlines.filter(d => {
        const deadlineDate = new Date(safeDateStr(d.due_date));
        const daysUntil = Math.ceil((deadlineDate - today) / (1000 * 60 * 60 * 24));
        return daysUntil <= 7; // Próximos 7 dias ou vencidos
      });
      const processIds = [...new Set(upcomingDeadlines.map(d => d.process_id))];
      filtered = processes.filter(p => processIds.includes(p.id));
    }
    // PACOTE BZ: REMOVIDAS as .filter() locais de config.filter e searchTerm.
    // O backend agora filtra por status e search via query params.

    // Ordenação: prioridade alta + tags urgentes SEMPRE no topo (apresentação)
    const hasUrgentTag = (p) => {
      const tags = p.tags || p.labels || [];
      if (!Array.isArray(tags) || tags.length === 0) return false;
      return tags.some(t => {
        const label = (typeof t === 'string' ? t : (t?.label || t?.name || '')).toLowerCase();
        return label.includes('urgente') || label.includes('urgent');
      });
    };
    const priorityWeight = (p) => {
      const raw = (p.prioridade || p.priority || "").toLowerCase();
      if (raw === "alta" || raw === "high") return 3;
      if (raw === "media" || raw === "medium") return 2;
      if (raw === "baixa" || raw === "low") return 1;
      if (hasUrgentTag(p)) return 3;
      return 0;
    };
    filtered = [...filtered].sort((a, b) => priorityWeight(b) - priorityWeight(a));

    return filtered;
  };

  const filteredProcesses = getFilteredProcesses();

  const getStatusInfo = (statusName) => {
    const status = workflowStatuses.find(s => s.name === statusName);
    return status || { label: statusName, color: "gray", order: null };
  };

  const getDeadlineInfo = (processId) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const processDeadlines = deadlines.filter(d => d.process_id === processId);
    if (processDeadlines.length === 0) return null;

    const upcoming = processDeadlines
      .map(d => ({
        ...d,
        daysUntil: Math.ceil((new Date(safeDateStr(d.due_date)) - today) / (1000 * 60 * 60 * 24))
      }))
      .filter(d => d.daysUntil <= 7)
      .sort((a, b) => a.daysUntil - b.daysUntil);

    return upcoming[0] || null;
  };

  const formatCurrency = (value) => {
    if (!value) return "-";
    return new Intl.NumberFormat('pt-PT', { 
      style: 'currency', 
      currency: 'EUR',
      maximumFractionDigits: 0 
    }).format(value);
  };

  /**
   * Resolve a prioridade de um processo (suporta campo PT e EN).
   * Retorna objecto com nivel normalizado, label, classes CSS e se é Alta.
   */
  const resolvePriority = (process) => {
    const raw = (process.prioridade || process.priority || "").toLowerCase();
    const isAlta = raw === "alta" || raw === "high";
    const isMedia = raw === "media" || raw === "medium";
    const isBaixa = raw === "baixa" || raw === "low";

    let label, badgeColor;
    if (isAlta) {
      label = "Alta";
      badgeColor = "bg-red-500 text-white border-red-600";
    } else if (isMedia) {
      label = "Média";
      badgeColor = "bg-amber-100 text-amber-800 border-amber-300";
    } else if (isBaixa) {
      label = "Baixa";
      badgeColor = "bg-green-100 text-green-800 border-green-300";
    } else {
      return { isAlta: false, label: raw || null, badgeColor: "", raw };
    }

    return { isAlta, isMedia, isBaixa, label, badgeColor, raw };
  };

  if (loading) {
    return (
      <DashboardLayout title="Processos">
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            <div className="h-9 w-9 bg-muted animate-pulse rounded" />
            <div className="space-y-1">
              <div className="h-6 w-48 bg-muted animate-pulse rounded" />
              <div className="h-4 w-64 bg-muted animate-pulse rounded" />
            </div>
          </div>
          <TableSkeleton rows={6} columns={5} />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title={config.title}>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div className={`p-3 rounded-lg ${config.bgColor}`}>
            <IconComponent className={`h-6 w-6 ${config.color}`} />
          </div>
          <div>
            <h1 className="text-2xl font-bold">{config.title}</h1>
            <p className="text-muted-foreground">{config.description}</p>
          </div>
          <Badge variant="secondary" className="ml-auto text-lg px-4 py-1">
            {filteredProcesses.length}
          </Badge>
        </div>

        {/* Search */}
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Pesquisar por nome, email ou telefone..."
            className="pl-10"
            value={searchTerm}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>

        {/* Lista */}
        <Card className="border-border">
          <CardContent className="p-0">
            {filteredProcesses.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                <IconComponent className="h-12 w-12 mx-auto mb-4 opacity-20" />
                <p>Nenhum processo encontrado</p>
              </div>
            ) : (
              <>
              {/* O9 - Mobile: Card view */}
              <div className="md:hidden space-y-3 p-3">
                {filteredProcesses.map((process) => {
                  const statusInfo = getStatusInfo(process.status);
                  const deadlineInfo = config.showDeadlineInfo ? getDeadlineInfo(process.id) : null;
                  const prio = resolvePriority(process);
                  return (
                    <div
                      key={`mobile-${process.id}`}
                      className={`border rounded-lg p-3 space-y-2 cursor-pointer hover:bg-muted/50 transition-colors ${
                        prio.isAlta ? 'border-l-[4px] border-l-red-500 bg-red-50/60 dark:bg-red-950/20' : 'bg-card'
                      }`}
                      onClick={() => navigate(`/process/${process.id}`)}
                      data-testid={`process-card-${process.id}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className={`text-sm truncate ${prio.isAlta ? 'font-bold' : 'font-medium'}`}>
                            {prio.isAlta && <span className="mr-1">🔥</span>}
                            {/* PACOTE CX — nome clicável + bolinhas inline (mobile card view) */}
                            <span
                              className="cursor-pointer text-primary hover:underline"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (process.client_id) {
                                  setClientDetailsModal({ open: true, clientId: process.client_id });
                                }
                              }}
                            >
                              {safeString(process.client_name)}
                              {process.has_unread_messages && <span className="w-2 h-2 rounded-full bg-blue-500 inline-block ml-2" title="Nova Mensagem"></span>}
                              {process.has_new_documents && <span className="w-2 h-2 rounded-full bg-green-500 inline-block ml-2" title="Novo Ficheiro"></span>}
                            </span>
                          </p>
                          <p className="text-xs text-muted-foreground">{safeString(process.client_phone) || safeString(process.client_email) || "-"}</p>
                        </div>
                        <div className="flex flex-col items-end gap-1 shrink-0">
                          {prio.isAlta && (
                            <Badge className="bg-red-500 text-white border-red-600 text-[9px] px-1.5 py-0 h-4 gap-0.5 shadow-sm shadow-red-300/50">
                              <Flame className="h-2.5 w-2.5" /> Alta
                            </Badge>
                          )}
                          <Badge 
                            variant="outline"
                            className={`shrink-0 text-[10px] bg-${statusInfo.color}-50 text-${statusInfo.color}-700 border-${statusInfo.color}-200`}
                          >
                            {statusInfo.order || ''} - {typeof statusInfo.label === 'object' ? (statusInfo.label?.label || statusInfo.label?.value || '') : (statusInfo.label || '')}
                          </Badge>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">{formatCurrency(process.property_value)}</span>
                        <div className="flex items-center gap-2">
                          {deadlineInfo && (
                            <Badge variant="outline" className={`text-[10px] ${deadlineInfo.daysUntil <= 0 ? "bg-red-100 text-red-800" : deadlineInfo.daysUntil <= 3 ? "bg-amber-100 text-amber-800" : "bg-blue-100 text-blue-800"}`}>
                              {deadlineInfo.daysUntil <= 0 ? "Vencido" : `${deadlineInfo.daysUntil}d`}
                            </Badge>
                          )}
                          <span>{process.created_at ? safeFormat(process.created_at, "dd/MM/yy", { locale: pt }) : "-"}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* O9 - Desktop: Table */}
              <div className="hidden md:block">
            <ScrollArea className="h-[400px] sm:h-[600px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Contacto</TableHead>
                    <TableHead>Fase</TableHead>
                    <TableHead>Valor</TableHead>
                    {/* PACOTE BE: coluna Notas do Consultor */}
                    <TableHead className="min-w-[140px] max-w-[220px]">Notas do Consultor</TableHead>
                    {config.showDeadlineInfo && <TableHead>Prazo</TableHead>}
                    <TableHead>Data Criação</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredProcesses.map((process) => {
                      const statusInfo = getStatusInfo(process.status);
                      const deadlineInfo = config.showDeadlineInfo ? getDeadlineInfo(process.id) : null;
                      const prio = resolvePriority(process);
                      
                      return (
                        <TableRow
                          key={process.id}
                          className={`cursor-pointer hover:bg-muted/50 ${
                            prio.isAlta 
                              ? 'bg-red-50/50 dark:bg-red-950/10 border-l-[4px] border-l-red-500' 
                              : ''
                          }`}
                          onClick={() => navigate(`/process/${process.id}`)}
                        >
                          <TableCell>
                            <div>
                              <div className="flex items-center gap-2">
                                <p className={prio.isAlta ? 'font-bold' : 'font-medium'}>
                                  {prio.isAlta && <span className="mr-1" title="Prioridade Alta">🔥</span>}
                                  {/* PACOTE CW — nome do cliente clicável (classe exata + bolinhas inline) */}
                                  <span
                                    className="cursor-pointer text-primary hover:underline"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      if (process.client_id) {
                                        setClientDetailsModal({ open: true, clientId: process.client_id });
                                      }
                                    }}
                                  >
                                    {safeString(process.client_name)}
                                    {process.has_unread_messages && <span className="w-2 h-2 rounded-full bg-blue-500 inline-block ml-2" title="Nova Mensagem"></span>}
                                    {process.has_new_documents && <span className="w-2 h-2 rounded-full bg-green-500 inline-block ml-2" title="Novo Ficheiro"></span>}
                                  </span>
                                </p>
                                {prio.isAlta && (
                                  <Badge className="bg-red-500 text-white border-red-600 text-[10px] px-1.5 py-0 h-4 gap-0.5 shadow-sm shadow-red-300/50">
                                    <Flame className="h-3 w-3" /> Alta
                                  </Badge>
                                )}
                              </div>
                              {process.under_35 && (
                                <Badge variant="outline" className="text-[10px] bg-green-50 text-green-700 mt-1">
                                  &lt;35 anos
                                </Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="text-sm">
                              <p>{safeString(process.client_phone) || "-"}</p>
                              <p className="text-muted-foreground text-xs truncate max-w-[150px]">
                                {safeString(process.client_email)}
                              </p>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge 
                              variant="outline"
                              className={`bg-${statusInfo.color}-50 text-${statusInfo.color}-700 border-${statusInfo.color}-200`}
                            >
                              {statusInfo.order || ''} - {typeof statusInfo.label === 'object' ? (statusInfo.label?.label || statusInfo.label?.value || '') : (statusInfo.label || '')}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-medium">
                            {formatCurrency(process.property_value)}
                          </TableCell>
                          {config.showDeadlineInfo && (
                            <TableCell>
                              {deadlineInfo ? (
                                <div>
                                  <p className="text-sm font-medium truncate max-w-[150px]">
                                    {deadlineInfo.title}
                                  </p>
                                  <Badge 
                                    variant="outline"
                                    className={
                                      deadlineInfo.daysUntil <= 0 
                                        ? "bg-red-100 text-red-800 border-red-200" 
                                        : deadlineInfo.daysUntil <= 3 
                                        ? "bg-amber-100 text-amber-800 border-amber-200"
                                        : "bg-blue-100 text-blue-800 border-blue-200"
                                    }
                                  >
                                    {deadlineInfo.daysUntil <= 0 
                                      ? "Vencido" 
                                      : deadlineInfo.daysUntil === 1 
                                      ? "Amanhã" 
                                      : `${deadlineInfo.daysUntil} dias`}
                                  </Badge>
                                </div>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
                            </TableCell>
                          )}
                          {/* PACOTE CZ: Notas — lê a atividade mais recente PRIMEIRO (não process.notes estático) */}
                          <TableCell className="min-w-[140px] max-w-[220px]">
                            {(() => {
                              const noteText = process.latest_activity_preview || process.latest_activity_note || process.latest_note || "";
                              if (noteText) {
                                return (
                                  <div className="line-clamp-2 text-sm text-muted-foreground" title={noteText}>
                                    {noteText.length > 60 ? noteText.substring(0, 60) + '…' : noteText}
                                  </div>
                                );
                              }
                              return <span className="text-xs text-muted-foreground">Sem notas recentes</span>;
                            })()}
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {process.created_at 
                              ? safeFormat(process.created_at, "dd/MM/yyyy", { locale: pt })
                              : "-"
                            }
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/process/${process.id}`);
                              }}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                </TableBody>
              </Table>
            </ScrollArea>
              </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* PACOTE CH — ClientDetailsModal reutilizável */}
      <ClientDetailsModal
        open={clientDetailsModal.open}
        clientId={clientDetailsModal.clientId}
        onClose={() => setClientDetailsModal({ open: false, clientId: null })}
        onNavigateToProcess={(pid) => navigate(`/process/${pid}`)}
      />
    </DashboardLayout>
  );
};

export default FilteredProcessList;
