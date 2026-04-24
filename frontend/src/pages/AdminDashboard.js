/**
 * AdminDashboard — Painel de administração principal com visão agregada do CRM.
 *
 * PORQUÊ: O PowerCell precisa de uma vista única onde administradores e diretores
 * podem monitorizar a saúde do pipeline de processos, atribuir tarefas à equipa,
 * acompanhar prazos e analisar KPIs de conversão. Este dashboard substitui o uso
 * de múltiplas ferramentas externas (Trello, Google Sheets, etc.) por uma interface
 * unificada com dados em tempo real.
 *
 * DECISÕES ARQUITECTURAIS:
 * - KPIs no topo: processos activos, valor em carteira, taxa de conversão, novos hoje.
 * - Gráfico de funil (funnel) do pipeline com Recharts para visualizar gargalos.
 * - Alerta de processos estagnados (sem actualização há 7+ dias) com navegação directa.
 * - Tabs modulares: Visão Geral (Kanban), Calendário, Documentos, Utilizadores,
 *   Análise IA, Pesquisa de Clientes, Tarefas e Leads — cada tab é um componente
 *   independente para manter a página gerível.
 * - Filtros por consultor, mediador e indexação aplicados globalmente.
 * - Feed de atividade recente para percepção imediata do que está a acontecer.
 *
 * @context {AuthContext} — Consome user para verificar permissões e filtros
 *
 * @route /admin — Rota principal do painel de administração
 *
 * @example
 * <AdminDashboard />
 * // Acesso via layout protegido — só visível para roles admin/ceo/diretor
 */
