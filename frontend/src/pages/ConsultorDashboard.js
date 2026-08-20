/**
 * ConsultorDashboard — Painel principal (Progressive Disclosure)
 *
 * Zona 1 (Foco): Tarefas Pendentes — prazos, tarefas e rascunhos
 * Zona 2 (Negócio): Funil visual de macro-fases (recharts)
 * Zona 3 (Exploração): Tabs — Clientes | Mural/Feed | Novidades
 */
import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Users, Eye, Plus, AlertTriangle, Mail,
  TrendingUp, ClipboardList, Rss, Calendar,
  MessageSquare, Inbox, ArrowRight, Megaphone, FileEdit
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  StatusBadge,
  SearchFilters,
  ProcessTable,
  ExpiringDocumentsList,
  AddExpiryDialog,
  LoadingSpinner,
  AIAnalysisTab,
  useDashboardData,
  useDocumentManagement,
  TYPE_LABELS,
  DOCUMENT_TYPES_CONSULTOR,
  formatDate
} from "../components/dashboard/DashboardShared";
import { PageHeader } from "../components/shared/PageHeader";
import { EmptyState } from "../components/ui/EmptyState";
import { processDeepLink } from "../utils/processDeepLink";
import SafeChartContainer from "../components/ui/SafeChartContainer";
import TasksPanel from "../components/TasksPanel";
import TeamMural from "../components/TeamMural";
import { getWebmailStats, getCalendarDeadlines, getCommunicationsFeed, getSystemChangelogs, getAutoDrafts } from "../services/api";
import { safeString } from "../utils/safeString";
import { safeDateStr } from "../lib/utils";
import { sanitizeHtml } from "../utils/sanitize";
import { markdownToHtml } from "../utils/markdown";
import { getDraftNavigationTarget, PROCESS_DRAFT_STATUSES } from "../utils/draftNavigation";
import AgendaCalendar from "../components/calendar/AgendaCalendar";
import { isTeamCalendarRole } from "../utils/agendaCalendar";

/** Macro-fases do funil (agrupam estados finos do workflow) */
const FUNNEL_MACRO = [
  {
    key: "novo",
    label: "Novo",
    statuses: ["clientes_espera", "fase_documental", "fase_documental_ii", "documentacao"],
    color: "hsl(var(--chart-4))",
  },
  {
    key: "analise",
    label: "Em Análise",
    statuses: [
      "enviado_bruno", "enviado_luis", "enviado_bcp_rui", "entradas_precision",
      "fase_bancaria", "fase_visitas", "analise", "pre_aprovacao",
    ],
    color: "hsl(var(--chart-1))",
  },
  {
    key: "aprovado",
    label: "Aprovado",
    statuses: [
      "ch_aprovado", "fase_escritura", "escritura_agendada",
      "credito_aprovado", "pedido_avaliacao", "avaliacao", "cpcv", "minuta", "escritura",
      "aprovado",
    ],
    color: "hsl(var(--chart-2))",
  },
  {
    key: "concluido",
    label: "Concluído",
    statuses: ["concluidos", "concluido", "escritura"],
    color: "hsl(var(--chart-3))",
  },
];

const DRAFT_STATUSES = PROCESS_DRAFT_STATUSES;

const roleLabels = {
  admin: "Administrador",
  ceo: "CEO",
  consultor: "Consultor",
  intermediario: "Intermediário de Crédito",
  diretor: "Diretor(a)",
  administrativo: "Administrativo(a)",
  indexacao: "Indexação",
};

