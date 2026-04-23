/**
 * StaffDashboard — Dashboard principal para utilizadores de equipa (consultores, mediadores).
 *
 * PORQUÊ: Vista centralizada do dia-a-dia da equipa, mostrando processos atribuídos, tarefas
 * pendentes, alertas urgentes, e acesso rápido a ações comuns.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import KanbanBoard from "../components/KanbanBoard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { Loader2, LayoutGrid, Calendar, Users, FileText, FileX, CheckCircle, XCircle, TrendingUp, ClipboardList, Plus, AlertTriangle, ShieldAlert, Mail, Send, Trash2, Edit3, ChevronRight, AlertCircle, Rss } from "lucide-react";
import TasksPanel from "../components/TasksPanel";
import { toast } from "sonner";
import { getStats, getUsers, getUpcomingExpiries, getCalendarDeadlines, createClientProcess, getAutoDrafts, sendAutoDraft, deleteAutoDraft, getWebmailStats } from "../services/api";
import SmartClientSearch from "../components/SmartClientSearch";
import TeamMural from "../components/TeamMural";
import { filterByAnyRole, filterByRole } from "../utils/roleUtils";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const roleLabels = {
  admin: "Administrador",
  ceo: "CEO",
  consultor: "Consultor",
  intermediario: "Intermediário de Crédito",
  mediador: "Intermediário de Crédito",
  diretor: "Diretor(a)",
  administrativo: "Administrativo(a)",
  cliente: "Cliente"
};

const StaffDashboard = () => {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [users, setUsers] = useState([]);
  const [expiries, setExpiries] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [dstiAlerts, setDstiAlerts] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Ler filtros da URL (persistidos na navegação)
  const [activeTab, setActiveTab] = useState(() => searchParams.get("tab") || "kanban");
  const [consultorFilter, setConsultorFilter] = useState(() => searchParams.get("consultor") || "all");
  const [mediadorFilter, setMediadorFilter] = useState(() => searchParams.get("mediador") || "all");
  const [indexacaoFilter, setIndexacaoFilter] = useState(() => searchParams.get("indexacao") || "all");
  const [parceiroFilter, setParceiroFilter] = useState(() => searchParams.get("parceiro") || "all");

  // Actualizar filtros na URL
  const updateTab = useCallback((tab) => {
    setActiveTab(tab);
    setSearchParams(prev => {
      if (tab === "kanban") prev.delete("tab");
      else prev.set("tab", tab);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const updateConsultorFilter = useCallback((value) => {
    setConsultorFilter(value);
    setSearchParams(prev => {
      if (value === "all") prev.delete("consultor");
      else prev.set("consultor", value);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const updateMediadorFilter = useCallback((value) => {
    setMediadorFilter(value);
    setSearchParams(prev => {
      if (value === "all") prev.delete("mediador");
      else prev.set("mediador", value);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const updateIndexacaoFilter = useCallback((value) => {
    setIndexacaoFilter(value);
    setSearchParams(prev => {
      if (value === "all") prev.delete("indexacao");
      else prev.set("indexacao", value);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const updateParceiroFilter = useCallback((value) => {
    setParceiroFilter(value);
    setSearchParams(prev => {
      if (value === "all") prev.delete("parceiro");
      else prev.set("parceiro", value);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);
  
  // Estado para rascunhos automáticos
  const [drafts, setDrafts] = useState([]);
  const [draftStats, setDraftStats] = useState({ total: 0, by_type: [] });
  const [draftLoading, setDraftLoading] = useState(false);
  const [expandedDraft, setExpandedDraft] = useState(null);
  const [sendingDraft, setSendingDraft] = useState(null);
  
  // Estado para estatísticas de webmail
  const [webmailStats, setWebmailStats] = useState({ unread_count: 0, sent_today_count: 0, drafts_count: 0 });

  // Estado para criação de nova lead
  const [showLeadDialog, setShowLeadDialog] = useState(false);
  const [creatingLead, setCreatingLead] = useState(false);
  const [newLead, setNewLead] = useState({
    client_name: "",
    client_email: "",
    client_phone: "",
    process_type: "credito_habitacao"
  });
  const [selectedClient, setSelectedClient] = useState(null);

  const isAdmin = user?.role === "admin";
  const isCeo = user?.role === "ceo";
  const isAdminOrCeo = isAdmin || isCeo;
  const canManageUsers = isAdminOrCeo;
  const canSeeAllStats = isAdminOrCeo;

  const consultors = useMemo(() => filterByAnyRole(users, ["consultor", "diretor"]), [users]);
  const intermediarios = useMemo(() => filterByAnyRole(users, ["mediador", "intermediario", "diretor"]), [users]);
  const indexacaoUsers = useMemo(() => filterByRole(users, "indexacao"), [users]);
  const parceiros = useMemo(() => filterByRole(users, "parceiro"), [users]);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [statsRes, usersRes, expiriesRes, deadlinesRes, webmailRes] = await Promise.all([
        getStats().catch(() => ({ data: {} })),
        getUsers().catch(() => ({ data: [] })),
        getUpcomingExpiries(60).catch(() => ({ data: [] })),
        getCalendarDeadlines().catch(() => ({ data: [] })),
        getWebmailStats().catch(() => ({ data: { unread_count: 0, sent_today_count: 0, drafts_count: 0 } })),
      ]);
      setStats(statsRes.data);
      setUsers(usersRes.data);
      setExpiries(expiriesRes.data);
      setDeadlines(deadlinesRes.data);
      setWebmailStats(webmailRes.data);
    } catch (error) {
      console.error("Error fetching data:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }

    // Carregar alertas DSTI em paralelo (não bloqueia o loading principal)
    fetchDSTIAlerts();
    // Carregar rascunhos em paralelo
    fetchDrafts();
  };

  const fetchDSTIAlerts = async () => {
    try {
      const res = await fetch(`${API_URL}/api/processes/dsti-alerts`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.enabled) {
          setDstiAlerts(data);
        }
      }
    } catch (err) {
      // Silenciar - DSTI pode estar desactivado
    }
  };

  // Carregar rascunhos automáticos
  const fetchDrafts = async () => {
    try {
      setDraftLoading(true);
      const res = await getAutoDrafts(10).catch(() => ({ data: { drafts: [], stats: { total: 0, by_type: [] } } }));
      setDrafts(res.data.drafts || []);
      setDraftStats(res.data.stats || { total: 0, by_type: [] });
    } catch (error) {
      console.error("Error fetching drafts:", error);
    } finally {
      setDraftLoading(false);
    }
  };

  // Enviar rascunho
  const handleSendDraft = async (draftId) => {
    setSendingDraft(draftId);
    try {
      await sendAutoDraft(draftId);
      toast.success("Rascunho enviado com sucesso!");
      fetchDrafts();
    } catch (error) {
      toast.error("Erro ao enviar rascunho");
    } finally {
      setSendingDraft(null);
    }
  };

  // Descartar rascunho
  const handleDeleteDraft = async (draftId) => {
    try {
      await deleteAutoDraft(draftId);
      toast.success("Rascunho descartado");
      fetchDrafts();
    } catch (error) {
      toast.error("Erro ao descartar rascunho");
    }
  };

  // Navegação para lista filtrada
  const goToFilteredList = (filter) => {
    navigate(`/processos-filtrados?filter=${filter}`);
  };

  // Criar novo processo/cliente
  const handleCreateLead = async () => {
    if (!selectedClient && !newLead.client_name.trim()) {
      toast.error("Selecione ou crie um cliente");
      return;
    }
    
    setCreatingLead(true);
    try {
      const clientName = selectedClient?.name || newLead.client_name;
      const clientEmail = selectedClient?.email || newLead.client_email;
      const clientPhone = selectedClient?.phone || newLead.client_phone;
      const clientNif = selectedClient?.nif || "";

      const payload = {
        process_type: newLead.process_type,
        personal_data: {
          nome_completo: clientName,
          email: clientEmail,
          telefone: clientPhone,
          ...(clientNif ? { nif: clientNif } : {}),
        }
      };

      // Se veio da pesquisa (cliente existente), passar client_id
      if (selectedClient?.id) {
        payload.client_id = selectedClient.id;
        payload.client_name = clientName;
        payload.client_email = clientEmail;
      }

      await createClientProcess(payload);
      
      toast.success(`Processo criado para "${clientName}"!`);
      setShowLeadDialog(false);
      setSelectedClient(null);
      setNewLead({
        client_name: "",
        client_email: "",
        client_phone: "",
        process_type: "credito_habitacao"
      });
      fetchData();
    } catch (error) {
      console.error("Erro ao criar lead:", error);
      toast.error(error.response?.data?.detail || "Erro ao criar processo");
    } finally {
      setCreatingLead(false);
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="space-y-6">
          <div className="flex items-start justify-between">
            <div className="space-y-1.5">
              <div className="h-7 w-40 bg-muted animate-pulse rounded" />
              <div className="h-4 w-56 bg-muted animate-pulse rounded" />
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            {[1,2,3,4,5,6,7].map(i => <div key={i} className="h-24 bg-muted animate-pulse rounded-lg" />)}
          </div>
          <div className="h-10 bg-muted animate-pulse rounded" />
          <div className="grid gap-4 md:grid-cols-2">
            {[1,2].map(i => <div key={i} className="h-48 bg-muted animate-pulse rounded-lg" />)}
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="staff-dashboard">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-bold truncate">Olá, {user?.name?.split(' ')[0]}</h1>
            <div className="text-muted-foreground flex items-center flex-wrap gap-2 mt-0.5">
              <Badge variant="outline" className="shrink-0">{roleLabels[user?.role] || user?.role}</Badge>
              <span className="text-sm">{canSeeAllStats ? `${stats.total_processes || 0} processos no sistema` : "Os seus processos atribuídos"}</span>
            </div>
          </div>
          {/* Botão Novo Cliente */}
          <Button 
            onClick={() => setShowLeadDialog(true)}
            className="bg-teal-600 hover:bg-teal-700 shrink-0"
            size="sm"
          >
            <Plus className="h-4 w-4 sm:mr-2" />
            <span className="hidden sm:inline">Novo Cliente</span>
          </Button>
        </div>

        {/* Quick Stats - Clickable cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
          <Card 
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate('/processos')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-3xl font-bold text-primary">{stats.total_processes || 0}</p>
                <p className="text-sm text-muted-foreground">Total</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="bg-blue-50 dark:bg-blue-950/30 border-blue-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => goToFilteredList('active')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <TrendingUp className="h-5 w-5 text-blue-600" />
                  <p className="text-3xl font-bold text-blue-600">{stats.active_processes || 0}</p>
                </div>
                <p className="text-sm text-blue-600/80">Ativos</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => goToFilteredList('concluded')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <CheckCircle className="h-5 w-5 text-emerald-600" />
                  <p className="text-3xl font-bold text-emerald-600">{stats.concluded_processes || 0}</p>
                </div>
                <p className="text-sm text-emerald-600/80">Concluídos</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="bg-red-50 dark:bg-red-950/30 border-red-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => goToFilteredList('dropped')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <XCircle className="h-5 w-5 text-red-600" />
                  <p className="text-3xl font-bold text-red-600">{stats.dropped_processes || 0}</p>
                </div>
                <p className="text-sm text-red-600/80">Desistências</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="bg-rose-50 dark:bg-rose-950/30 border-rose-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => goToFilteredList('no_indexacao')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <FileX className="h-5 w-5 text-rose-600" />
                  <p className="text-3xl font-bold text-rose-600">{stats.no_indexacao_processes || 0}</p>
                </div>
                <p className="text-sm text-rose-600/80">Sem Indexação</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate('/pendentes')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-3xl font-bold text-orange-500">{stats.total_pending || stats.pending_deadlines || 0}</p>
                <p className="text-sm text-muted-foreground">Pendentes</p>
                {(stats.pending_tasks > 0 || stats.pending_deadlines > 0) && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {stats.pending_tasks || 0} tarefas • {stats.pending_deadlines || 0} prazos
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
          {/* Email KPI Card */}
          <Card 
            className={`cursor-pointer hover:shadow-md transition-shadow ${webmailStats.unread_count > 0 ? "bg-amber-50 dark:bg-amber-950/30 border-amber-200" : "bg-emerald-50/50 dark:bg-emerald-950/20 border-emerald-200/50"}`}
            onClick={() => navigate('/webmail')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1 mb-1">
                  <Mail className="h-4 w-4" />
                </div>
                <p className={`text-3xl font-bold ${webmailStats.unread_count > 0 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                  {webmailStats.unread_count}
                </p>
                <p className="text-sm text-muted-foreground">
                  {webmailStats.unread_count === 1 ? "Email Não Lido" : "Emails Não Lidos"}
                </p>
                {(webmailStats.sent_today_count > 0 || webmailStats.drafts_count > 0) && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {webmailStats.sent_today_count > 0 && `${webmailStats.sent_today_count} enviado${webmailStats.sent_today_count !== 1 ? "s" : ""} hoje`}
                    {webmailStats.sent_today_count > 0 && webmailStats.drafts_count > 0 && " · "}
                    {webmailStats.drafts_count > 0 && `${webmailStats.drafts_count} rascunho${webmailStats.drafts_count !== 1 ? "s" : ""}`}
                  </p>
                )}
                <p className="text-xs font-medium text-primary mt-1.5 hover:underline">
                  Abrir Webmail
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* DSTI Alerts Banner */}
        {dstiAlerts && dstiAlerts.total > 0 && (
          <Card className="border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-900">
            <CardContent className="pt-4">
              <div className="flex items-center gap-2 mb-3">
                <ShieldAlert className="h-5 w-5 text-red-600" />
                <span className="font-semibold text-red-800 dark:text-red-200">
                  Alertas DSTI ({dstiAlerts.total} processo{dstiAlerts.total !== 1 ? "s" : ""})
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {dstiAlerts.processes.slice(0, 6).map((p) => (
                  <button
                    key={p.process_id}
                    onClick={() => navigate(`/processo/${p.process_id}`)}
                    className="flex items-center justify-between gap-2 p-2 rounded-lg bg-white dark:bg-gray-900 border border-red-100 dark:border-red-900 hover:bg-red-100 dark:hover:bg-red-950 transition-colors text-left"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {p.client_name}
                        <span className="text-muted-foreground font-normal ml-1">
                          #{p.process_number || "N/A"}
                        </span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        DSTI: <span className="font-semibold" style={{ color: p.risk_color }}>{p.dsti_pct}%</span>
                        {" · "}
                        Créditos: {p.prestacao_creditos}€ / {p.rendimento_bruto}€
                      </p>
                    </div>
                    <Badge
                      variant="outline"
                      className="shrink-0"
                      style={{ borderColor: p.risk_color, color: p.risk_color }}
                    >
                      {p.risk_level === "critico" ? "Crítico" : "Elevado"}
                    </Badge>
                  </button>
                ))}
              </div>
              {dstiAlerts.total > 6 && (
                <p className="text-xs text-muted-foreground mt-2 text-center">
                  ...e mais {dstiAlerts.total - 6} processos com DSTI elevado
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={updateTab}>
          <TabsList className="flex-wrap">
            <TabsTrigger value="kanban" className="gap-2">
              <LayoutGrid className="h-4 w-4" />
              <span className="hidden sm:inline">Quadro Geral</span>
              <span className="sm:hidden">Quadro</span>
            </TabsTrigger>
            <TabsTrigger value="tasks" className="gap-2">
              <ClipboardList className="h-4 w-4" />
              <span className="hidden sm:inline">Minhas Tarefas</span>
              <span className="sm:hidden">Tarefas</span>
            </TabsTrigger>
            <TabsTrigger value="calendar" className="gap-2">
              <Calendar className="h-4 w-4" />
              <span className="hidden sm:inline">Calendário</span>
              <span className="sm:hidden">Cal.</span>
            </TabsTrigger>
            <TabsTrigger value="documents" className="gap-2">
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Documentos</span>
              <span className="sm:hidden">Docs</span>
            </TabsTrigger>
            {draftStats.total > 0 && (
              <TabsTrigger value="drafts" className="gap-2">
                <Mail className="h-4 w-4" />
                <span className="hidden sm:inline">Rascunhos</span>
                <span className="sm:hidden">Rasc.</span>
                <Badge className="bg-orange-500 text-white text-[10px] px-1.5 py-0 min-w-[20px] text-center">
                  {draftStats.total}
                </Badge>
              </TabsTrigger>
            )}
            <TabsTrigger value="mural" className="gap-2">
              <Rss className="h-4 w-4" />
              <span className="hidden sm:inline">Mural</span>
              <span className="sm:hidden">Mural</span>
            </TabsTrigger>
            {canManageUsers && (
              <TabsTrigger value="users" className="gap-2">
                <Users className="h-4 w-4" />
                <span className="hidden sm:inline">Utilizadores</span>
                <span className="sm:hidden">Users</span>
              </TabsTrigger>
            )}
          </TabsList>

          {/* Mural da Equipa Tab */}
          <TabsContent value="mural" className="mt-6">
            <TeamMural />
          </TabsContent>

          {/* Kanban Tab */}
          <TabsContent value="kanban" className="mt-6">
            <Card className="border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-base sm:text-lg flex items-center gap-2">
                  <LayoutGrid className="h-5 w-5 shrink-0" />
                  Quadro Geral de Processos
                </CardTitle>
                <CardDescription className="text-xs sm:text-sm">
                  Filtre por consultor, intermediário, indexação ou parceiro
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
                  <div className="space-y-2">
                    <Label>Filtrar por Consultor</Label>
                    <Select value={consultorFilter} onValueChange={updateConsultorFilter}>
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
                    <Select value={mediadorFilter} onValueChange={updateMediadorFilter}>
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
                    <Select value={indexacaoFilter} onValueChange={updateIndexacaoFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos os indexação" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos os Indexação</SelectItem>
                        <SelectItem value="none">Nenhum (sem indexação)</SelectItem>
                        {indexacaoUsers.map((u) => (<SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Filtrar por Parceiro</Label>
                    <Select value={parceiroFilter} onValueChange={updateParceiroFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos os parceiros" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos os Parceiros</SelectItem>
                        <SelectItem value="none">Nenhum (sem parceiro)</SelectItem>
                        {parceiros.map((p) => (<SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <KanbanBoard 
                  token={token} 
                  user={user} 
                  consultorFilter={consultorFilter}
                  mediadorFilter={mediadorFilter}
                  indexacaoFilter={indexacaoFilter}
                  parceiroFilter={parceiroFilter}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Tasks Tab - Minhas Tarefas */}
          <TabsContent value="tasks" className="mt-6">
            <TasksPanel 
              showCreateButton={true}
              compact={false}
              maxHeight="600px"
              showOnlyMyTasks={true}
            />
          </TabsContent>

          {/* Calendar Tab */}
          <TabsContent value="calendar" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Próximos Prazos</CardTitle>
                <CardDescription>Prazos e eventos agendados</CardDescription>
              </CardHeader>
              <CardContent>
                {deadlines.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">Nenhum prazo agendado</p>
                ) : (
                  <div className="space-y-3">
                    {[...deadlines]
                      .sort((a, b) => new Date(a.due_date) - new Date(b.due_date))
                      .slice(0, 10)
                      .map((deadline) => (
                      <div key={deadline.id} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                        <div>
                          <p className="font-medium">{deadline.title}</p>
                          <p className="text-sm text-muted-foreground">{deadline.client_name}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-medium">{new Date(deadline.due_date).toLocaleDateString('pt-PT')}</p>
                          <Badge variant={deadline.priority === "high" ? "destructive" : "outline"}>
                            {deadline.priority === "high" ? "Alta" : deadline.priority === "medium" ? "Média" : "Baixa"}
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Documents Tab */}
          <TabsContent value="documents" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Documentos a Expirar</CardTitle>
                <CardDescription>Documentos dos seus clientes próximos da data de validade (60 dias), ordenados por data</CardDescription>
              </CardHeader>
              <CardContent>
                {expiries.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">Nenhum documento a expirar nos próximos 60 dias</p>
                ) : (
                  <div className="space-y-4">
                    {/* Ordenar documentos por data de expiração e agrupar por cliente */}
                    {(() => {
                      // Ordenar todos os documentos por data de expiração (crescente)
                      const sortedDocs = [...expiries].sort((a, b) => 
                        new Date(a.expiry_date) - new Date(b.expiry_date)
                      );
                      
                      // Agrupar por cliente mantendo a ordem
                      const grouped = sortedDocs.reduce((acc, doc) => {
                        const clientKey = doc.client_name || 'Sem Cliente';
                        if (!acc[clientKey]) {
                          acc[clientKey] = {
                            client_name: doc.client_name,
                            process_id: doc.process_id,
                            documents: [],
                            earliestExpiry: doc.expiry_date
                          };
                        }
                        acc[clientKey].documents.push(doc);
                        return acc;
                      }, {});
                      
                      // Ordenar grupos pelo documento mais próximo a expirar
                      const sortedGroups = Object.entries(grouped).sort((a, b) => 
                        new Date(a[1].earliestExpiry) - new Date(b[1].earliestExpiry)
                      );
                      
                      return sortedGroups.map(([clientName, clientData]) => {
                        const earliestDays = Math.ceil((new Date(clientData.earliestExpiry) - new Date()) / (1000 * 60 * 60 * 24));
                        const borderColor = earliestDays <= 7 ? 'border-l-red-500' : earliestDays <= 30 ? 'border-l-amber-500' : 'border-l-blue-500';
                        
                        return (
                          <div key={clientName} className={`border-l-4 ${borderColor} rounded-lg bg-muted/20 overflow-hidden`}>
                            <div className="py-2 px-4 bg-muted/40 flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <Users className="h-4 w-4 text-blue-900" />
                                {clientData.process_id ? (
                                  <span 
                                    className="font-semibold text-blue-900 hover:text-blue-700 cursor-pointer hover:underline"
                                    onClick={() => navigate(`/process/${clientData.process_id}`)}
                                  >
                                    {clientName}
                                  </span>
                                ) : (
                                  <span className="font-semibold">{clientName}</span>
                                )}
                                <Badge variant="outline">{clientData.documents.length} doc(s)</Badge>
                              </div>
                            </div>
                            <div className="p-3 space-y-2">
                              {clientData.documents.map((doc) => {
                                const daysUntil = Math.ceil((new Date(doc.expiry_date) - new Date()) / (1000 * 60 * 60 * 24));
                                const urgencyClass = daysUntil <= 7 ? 'bg-red-50 border-red-200 text-red-800' : 
                                                     daysUntil <= 30 ? 'bg-amber-50 border-amber-200 text-amber-800' : 
                                                     'bg-blue-50 border-blue-200 text-blue-800';
                                return (
                                  <div key={doc.id} className={`flex items-center justify-between p-2 rounded border ${urgencyClass}`}>
                                    <div className="flex items-center gap-2">
                                      <FileText className="h-4 w-4" />
                                      <span className="font-medium text-sm">{doc.document_name}</span>
                                      <Badge variant="outline" className="text-xs">{doc.document_type}</Badge>
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs">{new Date(doc.expiry_date).toLocaleDateString('pt-PT')}</span>
                                      <Badge className={daysUntil <= 7 ? 'bg-red-500' : daysUntil <= 30 ? 'bg-amber-500' : 'bg-blue-500'}>
                                        {daysUntil}d
                                      </Badge>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Auto-Drafts Tab - Rascunhos Pendentes */}
          {draftStats.total > 0 && (
            <TabsContent value="drafts" className="mt-6">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <Mail className="h-5 w-5" />
                        Rascunhos Pendentes
                      </CardTitle>
                      <CardDescription>
                        {draftStats.total} rascunho(s) de e-mail gerados automaticamente pela IA
                      </CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={fetchDrafts} disabled={draftLoading}>
                      {draftLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <AlertCircle className="h-4 w-4" />}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {drafts.length === 0 ? (
                    <p className="text-muted-foreground text-center py-8">Nenhum rascunho pendente</p>
                  ) : (
                    <div className="space-y-3">
                      {drafts.map((draft) => {
                        const isExpanded = expandedDraft === draft.id;
                        return (
                          <div key={draft.id} className="border rounded-lg overflow-hidden hover:shadow-sm transition-shadow">
                            {/* Header - always visible */}
                            <div 
                              className="p-3 bg-muted/20 cursor-pointer flex items-center justify-between"
                              onClick={() => setExpandedDraft(isExpanded ? null : draft.id)}
                            >
                              <div className="flex items-center gap-3 min-w-0 flex-1">
                                <div className="w-8 h-8 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center shrink-0">
                                  <Mail className="h-4 w-4 text-orange-600" />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <p className="font-medium text-sm truncate">{draft.subject}</p>
                                  <div className="flex items-center gap-2 mt-0.5">
                                    <span className="text-xs text-muted-foreground">
                                      {draft.client_name || "Cliente"}
                                    </span>
                                    <Badge variant="outline" className="text-[10px]">
                                      {draft.auto_draft_doc_label || draft.auto_draft_doc_type}
                                    </Badge>
                                  </div>
                                </div>
                              </div>
                              <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform shrink-0 ${isExpanded ? "rotate-90" : ""}`} />
                            </div>

                            {/* Expanded content */}
                            {isExpanded && (
                              <div className="p-4 border-t space-y-3">
                                {/* Email details */}
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                                  <div>
                                    <span className="text-muted-foreground">Para:</span>{" "}
                                    <span className="font-medium">{draft.to_emails?.[0] || "N/A"}</span>
                                  </div>
                                  <div>
                                    <span className="text-muted-foreground">Processo:</span>{" "}
                                    <span 
                                      className="font-medium text-primary hover:underline cursor-pointer"
                                      onClick={(e) => { e.stopPropagation(); navigate(`/process/${draft.process_id}`); }}
                                    >
                                      {draft.process_number || draft.process_id}
                                    </span>
                                  </div>
                                </div>

                                {/* Email body preview */}
                                <div className="bg-muted/30 rounded-lg p-3">
                                  <p className="text-sm whitespace-pre-wrap">{draft.body}</p>
                                </div>

                                {/* Action buttons */}
                                <div className="flex items-center gap-2 pt-2">
                                  <Button 
                                    size="sm" 
                                    className="bg-teal-600 hover:bg-teal-700"
                                    onClick={(e) => { e.stopPropagation(); handleSendDraft(draft.id); }}
                                    disabled={sendingDraft === draft.id}
                                  >
                                    {sendingDraft === draft.id ? (
                                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                                    ) : (
                                      <Send className="h-4 w-4 mr-1" />
                                    )}
                                    Enviar
                                  </Button>
                                  <Button 
                                    size="sm" 
                                    variant="outline"
                                    onClick={(e) => { e.stopPropagation(); navigate(`/process/${draft.process_id}`); }}
                                  >
                                    Ver Processo
                                  </Button>
                                  <Button 
                                    size="sm" 
                                    variant="ghost"
                                    className="text-red-600 hover:text-red-700 hover:bg-red-50 ml-auto"
                                    onClick={(e) => { e.stopPropagation(); handleDeleteDraft(draft.id); }}
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </Button>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )}

          {/* Users Tab (Admin only) */}
          {canManageUsers && (
            <TabsContent value="users" className="mt-6">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Gestão de Utilizadores</CardTitle>
                      <CardDescription>
                        {stats.active_users || 0} ativos • {stats.inactive_users || 0} inativos
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {users.map((u) => (
                      <div key={u.id} className={`flex items-center justify-between p-3 rounded-lg ${u.is_active === false ? 'bg-red-50 dark:bg-red-950/20' : 'bg-muted/30'}`}>
                        <div className="flex items-center gap-3">
                          <div className={`w-2 h-2 rounded-full ${u.is_active === false ? 'bg-red-500' : 'bg-emerald-500'}`} />
                          <div>
                            <p className={`font-medium ${u.is_active === false ? 'text-muted-foreground' : ''}`}>
                              {u.name}
                              {u.is_active === false && <span className="text-xs text-red-500 ml-2">(Inativo)</span>}
                            </p>
                            <p className="text-sm text-muted-foreground">{u.email}</p>
                          </div>
                        </div>
                        <Badge variant={u.is_active === false ? "secondary" : "default"}>
                          {roleLabels[u.role] || u.role}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          )}

        </Tabs>

        {/* Dialog para criar novo processo/cliente */}
        <Dialog open={showLeadDialog} onOpenChange={(open) => {
          if (!open) { setSelectedClient(null); setNewLead({ client_name: "", client_email: "", client_phone: "", process_type: "credito_habitacao" }); }
          setShowLeadDialog(open);
        }}>
          <DialogContent className="sm:max-w-lg w-[calc(100vw-2rem)]" aria-describedby="create-lead-description">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Plus className="h-5 w-5" />
                Novo Processo
              </DialogTitle>
              <DialogDescription id="create-lead-description">
                Pesquise um cliente existente ou crie um novo. O processo será associado ao cliente selecionado.
              </DialogDescription>
            </DialogHeader>
            
            <div className="space-y-4 py-4">
              <SmartClientSearch
                selectedClient={selectedClient}
                onClientSelect={(client) => {
                  setSelectedClient(client);
                  setNewLead(prev => ({
                    ...prev,
                    client_name: client.name || "",
                    client_email: client.email || "",
                    client_phone: client.phone || "",
                  }));
                }}
                onClearClient={() => {
                  setSelectedClient(null);
                  setNewLead(prev => ({ ...prev, client_name: "", client_email: "", client_phone: "" }));
                }}
              />
              
              <div className="space-y-2">
                <Label htmlFor="process_type">Tipo de Processo</Label>
                <Select 
                  value={newLead.process_type} 
                  onValueChange={(v) => setNewLead({ ...newLead, process_type: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="credito_habitacao">Crédito Habitação</SelectItem>
                    <SelectItem value="credito_pessoal">Crédito Pessoal</SelectItem>
                    <SelectItem value="credito_consolidado">Crédito Consolidado</SelectItem>
                    <SelectItem value="credito_automovel">Crédito Automóvel</SelectItem>
                    <SelectItem value="transferencia_credito">Transferência de Crédito</SelectItem>
                    <SelectItem value="imobiliario">Imobiliário</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowLeadDialog(false)}>
                Cancelar
              </Button>
              <Button 
                onClick={handleCreateLead} 
                disabled={creatingLead || !selectedClient}
                className="bg-teal-600 hover:bg-teal-700"
              >
                {creatingLead ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    A criar...
                  </>
                ) : "Criar Processo"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default StaffDashboard;

