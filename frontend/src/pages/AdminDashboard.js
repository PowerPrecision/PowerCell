/**
 * AdminDashboard - Painel de Administração
 * Refatorizado com componentes modulares
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
import { useAuth } from "../contexts/AuthContext";
import { 
  Users, FolderOpen, Loader2, CheckCircle, XCircle, FileText, 
  Calendar as CalendarIcon, Eye, Sparkles, LayoutGrid, Search, ClipboardList, Building
} from "lucide-react";
import { toast } from "sonner";
import { 
  getStats, getUsers, getWorkflowStatuses, getOneDriveStatus, 
  getProcesses, getCalendarDeadlines, createDeadline, deleteDeadline, getUpcomingExpiries
} from "../services/api";
import KanbanBoard from "../components/KanbanBoard";
import LeadsKanban from "../components/LeadsKanban";
import { 
  CalendarTab, DocumentsTab, UsersTab, ClientSearchTab, 
  CreateEventDialog, AIAnalysisTab 
} from "../components/admin";
import { StatsGridSkeleton, TableSkeleton } from "../components/ui/skeletons";
import TasksPanel from "../components/TasksPanel";

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
  
  const [activeTab, setActiveTab] = useState("overview");
  const [consultorFilter, setConsultorFilter] = useState("all");
  const [mediadorFilter, setMediadorFilter] = useState("all");
  const [indexacaoFilter, setIndexacaoFilter] = useState("all");
  const [isCreateEventDialogOpen, setIsCreateEventDialogOpen] = useState(false);
  const [selectedDateForEvent, setSelectedDateForEvent] = useState(new Date());

  // Get staff users for assignment (excluindo admin e ceo)
  const staffUsers = useMemo(() => users.filter(u => 
    u.role !== "cliente" && 
    u.role !== "admin" && 
    u.role !== "ceo"
  ), [users]);
  const consultors = useMemo(() => users.filter(u => ["consultor", "diretor"].includes(u.role)), [users]);
  const intermediarios = useMemo(() => users.filter(u => ["mediador", "intermediario", "diretor"].includes(u.role)), [users]);
  const indexacaoUsers = useMemo(() => users.filter(u => u.role === "indexacao"), [users]);

  // Filter processes
  const filteredProcesses = useMemo(() => {
    return processes.filter(process => {
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

  useEffect(() => { fetchData(); }, []);
  useEffect(() => { fetchCalendarData(); }, [consultorFilter, mediadorFilter]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem("token");
      
      const [statsRes, usersRes, processesRes, statusesRes, storageRes, expiriesRes] = await Promise.all([
        getStats(),
        getUsers(),
        getProcesses(),
        getWorkflowStatuses(),
        fetch(`${process.env.REACT_APP_BACKEND_URL}/api/storage/status`, {
          headers: { Authorization: `Bearer ${token}` }
        }).then(r => r.json()).catch(() => ({ configured: false })),
        getUpcomingExpiries(60).catch(() => ({ data: [] })),
      ]);
      setStats(statsRes.data);
      setUsers(usersRes.data);
      setProcesses(processesRes.data);
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

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Total Processos</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{stats.total_processes || 0}</div>
            </CardContent>
          </Card>
          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Utilizadores</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <Users className="h-5 w-5 text-blue-600" />
                <span className="text-3xl font-bold">{users.length}</span>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Documentos a Expirar</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-amber-600" />
                <span className="text-3xl font-bold">{upcomingExpiries.length}</span>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Drive</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <FolderOpen className="h-5 w-5" />
                {storageStatus?.configured ? (
                  <Badge className="bg-green-100 dark:bg-green-900/50 text-green-800 dark:text-green-300">
                    <CheckCircle className="h-3 w-3 mr-1" />
                    {storageStatus.provider || 'Configurado'}
                  </Badge>
                ) : (
                  <Badge variant="secondary"><XCircle className="h-3 w-3 mr-1" />Não configurado</Badge>
                )}
              </div>
            </CardContent>
          </Card>
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
                <div className="mt-4 border-t border-orange-200 dark:border-orange-800 pt-3 space-y-1 max-h-[400px] overflow-y-auto" data-testid="stale-processes-list">
                  <div className="grid grid-cols-12 gap-2 px-2 py-1.5 text-xs font-medium text-orange-800 dark:text-orange-300 border-b border-orange-200 dark:border-orange-700">
                    <div className="col-span-3">Cliente</div>
                    <div className="col-span-2">Estado</div>
                    <div className="col-span-3">Consultor</div>
                    <div className="col-span-2">Dias s/ atualização</div>
                    <div className="col-span-2 text-right">Urgência</div>
                  </div>
                  {staleStats.processes.map((p) => (
                    <div
                      key={p.id}
                      className="grid grid-cols-12 gap-2 px-2 py-2 items-center rounded hover:bg-orange-100 dark:hover:bg-orange-900/30 cursor-pointer transition-colors"
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
