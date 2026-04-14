/**
 * ConsultorDashboard - Painel do Consultor
 * Refatorado para usar componentes partilhados do DashboardShared
 */
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Users, Eye, Plus, AlertTriangle, Building2, Mail } from "lucide-react";
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
  DOCUMENT_TYPES_CONSULTOR,
  formatDate
} from "../components/dashboard/DashboardShared";
import { getWebmailStats } from "../services/api";

const ConsultorDashboard = () => {
  const navigate = useNavigate();
  
  // Webmail stats
  const [webmailStats, setWebmailStats] = useState({ unread_count: 0, sent_today_count: 0, drafts_count: 0 });

  // Hook para dados do dashboard
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

  // Fetch webmail stats
  useEffect(() => {
    getWebmailStats()
      .then(res => setWebmailStats(res.data))
      .catch(() => {});
  }, []);

  // Hook para gestão de documentos
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

  if (loading) {
    return (
      <DashboardLayout>
        <LoadingSpinner />
      </DashboardLayout>
    );
  }

  // Configuração das colunas da tabela
  const tableColumns = [
    { key: "client", label: "Cliente" },
    { key: "email", label: "Email" },
    { key: "type", label: "Tipo" },
    { key: "status", label: "Estado" },
    { key: "date", label: "Data" },
    { key: "actions", label: "Ações", className: "text-right" }
  ];

  // Função para renderizar cada linha da tabela
  const renderRow = (process) => (
    <tr key={process.id} className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
      <td className="p-2 sm:p-3 lg:p-4 align-middle font-medium">{process.client_name}</td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">{process.client_email}</td>
      <td className="p-2 sm:p-3 lg:p-4 align-middle">
        <Badge variant="outline">{TYPE_LABELS[process.process_type] || process.process_type}</Badge>
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
        <div>
          <h1 className="text-2xl font-bold">Painel do Consultor</h1>
          <p className="text-muted-foreground">Gestão dos seus clientes e processos imobiliários</p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard
            icon={Users}
            iconColor="text-blue-600"
            bgColor="bg-blue-100 dark:bg-teal-600/30"
            value={processes.length}
            label="Meus Clientes"
          />
          <StatCard
            icon={AlertTriangle}
            iconColor="text-yellow-600"
            bgColor="bg-yellow-100 dark:bg-yellow-900/30"
            value={stats.pending_deadlines || 0}
            label="Prazos Pendentes"
          />
          <StatCard
            icon={AlertTriangle}
            iconColor="text-orange-600"
            bgColor="bg-orange-100 dark:bg-orange-900/30"
            value={upcomingExpiries.length}
            label="Docs a Expirar"
          />
          <StatCard
            icon={Building2}
            iconColor="text-green-600"
            bgColor="bg-green-100 dark:bg-green-900/30"
            value={processes.filter(p => p.status === "aprovado").length}
            label="Aprovados"
          />
          {/* Email KPI Card */}
          <Card 
            className={`cursor-pointer hover:shadow-md transition-shadow ${webmailStats.unread_count > 0 ? "bg-amber-50 dark:bg-amber-950/30 border-amber-200" : "bg-emerald-50/50 dark:bg-emerald-950/20 border-emerald-200/50"}`}
            onClick={() => navigate('/webmail')}
          >
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className={`p-3 ${webmailStats.unread_count > 0 ? "bg-amber-100 dark:bg-amber-900/30" : "bg-emerald-100 dark:bg-emerald-900/30"} rounded-lg`}>
                  <Mail className={`h-6 w-6 ${webmailStats.unread_count > 0 ? "text-amber-600" : "text-emerald-600"}`} />
                </div>
                <div>
                  <p className={`text-2xl font-bold ${webmailStats.unread_count > 0 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                    {webmailStats.unread_count}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {webmailStats.unread_count === 1 ? "Email Não Lido" : "Emails Não Lidos"}
                  </p>
                  <p className="text-xs font-medium text-primary hover:underline">
                    Abrir Webmail →
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Tabs */}
        <Tabs defaultValue="clients">
          <TabsList className="flex-wrap">
            <TabsTrigger value="clients" className="gap-2">
              <Users className="h-4 w-4" />
              Meus Clientes
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

          {/* Clients Tab */}
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

          {/* Documents Expiry Tab */}
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

          {/* AI Analysis Tab */}
          <TabsContent value="ai" className="mt-6">
            <AIAnalysisTab
              processes={processes}
              selectedClient={selectedClient}
              onSelectClient={(value) => {
                const process = processes.find(p => p.id === value);
                if (process) loadClientFiles(process);
              }}
              oneDriveFiles={oneDriveFiles}
              isAnalyzing={isAnalyzing}
              onAnalyzeDocument={analyzeDocumentWithAI}
              analysisResult={analysisResult}
            />
          </TabsContent>
        </Tabs>

        {/* Add Document Expiry Dialog */}
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