import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { ScrollArea } from "../components/ui/scroll-area";
import { useAuth } from "../contexts/AuthContext";
import { 
  Users, FolderOpen, Loader2, CheckCircle, XCircle, FileText, 
  Calendar as CalendarIcon, Eye, Sparkles, LayoutGrid, Search, ClipboardList, Building,
  TrendingUp, DollarSign, Clock, Target, Activity, ArrowRight, ChevronRight
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";
import { 
  getStats, getUsers, getWorkflowStatuses, getOneDriveStatus, 
  getProcesses, getCalendarDeadlines, createDeadline, deleteDeadline, getUpcomingExpiries,
  getActivities
} from "../services/api";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from "recharts";
import KanbanBoard from "../components/KanbanBoard";
import LeadsKanban from "../components/LeadsKanban";
import CalendarTab from "../components/admin/CalendarTab";
import DocumentsTab from "../components/admin/DocumentsTab";
import UsersTab from "../components/admin/UsersTab";
import ClientSearchTab from "../components/admin/ClientSearchTab";
import CreateEventDialog from "../components/admin/CreateEventDialog";
import AIAnalysisTab from "../components/admin/AIAnalysisTab";
import { StatsGridSkeleton, TableSkeleton } from "../components/ui/skeletons";
import SafeChartContainer from "../components/ui/SafeChartContainer";
import TasksPanel from "../components/TasksPanel";
import TeamFeed from "../components/TeamFeed";
import { hasAnyRole, filterByAnyRole, filterByRole, excludeRoles } from "../utils/roleUtils";
const AdminDashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [users, setUsers] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [storageStatus, setStorageStatus] = useState(null);
  const [calendarDeadlines, setCalendarDeadlines] = useState([]);
  const [upcomingExpiries, setUpcomingExpiries] = useState([]);
  const [staleStats, setStaleStats] = useState(null);
  const [showStaleList, setShowStaleList] = useState(false);
  const [recentActivities, setRecentActivities] = useState([]);
  
  const [activeTab, setActiveTab] = useState("overview");
  const [consultorFilter, setConsultorFilter] = useState("all");
  const [mediadorFilter, setMediadorFilter] = useState("all");
  const [indexacaoFilter, setIndexacaoFilter] = useState("all");
  const [isCreateEventDialogOpen, setIsCreateEventDialogOpen] = useState(false);
  const [selectedDateForEvent, setSelectedDateForEvent] = useState(new Date());

  // Get staff users for assignment (excluindo admin e ceo)
  const staffUsers = useMemo(() => excludeRoles(users || [], ["cliente", "admin", "ceo"]), [users]);
  const consultors = useMemo(() => filterByAnyRole(users || [], ["consultor", "diretor"]), [users]);
  const intermediarios = useMemo(() => filterByAnyRole(users || [], ["mediador", "intermediario", "diretor"]), [users]);
  const indexacaoUsers = useMemo(() => filterByRole(users || [], "indexacao"), [users]);

  // Filter processes
  const filteredProcesses = useMemo(() => {
    return (processes || []).filter(process => {
      const matchesConsultor = consultorFilter === "all" || 
        (consultorFilter === "none" && !process.assigned_consultor_id) ||
        process.assigned_consultor_id === consultorFilter;
      const matchesMediador = mediadorFilter === "all" || 
        (mediadorFilter === "none" && !process.assigned_mediador_id) ||
        process.assigned_mediador_id === mediadorFilter;
      const matchesIndexacao = indexacaoFilter === "all" || 
        (indexacaoFilter === "none" && !process.assigned_indexacao_id) ||
        process.assigned_indexacao_id === indexacaoFilter;
      return matchesConsultor && matchesMediador && matchesIndexacao;
    });
  }, [processes, consultorFilter, mediadorFilter, indexacaoFilter]);

  // ===== KPIs do Dashboard =====
  const activeProcesses = useMemo(() => 
    (processes || []).filter(p => !["concluido", "arquivo", "perdido", "desistencias", "cancelado"].includes(p.status)),
    [processes]
  );
  
  const totalActive = activeProcesses.length;
  
  const totalValueInPortfolio = useMemo(() => 
    activeProcesses.reduce((sum, p) => sum + (p.property_value || 0), 0),
    [activeProcesses]
  );
  
  const conversionRate = useMemo(() => {
    const submitted = (processes || []).filter(p => ["pre_aprovacao", "credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv", "minuta", "escritura", "concluido", "arquivo"].includes(p.status)).length;
    const approved = (processes || []).filter(p => ["credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv", "minuta", "escritura", "concluido", "arquivo"].includes(p.status)).length;
    return submitted > 0 ? ((approved / submitted) * 100).toFixed(1) : "0.0";
  }, [processes]);
  
  const newToday = useMemo(() => {
    const today = new Date().toISOString().split("T")[0];
    return (processes || []).filter(p => (p.created_at || "").startsWith(today)).length;
  }, [processes]);

  // ===== Funnel Data =====
  const funnelData = useMemo(() => {
    const stages = [
      { key: "clientes_espera", label: "Leads", color: "#3B82F6" },
      { key: "documentacao", label: "Documentação", color: "#6366F1" },
      { key: "analise", label: "Análise", color: "#8B5CF6" },
      { key: "pre_aprovacao", label: "Pré-Aprovação", color: "#A855F7" },
      { key: "credito_aprovado", label: "Aprovado", color: "#10B981" },
      { key: "pedido_avaliacao", label: "Avaliação", color: "#F59E0B" },
      { key: "avaliacao", label: "Avaliado", color: "#F97316" },
      { key: "cpcv", label: "CPCV", color: "#EF4444" },
      { key: "minuta", label: "Minuta", color: "#EC4899" },
      { key: "escritura", label: "Escriturado", color: "#22C55E" },
      { key: "concluido", label: "Concluído", color: "#14B8A6" },
    ];
    return stages.map(stage => ({
      name: stage.label,
      value: (processes || []).filter(p => p.status === stage.key).length,
      color: stage.color,
    })).filter(s => s.value > 0);
  }, [processes]);

  useEffect(() => { fetchData(); }, []);
  useEffect(() => { fetchCalendarData(); }, [consultorFilter, mediadorFilter]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem("token");
      
      const [statsRes, usersRes, processesRes, statusesRes, storageRes, expiriesRes] = await Promise.all([
        getStats(),
        getUsers(),
        getProcesses({ view_mode: "all", size: 100 }),
        getWorkflowStatuses(),
        fetch(`${process.env.REACT_APP_BACKEND_URL}/api/storage/status`, {
          headers: { Authorization: `Bearer ${token}` }
        }).then(r => r.json()).catch(() => ({ configured: false })),
        getUpcomingExpiries(60).catch(() => ({ data: [] })),
      ]);
      setStats(statsRes.data);
      setUsers(usersRes.data);
      // O endpoint /api/processes retorna um objeto paginado {items: [...], total, page, size, pages}
      setProcesses(processesRes.data?.items || processesRes.data || []);
      setWorkflowStatuses(statusesRes.data);
      setStorageStatus(storageRes);
      setUpcomingExpiries(expiriesRes.data);
      
      // Fetch stale processes stats
      try {
        const staleRes = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin/stale-processes?days=7`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (staleRes.ok) setStaleStats(await staleRes.json());
      } catch { /* silent */ }
      
      // Fetch recent activities (latest 20 across all processes)
      try {
        const activitiesRes = await getActivities(undefined, 20);
        const allActivities = activitiesRes.data || [];
        setRecentActivities(Array.isArray(allActivities) ? allActivities : []);
      } catch { /* silent */ }
    } catch (error) {
      console.error("Error fetching data:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  };

  const fetchCalendarData = async () => {
    try {
      const res = await getCalendarDeadlines(
        consultorFilter !== "all" ? consultorFilter : null,
        mediadorFilter !== "all" ? mediadorFilter : null
      );
      setCalendarDeadlines(res.data);
    } catch (error) {
      console.error("Error fetching calendar data:", error);
    }
  };

  const handleCreateEvent = async (eventData) => {
    try {
      await createDeadline(eventData);
      toast.success("Evento criado com sucesso");
      fetchCalendarData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar evento");
      throw error;
    }
  };

  const handleDeleteEvent = async (eventId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este evento?")) return;
    try {
      await deleteDeadline(eventId);
      toast.success("Evento eliminado");
      fetchCalendarData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao eliminar evento");
    }
  };

  const openCreateEvent = (date) => {
    setSelectedDateForEvent(date || new Date());
    setIsCreateEventDialogOpen(true);
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="space-y-6">
          <div className="space-y-2">
            <div className="h-7 w-64 bg-muted animate-pulse rounded" />
            <div className="h-4 w-48 bg-muted animate-pulse rounded" />
          </div>
          <StatsGridSkeleton count={4} />
          <div className="h-10 w-full bg-muted animate-pulse rounded" />
          <TableSkeleton rows={5} columns={5} />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="admin-dashboard">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Painel de Administração</h1>
            <p className="text-muted-foreground">Olá, {user?.name}. Bem-vindo ao sistema.</p>
          </div>
        </div>

        {/* KPI Cards de Topo */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="border-border hover:shadow-md transition-shadow cursor-pointer" onClick={() => navigate('/processos')}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <Activity className="h-4 w-4 text-blue-500" />
                Processos Ativos
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{totalActive}</div>
              <p className="text-xs text-muted-foreground mt-1">
                de {(processes || []).length} total
              </p>
            </CardContent>
          </Card>
          <Card className="border-border hover:shadow-md transition-shadow cursor-pointer" onClick={() => navigate('/financeiro')}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-emerald-500" />
                Valor em Carteira
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">
                {totalValueInPortfolio >= 1000000 
                  ? `€${(totalValueInPortfolio / 1000000).toFixed(1)}M`
                  : `€${(totalValueInPortfolio / 1000).toFixed(0)}k`
                }
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Imóveis em processo
              </p>
            </CardContent>
          </Card>
          <Card className="border-border hover:shadow-md transition-shadow cursor-pointer" onClick={() => navigate('/processos?view_mode=historical')}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <Target className="h-4 w-4 text-amber-500" />
                Taxa de Conversão
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{conversionRate}%</div>
              <p className="text-xs text-muted-foreground mt-1">
                Aprovados / Submetidos
              </p>
            </CardContent>
          </Card>
          <Card className="border-border hover:shadow-md transition-shadow cursor-pointer" onClick={() => navigate('/processos?sort=created_at&order=desc')}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-violet-500" />
                Novos Hoje
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{newToday}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {newToday === 1 ? "processo criado" : "processos criados"}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Funnel + Activity Feed Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Funnel Chart */}
          <Card className="lg:col-span-2 border-border">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <LayoutGrid className="h-5 w-5 text-blue-500" />
                Funil do Pipeline
              </CardTitle>
              <CardDescription>
                Processos por fase do workflow
              </CardDescription>
            </CardHeader>
            <CardContent>
              {funnelData.length > 0 ? (
                <SafeChartContainer className="h-[280px] min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={funnelData} layout="vertical" margin={{ left: 20, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis dataKey="name" type="category" width={100} tick={{ fontSize: 12 }} />
                      <Tooltip 
                        formatter={(value) => [`${value} processos`, "Quantidade"]}
                        contentStyle={{ borderRadius: "8px", fontSize: "13px" }}
                      />
                      <Bar dataKey="value" radius={[0, 6, 6, 0]} name="Processos">
                        {funnelData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </SafeChartContainer>
              ) : (
                <div className="flex items-center justify-center h-[280px] text-muted-foreground">
                  Sem dados de pipeline disponíveis
                </div>
              )}
            </CardContent>
          </Card>

          {/* Team Feed (Mural da Equipa) */}
          <TeamFeed />
        </div>

        {/* Stale Processes Alert */}
        {staleStats && staleStats.total > 0 && (
          <Card className="border-orange-200 dark:border-orange-800 bg-orange-50/50 dark:bg-orange-950/20" data-testid="stale-processes-alert">
            <CardContent className="p-4">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-orange-100 dark:bg-orange-900/50 flex items-center justify-center shrink-0">
                    <CalendarIcon className="h-5 w-5 text-orange-600 dark:text-orange-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-orange-900 dark:text-orange-200">
                      {staleStats.total} processo{staleStats.total !== 1 ? 's' : ''} sem atualização
                    </p>
                    <p className="text-xs text-orange-700 dark:text-orange-400">
                      {staleStats.critical > 0 && <span className="font-medium">{staleStats.critical} crítico{staleStats.critical !== 1 ? 's' : ''}</span>}
                      {staleStats.critical > 0 && staleStats.high > 0 && ' · '}
                      {staleStats.high > 0 && <span>{staleStats.high} atrasado{staleStats.high !== 1 ? 's' : ''}</span>}
                      {(staleStats.critical > 0 || staleStats.high > 0) && staleStats.medium > 0 && ' · '}
                      {staleStats.medium > 0 && <span>{staleStats.medium} urgente{staleStats.medium !== 1 ? 's' : ''}</span>}
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="border-orange-300 dark:border-orange-700 text-orange-700 dark:text-orange-300 hover:bg-orange-100 dark:hover:bg-orange-900/30 shrink-0"
                  onClick={() => setShowStaleList(!showStaleList)}
                  data-testid="stale-processes-action-btn"
                >
                  {showStaleList ? 'Esconder' : 'Ver processos'}
                </Button>
              </div>
              {showStaleList && staleStats.processes && (
                <div className="mt-4 border-t border-orange-200 dark:border-orange-800 pt-3 space-y-1 max-h-[400px] overflow-x-auto overflow-y-auto" data-testid="stale-processes-list">
                  <div className="grid grid-cols-12 gap-2 px-2 py-1.5 text-xs font-medium text-orange-800 dark:text-orange-300 border-b border-orange-200 dark:border-orange-700 min-w-[700px]">
                    <div className="col-span-3">Cliente</div>
                    <div className="col-span-2">Estado</div>
                    <div className="col-span-3">Consultor</div>
                    <div className="col-span-2">Dias s/ atualização</div>
                    <div className="col-span-2 text-right">Urgência</div>
                  </div>
                  {staleStats.processes.map((p) => (
                    <div
                      key={p.id}
                      className="grid grid-cols-12 gap-2 px-2 py-2 items-center rounded hover:bg-orange-100 dark:hover:bg-orange-900/30 cursor-pointer transition-colors min-w-[700px]"
                      onClick={() => navigate(`/process/${p.id}`)}
                      data-testid={`stale-process-${p.id}`}
                    >
                      <div className="col-span-3 text-sm font-medium truncate">{p.client_name || '—'}</div>
                      <div className="col-span-2">
                        <Badge variant="outline" className="text-xs">{p.status || '—'}</Badge>
                      </div>
                      <div className="col-span-3 text-sm text-muted-foreground truncate">{p.consultor_name || p.mediador_name || '—'}</div>
                      <div className="col-span-2 text-sm text-center">{p.days_since_update} dias</div>
                      <div className="col-span-2 text-right">
                        <Badge className={
                          p.urgency === 'critical' ? 'bg-red-600 text-white' :
                          p.urgency === 'high' ? 'bg-orange-500 text-white' :
                          'bg-yellow-500 text-white'
                        }>
                          {p.urgency === 'critical' ? 'Crítico' : p.urgency === 'high' ? 'Atrasado' : 'Urgente'}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="w-full overflow-x-auto scrollbar-hide -mx-1 px-1">
            <TabsList className="inline-flex w-max min-w-full h-auto p-1 gap-1">
              <TabsTrigger value="overview" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3" data-testid="tab-overview">
                <Eye className="h-4 w-4 shrink-0" /><span className="hidden sm:inline">Visão Geral</span><span className="sm:hidden">Geral</span>
              </TabsTrigger>
              <TabsTrigger value="calendar" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3" data-testid="tab-calendar">
                <CalendarIcon className="h-4 w-4 shrink-0" /><span className="hidden sm:inline">Calendário</span><span className="sm:hidden">Cal</span>
              </TabsTrigger>
              <TabsTrigger value="documents" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3" data-testid="tab-documents">
                <FileText className="h-4 w-4 shrink-0" /><span className="hidden sm:inline">Documentos</span><span className="sm:hidden">Doc</span>
              </TabsTrigger>
              <TabsTrigger value="users" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3" data-testid="tab-users">
                <Users className="h-4 w-4 shrink-0" /><span className="hidden sm:inline">Utilizadores</span><span className="sm:hidden">Users</span>
              </TabsTrigger>
              <TabsTrigger value="ai" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3" data-testid="tab-ai">
                <Sparkles className="h-4 w-4 shrink-0" /><span className="hidden sm:inline">Análise IA</span><span className="sm:hidden">IA</span>
              </TabsTrigger>
              <TabsTrigger value="clients" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3" data-testid="tab-search">
                <Search className="h-4 w-4 shrink-0" /><span className="hidden sm:inline">Pesquisar</span><span className="sm:hidden">Busca</span>
              </TabsTrigger>
              <TabsTrigger value="tasks" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3" data-testid="tab-tasks">
                <ClipboardList className="h-4 w-4 shrink-0" /><span className="hidden sm:inline">Tarefas</span><span className="sm:hidden">Tasks</span>
              </TabsTrigger>
              <TabsTrigger value="leads" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3" data-testid="tab-leads">
                <Building className="h-4 w-4 shrink-0" />Leads
              </TabsTrigger>
            </TabsList>
          </div>

          {/* Overview Tab */}
          <TabsContent value="overview" className="mt-4 space-y-4">
            <Card className="border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-base sm:text-lg flex items-center gap-2">
                  <LayoutGrid className="h-5 w-5 shrink-0" />
                  <span className="hidden sm:inline">Quadro Geral de Processos</span>
                  <span className="sm:hidden">Quadro Processos</span>
                </CardTitle>
                <CardDescription className="text-xs sm:text-sm">
                  {filteredProcesses.length} processos • Filtre por consultor, intermediário ou indexação
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                  <div className="space-y-2">
                    <Label>Filtrar por Consultor</Label>
                    <Select value={consultorFilter} onValueChange={setConsultorFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos os consultores" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos os consultores</SelectItem>
                        <SelectItem value="none">Nenhum (sem consultor)</SelectItem>
                        {consultors.map((c) => (<SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Filtrar por Intermediário</Label>
                    <Select value={mediadorFilter} onValueChange={setMediadorFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos os intermediários" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos os intermediários</SelectItem>
                        <SelectItem value="none">Nenhum (sem intermediário)</SelectItem>
                        {intermediarios.map((m) => (<SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Filtrar por Indexação</Label>
                    <Select value={indexacaoFilter} onValueChange={setIndexacaoFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos os indexação" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos os Indexação</SelectItem>
                        <SelectItem value="none">Nenhum (sem indexação)</SelectItem>
                        {indexacaoUsers.map((u) => (<SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <KanbanBoard 
                  token={localStorage.getItem('token')} 
                  user={user} 
                  consultorFilter={consultorFilter}
                  mediadorFilter={mediadorFilter}
                  indexacaoFilter={indexacaoFilter}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Calendar Tab */}
          <TabsContent value="calendar" className="mt-6">
            <CalendarTab
              calendarDeadlines={calendarDeadlines}
              consultors={consultors}
              intermediarios={intermediarios}
              users={users}
              currentUser={user}
              onCreateEvent={openCreateEvent}
              onDeleteEvent={handleDeleteEvent}
            />
          </TabsContent>

          {/* Documents Tab */}
          <TabsContent value="documents" className="mt-6">
            <DocumentsTab upcomingExpiries={upcomingExpiries} />
          </TabsContent>

          {/* Users Tab */}
          <TabsContent value="users" className="mt-6">
            <UsersTab users={users} />
          </TabsContent>

          {/* AI Analysis Tab */}
          <TabsContent value="ai" className="mt-6">
            <AIAnalysisTab />
          </TabsContent>

          {/* Client Search Tab */}
          <TabsContent value="clients" className="mt-6">
            <ClientSearchTab processes={processes} workflowStatuses={workflowStatuses} />
          </TabsContent>

          {/* Tasks Tab */}
          <TabsContent value="tasks" className="mt-6">
            <TasksPanel showCreateButton={true} maxHeight="600px" />
          </TabsContent>

          {/* Leads Tab */}
          <TabsContent value="leads" className="mt-6">
            <LeadsKanban />
          </TabsContent>
        </Tabs>

        {/* Create Event Dialog */}
        <CreateEventDialog
          open={isCreateEventDialogOpen}
          onOpenChange={setIsCreateEventDialogOpen}
          onSubmit={handleCreateEvent}
          processes={processes}
          staffUsers={staffUsers}
          currentUserId={user?.id}
          initialDate={selectedDateForEvent}
        />
      </div>
    </DashboardLayout>
  );
};

export default AdminDashboard;