const ConsultorDashboard = () => {
  const navigate = useNavigate();
  const { user, effectiveRole } = useAuth();
  const [exploreTab, setExploreTab] = useState("clients");

  const [webmailStats, setWebmailStats] = useState({ unread_count: 0, sent_today_count: 0, drafts_count: 0 });
  const [emailDrafts, setEmailDrafts] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [commsFeed, setCommsFeed] = useState({
    portal_messages: [], unread_emails: [], portal_unread_count: 0, email_unread_count: 0,
  });
  const [changelog, setChangelog] = useState(null);

  const {
    processes,
    filteredProcesses,
    workflowStatuses,
    upcomingExpiries,
    loading,
    searchTerm,
    setSearchTerm,
    statusFilter,
    setStatusFilter,
    fetchData
  } = useDashboardData();

  const {
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
    loadClientAndAnalyze,
    refreshAiAnalysis,
    analyzeDocumentWithAI
  } = useDocumentManagement(fetchData);

  useEffect(() => {
    getWebmailStats("personal")
      .then((res) => setWebmailStats(res.data || { unread_count: 0, sent_today_count: 0, drafts_count: 0 }))
      .catch(() => {});
    getCalendarDeadlines()
      .then((res) => setDeadlines(res.data || []))
      .catch(() => {});
    getCommunicationsFeed()
      .then((res) => setCommsFeed(res.data || {
        portal_messages: [], unread_emails: [], portal_unread_count: 0, email_unread_count: 0,
      }))
      .catch(() => {});
    getAutoDrafts(5)
      .then((res) => setEmailDrafts(res.data?.drafts || []))
      .catch(() => {});
    getSystemChangelogs(1)
      .then((res) => {
        const data = res.data;
        if (Array.isArray(data) && data.length > 0) setChangelog(data[0]);
      })
      .catch(() => {});
  }, []);

  const draftProcesses = useMemo(
    () => (processes || []).filter((p) => DRAFT_STATUSES.has(p.status)).slice(0, 5),
    [processes]
  );

  const dashboardDrafts = useMemo(() => {
    const emails = (emailDrafts || []).slice(0, 5).map((d) => ({
      ...d,
      kind: "email",
      _label: d.subject || d.client_name || "Rascunho de email",
      _sub: d.client_name || (Array.isArray(d.to_emails) ? d.to_emails[0] : "") || "Email",
    }));
    const procs = draftProcesses.map((p) => ({
      ...p,
      kind: p.status === "pre_registo" || p.is_lead ? "lead" : "process",
      _label: p.client_name || "Processo em rascunho",
      _sub: p.client_email || p.status || "",
    }));
    return [...emails, ...procs].slice(0, 8);
  }, [emailDrafts, draftProcesses]);

  const upcomingDeadlines = useMemo(() => {
    return [...(deadlines || [])]
      .sort((a, b) => new Date(safeDateStr(a.due_date)) - new Date(safeDateStr(b.due_date)))
      .slice(0, 5);
  }, [deadlines]);

  const funnelData = useMemo(() => {
    const list = processes || [];
    return FUNNEL_MACRO.map((phase) => {
      const statusSet = new Set(phase.statuses);
      const count = list.filter((p) => statusSet.has(p.status)).length;
      return {
        key: phase.key,
        name: phase.label,
        value: count,
        color: phase.color,
        statuses: phase.statuses,
      };
    });
  }, [processes]);

  const handleFunnelClick = (entry) => {
    if (!entry?.statuses?.length) return;
    // Prefer first matching workflow status that exists in data / config
    const match = entry.statuses.find((s) =>
      (workflowStatuses || []).some((w) => w.name === s)
      || (processes || []).some((p) => p.status === s)
    ) || entry.statuses[0];
    setStatusFilter(match);
    setExploreTab("clients");
  };

  if (loading) {
    return (
      <DashboardLayout>
        <LoadingSpinner />
      </DashboardLayout>
    );
  }

  const firstName = user?.name?.split(" ")[0] || "";
  const roleLabel = roleLabels[user?.role] || user?.role || "";

  const tableColumns = [
    { key: "client", label: "Cliente" },
    { key: "email", label: "Email" },
    { key: "type", label: "Tipo" },
    { key: "status", label: "Estado" },
    { key: "date", label: "Data" },
    { key: "actions", label: "Ações", className: "text-right" }
  ];

  const renderRow = (process) => (
    <tr key={process.id} className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
      <td className="p-2 sm:p-3 lg:p-4 align-middle font-medium">{safeString(process.client_name)}</td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">{safeString(process.client_email)}</td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">
        <Badge variant="outline">
          {TYPE_LABELS[process.process_type] || (typeof process.process_type === "string" ? process.process_type : "")}
        </Badge>
      </td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">
        <StatusBadge status={process.status} workflowStatuses={workflowStatuses} />
      </td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle text-sm text-muted-foreground">
        {formatDate(process.created_at)}
      </td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle text-right">
        <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => navigate(`/process/${process.id}`)}>
          <Eye className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => openAddExpiryDialog(process.id)}>
          <Plus className="h-4 w-4" />
        </Button>
      </td>
    </tr>
  );

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="consultor-dashboard">

        <PageHeader
          title={`Olá, ${firstName}`}
          description={
            <span className="flex flex-wrap items-center gap-2">
              {roleLabel && <Badge variant="secondary" className="text-xs">{roleLabel}</Badge>}
              <span>Foque-se no que importa — explore o resto quando precisar</span>
            </span>
          }
          actions={
            <div className="flex flex-wrap gap-2">
              {webmailStats.unread_count > 0 && (
                <Button variant="outline" size="sm" className="gap-2" onClick={() => navigate("/webmail")}>
                  <Mail className="h-4 w-4" />
                  {webmailStats.unread_count} não lido{webmailStats.unread_count !== 1 ? "s" : ""}
                </Button>
              )}
              <Button onClick={() => navigate("/kanban")} variant="outline" className="gap-2">
                <TrendingUp className="h-4 w-4" />
                Quadro Geral
              </Button>
            </div>
          }
        />

        {/* ── Zona 1: Foco — Tarefas Pendentes ── */}
        <Card className="border-border" data-testid="pending-tasks-zone">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <ClipboardList className="h-5 w-5 text-primary" />
              Tarefas Pendentes
            </CardTitle>
            <CardDescription>
              Prazos, tarefas e processos em rascunho — o essencial do dia
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 lg:gap-6">
              {/* Prazos */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium flex items-center gap-2 text-foreground">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    Prazos
                  </h3>
                  <Badge variant="secondary" className="text-xs">{upcomingDeadlines.length}</Badge>
                </div>
                {upcomingDeadlines.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4">Sem prazos próximos</p>
                ) : (
                  <ul className="space-y-2">
                    {upcomingDeadlines.map((deadline) => {
                      const dueDate = new Date(safeDateStr(deadline.due_date));
                      const daysLeft = Math.ceil((dueDate - new Date()) / (1000 * 60 * 60 * 24));
                      return (
                        <li
                          key={deadline.id}
                          className="flex items-start justify-between gap-2 rounded-md border border-border bg-muted/30 p-2.5"
                        >
                          <div className="min-w-0">
                            <p className="text-sm font-medium truncate">
                              {deadline.title || deadline.description || "Prazo"}
                            </p>
                            <p className="text-xs text-muted-foreground">{formatDate(deadline.due_date)}</p>
                          </div>
                          <span className={`text-xs shrink-0 ${daysLeft < 0 ? "text-destructive" : "text-muted-foreground"}`}>
                            {daysLeft < 0 ? `${Math.abs(daysLeft)}d atrasado` : daysLeft === 0 ? "Hoje" : `em ${daysLeft}d`}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              {/* Tarefas */}
              <div className="space-y-3 min-h-0">
                <h3 className="text-sm font-medium flex items-center gap-2 text-foreground">
                  <ClipboardList className="h-4 w-4 text-muted-foreground" />
                  As minhas tarefas
                </h3>
                <TasksPanel
                  showCreateButton={true}
                  compact={true}
                  maxHeight="280px"
                  showOnlyMyTasks={true}
                />
              </div>

              {/* Rascunhos */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium flex items-center gap-2 text-foreground">
                    <FileEdit className="h-4 w-4 text-muted-foreground" />
                    Em rascunho
                  </h3>
                  <Badge variant="secondary" className="text-xs">{dashboardDrafts.length}</Badge>
                </div>
                {dashboardDrafts.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4">Nenhum processo em fase inicial</p>
                ) : (
                  <ul className="space-y-2">
                    {dashboardDrafts.map((p) => (
                      <li key={`${p.kind || "item"}-${p.id}`}>
                        <button
                          type="button"
                          className="w-full flex items-center justify-between gap-2 rounded-md border border-border bg-muted/30 p-2.5 text-left hover:bg-muted/50 transition-colors"
                          onClick={() => {
                            const { href } = getDraftNavigationTarget(p);
                            navigate(href);
                          }}
                        >
                          <div className="min-w-0">
                            <p className="text-sm font-medium truncate">{safeString(p._label || p.client_name)}</p>
                            <p className="text-xs text-muted-foreground truncate">{safeString(p._sub || p.client_email)}</p>
                          </div>
                          <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── Zona 2: Negócio — Funil ── */}
        <Card className="border-border" data-testid="pipeline-funnel-zone">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-primary" />
              Funil do Pipeline
            </CardTitle>
            <CardDescription>
              Macro-fases dos seus processos — clique para filtrar a tabela de clientes
            </CardDescription>
          </CardHeader>
          <CardContent>
            {funnelData.every((d) => d.value === 0) ? (
              <EmptyState
                icon={TrendingUp}
                message="Ainda não há processos para montar o funil"
                className="py-10"
              />
            ) : (
              <SafeChartContainer className="h-[240px] min-w-0">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={funnelData}
                    layout="vertical"
                    margin={{ left: 8, right: 24, top: 8, bottom: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border" />
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
                    <YAxis dataKey="name" type="category" width={96} tick={{ fontSize: 12 }} />
                    <Tooltip
                      formatter={(value) => [`${value} processos`, "Quantidade"]}
                      contentStyle={{
                        borderRadius: "8px",
                        fontSize: "13px",
                        border: "1px solid hsl(var(--border))",
                        background: "hsl(var(--card))",
                        color: "hsl(var(--card-foreground))",
                      }}
                    />
                    <Bar
                      dataKey="value"
                      radius={[0, 6, 6, 0]}
                      name="Processos"
                      cursor="pointer"
                      onClick={(data) => handleFunnelClick(data)}
                    >
                      {funnelData.map((entry) => (
                        <Cell key={entry.key} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </SafeChartContainer>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {funnelData.map((phase) => (
                <Button
                  key={phase.key}
                  variant={statusFilter && phase.statuses.includes(statusFilter) ? "default" : "outline"}
                  size="sm"
                  className="gap-2"
                  onClick={() => handleFunnelClick(phase)}
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: phase.color }}
                    aria-hidden
                  />
                  {phase.name}
                  <Badge variant="secondary" className="text-[10px] px-1.5">{phase.value}</Badge>
                </Button>
              ))}
              {statusFilter !== "all" && (
                <Button variant="ghost" size="sm" onClick={() => setStatusFilter("all")}>
                  Limpar filtro
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ── Zona 3: Exploração — Tabs ── */}
        <Tabs value={exploreTab} onValueChange={setExploreTab} data-testid="explore-tabs-zone">
          <TabsList className="flex-wrap h-auto">
            <TabsTrigger value="clients" className="gap-2">
              <Users className="h-4 w-4" />
              Clientes
            </TabsTrigger>
            <TabsTrigger value="calendar" className="gap-2">
              <Calendar className="h-4 w-4" />
              Calendário
            </TabsTrigger>
            <TabsTrigger value="feed" className="gap-2">
              <Rss className="h-4 w-4" />
              Mural & Feed
              {(commsFeed.portal_unread_count + commsFeed.email_unread_count) > 0 && (
                <Badge className="ml-1 h-5 min-w-5 px-1.5 text-[10px]">
                  {commsFeed.portal_unread_count + commsFeed.email_unread_count}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="changelog" className="gap-2">
              <Megaphone className="h-4 w-4" />
              Novidades
            </TabsTrigger>
            <TabsTrigger value="documents" className="gap-2">
              <AlertTriangle className="h-4 w-4" />
              Docs a expirar
            </TabsTrigger>
            <TabsTrigger value="ai" className="gap-2">
              Análise IA
            </TabsTrigger>
          </TabsList>

          <TabsContent value="clients" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <div className="flex flex-col sm:flex-row gap-4 justify-between">
                  <div>
                    <CardTitle className="text-lg">Os Meus Clientes</CardTitle>
                    <CardDescription>Processos atribuídos a si</CardDescription>
                  </div>
                  <SearchFilters
                    searchTerm={searchTerm}
                    setSearchTerm={setSearchTerm}
                    statusFilter={statusFilter}
                    setStatusFilter={setStatusFilter}
                    workflowStatuses={workflowStatuses}
                  />
                </div>
              </CardHeader>
              <CardContent>
                <ProcessTable
                  processes={filteredProcesses}
                  columns={tableColumns}
                  renderRow={renderRow}
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="calendar" className="mt-6">
            <AgendaCalendar
              events={deadlines}
              compact
              isTeamView={isTeamCalendarRole(effectiveRole)}
              viewerId={user?.id}
              title="Agenda"
              description="Próximas marcações — abra o calendário completo para a vista mensal e semanal"
              headerAction={
                <Button variant="outline" size="sm" className="h-8" onClick={() => navigate("/calendario")}>
                  Abrir calendário
                </Button>
              }
            />
          </TabsContent>

          <TabsContent value="feed" className="mt-6 space-y-6">
            <Card className="border-border">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Rss className="h-5 w-5" />
                  Mural da Equipa
                </CardTitle>
                <CardDescription className="text-xs">
                  Novidades, avisos e comunicação interna
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <TeamMural />
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="border-border">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <MessageSquare className="h-5 w-5 text-accent-foreground" />
                    Mensagens do Portal
                    {commsFeed.portal_unread_count > 0 && (
                      <Badge variant="secondary">{commsFeed.portal_unread_count}</Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  {commsFeed.portal_messages.length === 0 ? (
                    <EmptyState message="Sem mensagens por ler" className="py-8" />
                  ) : (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {commsFeed.portal_messages.map((msg) => (
                        <button
                          type="button"
                          key={msg.id}
                          className="w-full flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/30 hover:bg-muted/50 transition-colors text-left"
                          onClick={() => navigate(processDeepLink(msg.process_id, "portal"))}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-medium text-sm truncate">{msg.sender_name || "Cliente"}</span>
                              {msg.process_number && (
                                <Badge variant="outline" className="text-[10px] px-1 py-0">#{msg.process_number}</Badge>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground truncate">{msg.content}</p>
                          </div>
                          <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                        </button>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-border">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Inbox className="h-5 w-5 text-primary" />
                    E-mails não lidos
                    {commsFeed.email_unread_count > 0 && (
                      <Badge variant="secondary">{commsFeed.email_unread_count}</Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  {commsFeed.unread_emails.length === 0 ? (
                    <EmptyState message="Sem emails por ler" className="py-8" />
                  ) : (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {commsFeed.unread_emails.map((email) => (
                        <button
                          type="button"
                          key={email.id}
                          className="w-full flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/30 hover:bg-muted/50 transition-colors text-left"
                          onClick={() => (email.process_id ? navigate(processDeepLink(email.process_id, "emails")) : navigate("/webmail"))}
                        >
                          <div className="min-w-0 flex-1">
                            <p className="font-medium text-sm truncate">{email.subject}</p>
                            <p className="text-xs text-muted-foreground truncate">De: {email.from_address}</p>
                          </div>
                          <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                        </button>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="changelog" className="mt-6">
            {changelog?.content_markdown ? (
              <Card className="border-border bg-secondary/40">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Megaphone className="h-5 w-5 text-primary" />
                    Novidades do CRM
                    {changelog.version && (
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        {safeString(changelog.version)}
                      </Badge>
                    )}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {changelog.published_at && formatDate(changelog.published_at)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0">
                  <div
                    className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed changelog-content"
                    dangerouslySetInnerHTML={{
                      __html: sanitizeHtml(markdownToHtml(changelog.content_markdown))
                    }}
                  />
                </CardContent>
              </Card>
            ) : (
              <Card className="border-border">
                <CardContent>
                  <EmptyState icon={Megaphone} message="Ainda não há novidades publicadas" />
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="documents" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-accent-foreground" />
                  Documentos a Expirar (Próximos 60 dias)
                </CardTitle>
                <CardDescription>
                  Documentos dos seus clientes próximos da data de validade
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ExpiringDocumentsList
                  expiries={upcomingExpiries}
                  onNavigate={(processId) => navigate(`/process/${processId}`)}
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="ai" className="mt-6">
            <AIAnalysisTab
              processes={processes}
              selectedClient={selectedClient}
              onSelectClient={(process) => {
                if (process) loadClientAndAnalyze(process);
              }}
              oneDriveFiles={oneDriveFiles}
              isAnalyzing={isAnalyzing}
              isLoadingFiles={isLoadingFiles}
              onAnalyzeDocument={analyzeDocumentWithAI}
              analysisResult={analysisResult}
              aiSummary={aiSummary}
              aiAnalysisDate={aiAnalysisDate}
              aiError={aiError}
              onRefreshAnalysis={refreshAiAnalysis}
            />
          </TabsContent>
        </Tabs>

        <AddExpiryDialog
          isOpen={isAddExpiryOpen}
          onClose={setIsAddExpiryOpen}
          formData={expiryFormData}
          setFormData={setExpiryFormData}
          onSubmit={handleAddExpiry}
          loading={formLoading}
          documentTypes={DOCUMENT_TYPES_CONSULTOR}
        />
      </div>
    </DashboardLayout>
  );
};

export default ConsultorDashboard;
