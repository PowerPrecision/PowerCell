/**
 * MediadorDashboard - Painel do Mediador de Crédito
 * Refatorado para usar componentes partilhados do DashboardShared
 */
import React, { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { CreditCard, Eye, Plus, AlertTriangle, Euro } from "lucide-react";
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

const MediadorDashboard = () => {
  const navigate = useNavigate();
  
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

  // Filtrar apenas processos de crédito (específico do Mediador)
  const creditProcesses = useMemo(() => {
    return filteredProcesses.filter(p => p.process_type === "credito" || p.process_type === "ambos");
  }, [filteredProcesses]);

  if (loading) {
    return (
      <DashboardLayout>
        <LoadingSpinner />
      </DashboardLayout>
    );
  }

  // Configuração das colunas da tabela (específica do Mediador)
  const tableColumns = [
    { key: "client", label: "Cliente" },
    { key: "email", label: "Email" },
    { key: "income", label: "Rendimento" },
    { key: "value", label: "Valor Financiar" },
    { key: "status", label: "Estado" },
    { key: "actions", label: "Ações", className: "text-right" }
  ];

  // Função para renderizar cada linha da tabela
  const renderRow = (process) => (
    <tr key={process.id} className="border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted">
      <td className="p-4 align-middle font-medium">{process.client_name}</td>
      <td className="p-4 align-middle">{process.client_email}</td>
      <td className="p-4 align-middle">
        {process.financial_data?.monthly_income 
          ? `€${process.financial_data.monthly_income.toLocaleString()}` 
          : "-"}
      </td>
      <td className="p-4 align-middle">
        {process.financial_data?.valor_financiado || "-"}
      </td>
      <td className="p-4 align-middle">
        <StatusBadge status={process.status} workflowStatuses={workflowStatuses} />
      </td>
      <td className="p-4 align-middle text-right">
        <Button variant="ghost" size="icon" onClick={() => navigate(`/process/${process.id}`)}>
          <Eye className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={() => openAddExpiryDialog(process.id)}>
          <Plus className="h-4 w-4" />
        </Button>
      </td>
    </tr>
  );

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="mediador-dashboard">
        <div>
          <h1 className="text-2xl font-bold">Painel do Mediador de Crédito</h1>
          <p className="text-muted-foreground">Gestão dos seus clientes e processos de crédito</p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={CreditCard}
            iconColor="text-emerald-600"
            bgColor="bg-emerald-100 dark:bg-emerald-900/30"
            value={creditProcesses.length}
            label="Processos Crédito"
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
            icon={Euro}
            iconColor="text-blue-600"
            bgColor="bg-blue-100 dark:bg-teal-600/30"
            value={creditProcesses.filter(p => p.status === "fase_bancaria" || p.status === "ch_aprovado").length}
            label="Em Aprovação"
          />
        </div>

        {/* Main Tabs */}
        <Tabs defaultValue="clients">
          <TabsList>
            <TabsTrigger value="clients" className="gap-2">
              <CreditCard className="h-4 w-4" />
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

        {/* Add Document Expiry Dialog */}
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
