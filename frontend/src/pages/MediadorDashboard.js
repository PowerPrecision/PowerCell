/**
 * MediadorDashboard — Painel do Mediador de Crédito
 * 
 * Vista centralizada com widgets de métricas, mural da equipa, tarefas e
 * acesso rápido ao webmail, focada em processos de crédito.
 *
 * @context {AuthContext} — user, token
 * @widget TeamMural — Mural de novidades da equipa
 * @widget TasksPanel — Gestão de tarefas com prioridades e prazos
 * @widget Email KPI Card — Emails não lidos (personal box)
 */
import React, { useMemo, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  CreditCard, Eye, Plus, AlertTriangle, Euro, Mail,
  TrendingUp, CheckCircle, XCircle, ClipboardList, Rss, Calendar
} from "lucide-react";
import {
  StatCard,
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
  DOCUMENT_TYPES_MEDIADOR,
  formatDate
} from "../components/dashboard/DashboardShared";
import TasksPanel from "../components/TasksPanel";
import TeamMural from "../components/TeamMural";
import { getWebmailStats, getCalendarDeadlines } from "../services/api";
import { safeString } from "../utils/safeString";
import { safeDateStr } from "../lib/utils";

const roleLabels = {
  admin: "Administrador",
  ceo: "CEO",
  consultor: "Consultor",
  intermediario: "Intermediário de Crédito",
  diretor: "Diretor(a)",
  administrativo: "Administrativo(a)",
  indexacao: "Indexação",
};

const MediadorDashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  // Webmail stats (personal box)
  const [webmailStats, setWebmailStats] = useState({ unread_count: 0, sent_today_count: 0, drafts_count: 0 });
  // Calendar deadlines
  const [deadlines, setDeadlines] = useState([]);

  // Dashboard data hook
  const {
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
  } = useDashboardData();

  // Document management hook
  const {
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
  } = useDocumentManagement(fetchData);

  // Filter credit-only processes (Mediador specific)
  const creditProcesses = useMemo(() => {
    return filteredProcesses.filter(p => p.process_type === "credito" || p.process_type === "ambos");
  }, [filteredProcesses]);

  // Fetch webmail stats and deadlines on mount
  useEffect(() => {
    getWebmailStats("personal")
      .then(res => setWebmailStats(res.data || { unread_count: 0, sent_today_count: 0, drafts_count: 0 }))
      .catch(() => {});

    getCalendarDeadlines()
      .then(res => setDeadlines(res.data || []))
      .catch(() => {});
  }, []);

  if (loading) {
    return (
      <DashboardLayout>
        <LoadingSpinner />
      </DashboardLayout>
    );
  }

  // Greeting
  const firstName = user?.name?.split(" ")[0] || "";
  const roleLabel = roleLabels[user?.role] || user?.role || "";

  // Table columns (Mediador specific with financial columns)
  const tableColumns = [
    { key: "client", label: "Cliente" },
    { key: "email", label: "Email" },
    { key: "income", label: "Rendimento" },
    { key: "value", label: "Valor Financiar" },
    { key: "status", label: "Estado" },
    { key: "actions", label: "Ações", className: "text-right" }
  ];

  // Row renderer
  const renderRow = (process) => (
    <tr key={process.id} className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
      <td className="p-2 sm:p-3 lg:p-4 align-middle font-medium">{safeString(process.client_name)}</td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">{safeString(process.client_email)}</td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">
        {process.financial_data?.monthly_income
          ? `€${process.financial_data.monthly_income.toLocaleString()}`
          : "-"}
      </td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">
        {process.financial_data?.valor_financiado || "-"}
      </td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">
        <StatusBadge status={process.status} workflowStatuses={workflowStatuses} />
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
      <div className="space-y-6" data-testid="mediador-dashboard">

        {/* ── Header ── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h1 className="text-2xl font-bold">
              Olá, {firstName} 👋
            </h1>
            <p className="text-muted-foreground">
              {roleLabel && <Badge variant="secondary" className="mr-2 text-xs">{roleLabel}</Badge>}
              Gestão dos seus clientes e processos de crédito
            </p>
          </div>
          <Button onClick={() => navigate('/staff-dashboard')} variant="outline" className="gap-2 self-start">
            <TrendingUp className="h-4 w-4" />
            Quadro Geral
          </Button>
        </div>

        {/* ── KPI / Metrics Row ── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <Card
            className="bg-blue-50 dark:bg-blue-950/30 border-blue-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate('/processos')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <TrendingUp className="h-5 w-5 text-blue-600" />
                  <p className="text-2xl sm:text-3xl font-bold text-blue-600">{stats.active_processes || 0}</p>
                </div>
                <p className="text-xs sm:text-sm text-blue-600/80">Ativos</p>
              </div>
            </CardContent>
          </Card>
          <Card
            className="bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate('/processos?view_mode=historical')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <CheckCircle className="h-5 w-5 text-emerald-600" />
                  <p className="text-2xl sm:text-3xl font-bold text-emerald-600">{stats.concluded_processes || 0}</p>
                </div>
                <p className="text-xs sm:text-sm text-emerald-600/80">Concluídos</p>
              </div>
            </CardContent>
          </Card>
          <Card
            className="bg-red-50 dark:bg-red-950/30 border-red-200 cursor-pointer hover:shadow-md transition-shadow"
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <XCircle className="h-5 w-5 text-red-600" />
                  <p className="text-2xl sm:text-3xl font-bold text-red-600">{stats.dropped_processes || 0}</p>
                </div>
                <p className="text-xs sm:text-sm text-red-600/80">Desistências</p>
              </div>
            </CardContent>
          </Card>
          <StatCard
            icon={CreditCard}
            iconColor="text-emerald-600"
            bgColor="bg-emerald-100 dark:bg-emerald-900/30"
            value={creditProcesses.length}
            label="Proc. Crédito"
          />
          <StatCard
            icon={AlertTriangle}
            iconColor="text-yellow-600"
            bgColor="bg-yellow-100 dark:bg-yellow-900/30"
            value={stats.pending_deadlines || 0}
            label="Prazos Pendentes"
          />
          <StatCard
            icon={Euro}
            iconColor="text-blue-600"
            bgColor="bg-blue-100 dark:bg-teal-600/30"
            value={creditProcesses.filter(p => p.status === "fase_bancaria" || p.status === "ch_aprovado").length}
            label="Em Aprovação"
          />
          {/* ── Email KPI Card ── */}
          <Card
            className={`cursor-pointer hover:shadow-md transition-shadow ${webmailStats.unread_count > 0 ? "bg-amber-50 dark:bg-amber-950/30 border-amber-200" : "bg-emerald-50/50 dark:bg-emerald-950/20 border-emerald-200/50"}`}
            onClick={() => navigate('/webmail')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1 mb-0.5">
                  <Mail className="h-4 w-4" />
                </div>
                <p className={`text-2xl sm:text-3xl font-bold ${webmailStats.unread_count > 0 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                  {webmailStats.unread_count}
                </p>
                <p className="text-xs sm:text-sm text-muted-foreground">
                  {webmailStats.unread_count === 1 ? "Email Não Lido" : "Emails Não Lidos"}
                </p>
                {(webmailStats.sent_today_count > 0 || webmailStats.drafts_count > 0) && (
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {webmailStats.sent_today_count > 0 && `${webmailStats.sent_today_count} enviado${webmailStats.sent_today_count !== 1 ? "s" : ""} hoje`}
                    {webmailStats.sent_today_count > 0 && webmailStats.drafts_count > 0 && " · "}
                    {webmailStats.drafts_count > 0 && `${webmailStats.drafts_count} rascunho${webmailStats.drafts_count !== 1 ? "s" : ""}`}
                  </p>
                )}
                <p className="text-[10px] font-medium text-primary mt-1 hover:underline">
                  Abrir Webmail →
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ── Two-column Widget Grid: Tasks + Mural ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* ── Left Column: Tasks Panel ── */}
          <Card className="border-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <ClipboardList className="h-5 w-5 shrink-0" />
                Minhas Tarefas
              </CardTitle>
              <CardDescription className="text-xs">
                Prazos, prioridades e tarefas em background
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-0">
              <TasksPanel
                showCreateButton={true}
                compact={false}
                maxHeight="520px"
                showOnlyMyTasks={true}
              />
            </CardContent>
          </Card>

          {/* ── Right Column: Team Mural ── */}
          <Card className="border-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Rss className="h-5 w-5 shrink-0" />
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
        </div>

        {/* ── Main Tabs: Clients / Calendar / Documents / AI ── */}
        <Tabs defaultValue="clients">
          <TabsList className="flex-wrap">
            <TabsTrigger value="clients" className="gap-2">
              <CreditCard className="h-4 w-4" />
              Meus Clientes
            </TabsTrigger>
            <TabsTrigger value="calendar" className="gap-2">
              <Calendar className="h-4 w-4" />
              Próximos Prazos
            </TabsTrigger>
            <TabsTrigger value="documents" className="gap-2">
              <AlertTriangle className="h-4 w-4" />
              Documentos a Expirar
            </TabsTrigger>
            <TabsTrigger value="ai" className="gap-2">
              <AlertTriangle className="h-4 w-4" />
              Análise IA
            </TabsTrigger>
          </TabsList>

          {/* ── Clients Tab ── */}
          <TabsContent value="clients" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <div className="flex flex-col sm:flex-row gap-4 justify-between">
                  <div>
                    <CardTitle className="text-lg">Os Meus Clientes de Crédito</CardTitle>
                    <CardDescription>Processos de crédito atribuídos a si</CardDescription>
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
                  processes={creditProcesses}
                  columns={tableColumns}
                  renderRow={renderRow}
                  emptyMessage="Nenhum processo de crédito encontrado"
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── Calendar / Deadlines Tab ── */}
          <TabsContent value="calendar" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5" />
                  Próximos Prazos
                </CardTitle>
                <CardDescription>Prazos e eventos agendados</CardDescription>
              </CardHeader>
              <CardContent>
                {deadlines.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">Nenhum prazo agendado</p>
                ) : (
                  <div className="space-y-3 max-h-[520px] overflow-y-auto">
                    {[...deadlines]
                      .sort((a, b) => new Date(safeDateStr(a.due_date)) - new Date(safeDateStr(b.due_date)))
                      .slice(0, 15)
                      .map((deadline) => {
                        const dueDate = new Date(safeDateStr(deadline.due_date));
                        const now = new Date();
                        const daysLeft = Math.ceil((dueDate - now) / (1000 * 60 * 60 * 24));
                        const urgencyClass = daysLeft < 0 ? "border-red-300 bg-red-50 dark:bg-red-950/20" :
                          daysLeft <= 3 ? "border-orange-300 bg-orange-50 dark:bg-orange-950/20" :
                          daysLeft <= 7 ? "border-yellow-300 bg-yellow-50 dark:bg-yellow-950/20" :
                          "border-border bg-muted/30";
                        return (
                          <div key={deadline.id} className={`flex items-center justify-between p-3 rounded-lg border ${urgencyClass}`}>
                            <div className="min-w-0 flex-1">
                              <p className="font-medium text-sm truncate">{deadline.title || deadline.description || "Prazo"}</p>
                              {deadline.process_id && (
                                <p className="text-xs text-muted-foreground truncate">
                                  Processo: {deadline.process_id}
                                </p>
                              )}
                            </div>
                            <div className="text-right ml-3 shrink-0">
                              <p className="text-sm font-medium">
                                {formatDate(deadline.due_date)}
                              </p>
                              <p className={`text-xs ${daysLeft < 0 ? "text-red-600" : daysLeft <= 3 ? "text-orange-600" : "text-muted-foreground"}`}>
                                {daysLeft < 0 ? `${Math.abs(daysLeft)}d atrasado` : daysLeft === 0 ? "Hoje" : `em ${daysLeft}d`}
                              </p>
                            </div>
                          </div>
                        );
                      })}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── Documents Expiry Tab ── */}
          <TabsContent value="documents" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-orange-500" />
                  Documentos a Expirar (Próximos 60 dias)
                </CardTitle>
                <CardDescription>Documentos dos seus clientes que estão próximos da data de validade</CardDescription>
              </CardHeader>
              <CardContent>
                <ExpiringDocumentsList
                  expiries={upcomingExpiries}
                  onNavigate={(processId) => navigate(`/process/${processId}`)}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* ── AI Analysis Tab ── */}
          <TabsContent value="ai" className="mt-6">
            <AIAnalysisTab
              processes={creditProcesses}
              selectedClient={selectedClient}
              onSelectClient={(value) => {
                const process = creditProcesses.find(p => p.id === value);
                if (process) loadClientFiles(process);
              }}
              oneDriveFiles={oneDriveFiles}
              isAnalyzing={isAnalyzing}
              onAnalyzeDocument={analyzeDocumentWithAI}
              analysisResult={analysisResult}
            />
          </TabsContent>
        </Tabs>

        {/* ── Add Document Expiry Dialog ── */}
        <AddExpiryDialog
          isOpen={isAddExpiryOpen}
          onClose={setIsAddExpiryOpen}
          formData={expiryFormData}
          setFormData={setExpiryFormData}
          onSubmit={handleAddExpiry}
          loading={formLoading}
          documentTypes={DOCUMENT_TYPES_MEDIADOR}
        />
      </div>
    </DashboardLayout>
  );
};

export default MediadorDashboard;
