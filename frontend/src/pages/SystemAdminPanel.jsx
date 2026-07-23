/**
 * SystemAdminPanel — Painel de Administração do Sistema (separado do dashboard operacional).
 *
 * PORQUÊ: O AdminDashboard misturava tabs de negócio (Visão Geral, Calendário, etc.)
 * com tabs de administração/configuração do sistema (Utilizadores, Configurações, Backups, etc.).
 * Esta separação cria um painel dedicado à gestão administrativa e técnica, enquanto
 * o AdminDashboard mantém apenas as funcionalidades operacionais de negócio.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Tabs organizadas em categorias visuais:
 *   1. GESTÃO (amber/gold): Utilizadores, Permissões, Configurações, Automações, Empresas —
 *      visíveis para admin e CEO.
 *   2. CUSTOMIZAÇÃO (emerald/green): Estados de Workflow, Formulários, Templates, Perfis —
 *      visíveis para admin e CEO.
 *   3. COMUNICAÇÕES (sky/blue): Contas de Email, Notificações —
 *      visíveis para admin e CEO.
 *   4. COMPLIANCE (violet/purple): RGPD, Auditoria —
 *      visíveis para admin e CEO.
 *   5. TÉCNICO (red): Backups, Logs & Diagnósticos, Inteligência Artificial, Processos BG —
 *      visíveis APENAS para o role "admin" (não CEO). Estas tabs envolvem operações
 *      de baixo nível que não são relevantes para o CEO.
 * - Sub-tabs nas tabs "Customização", "Comunicações", "Compliance" e "Técnico"
 *   para organizar as páginas órfãs que ficaram inacessíveis após a refatoração
 *   da Sidebar do DashboardLayout.
 * - Botão "Voltar ao Dashboard" para navegação de regresso ao AdminDashboard operacional.
 * - Todas as páginas integradas usam o modo `embedded={true}` para não renderizar
 *   o DashboardLayout interno.
 *
 * @context {AuthContext} — Consome user para verificar permissões (role admin)
 *
 * @route /system-admin — Rota do painel de administração do sistema
 *
 * @example
 * <SystemAdminPanel />
 * // Acesso via layout protegido — visível para roles admin e CEO
 * // Tabs técnicas exclusivas do admin
 */
import { useState, lazy, Suspense } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { useAuth } from "../contexts/AuthContext";
import {
  Users, Settings, Zap, Lock, ArrowLeft,
  // Customização
  Palette, GitBranch, FileText, LayoutTemplate,
  // Comunicações
  MessageSquare, Mail, Bell,
  // Compliance
  ShieldCheck, Scale, ClipboardList,
  // Técnico
  Shield, AlertTriangle, Database, Brain, Activity, ArrowRightLeft,
  // Finanças
  Landmark,
  // Gestão de Empresas
  Building2
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { hasRole } from "../utils/roleUtils";

// Embedded pages — Gestão (eager: leves)
import UsersManagementPage from "./UsersManagementPage";
import AutomationPage from "./AutomationPage";
import PermissionsTab from "../components/admin/PermissionsTab";

// PACOTE AZ: Lazy loading para páginas pesadas que causam TDZ
// (Cannot access 'd' before initialization) devido a dependências
// circulares indiretas no bundle do Vite.
const SystemConfigPage = lazy(() => import("./SystemConfigPage"));
const WorkflowStatusesPage = lazy(() => import("./WorkflowStatusesPage"));
const FormManagementPage = lazy(() => import("./FormManagementPage"));
const TemplatesPage = lazy(() => import("./TemplatesPage"));
const EmailAccountsPage = lazy(() => import("./EmailAccountsPage"));
const NotificationSettingsPage = lazy(() => import("./NotificationSettingsPage"));
const RGPDAdminPage = lazy(() => import("./RGPDAdminPage"));
const AuditTrailPage = lazy(() => import("./AuditTrailPage"));
const BackupsPage = lazy(() => import("./BackupsPage"));
const UnifiedLogsPage = lazy(() => import("./UnifiedLogsPage"));
const DiagnosticsPage = lazy(() => import("./DiagnosticsPage"));
const AIConfigPage = lazy(() => import("./AIConfigPage"));
const BackgroundJobsPage = lazy(() => import("./BackgroundJobsPage"));
const ProcessMigrationTab = lazy(() => import("../components/admin/ProcessMigrationTab"));
const FinanceTab = lazy(() => import("../components/admin/FinanceTab"));
const CompaniesManagementPage = lazy(() => import("./CompaniesManagementPage"));

// PACOTE BG: SystemEmailsSectionWrapper e IntegrationsConfigSectionWrapper
// removidos — as sub-tabs 'Emails de Sistema' e 'Integrações' foram
// eliminadas. As configurações estão cobertas em EmailAccountsPage e
// no detalhe de cada Empresa (Pacote BF).

// Loader para Suspense
const TabLoader = () => (
  <div className="flex items-center justify-center py-12">
    <div className="h-6 w-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
  </div>
);

const SystemAdminPanel = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  // Verificar se o utilizador é admin (para tabs técnicas exclusivas — não CEO)
  const isAdmin = hasRole(user, "admin");

  const [activeTab, setActiveTab] = useState("users-mgmt");

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="system-admin-panel">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Painel de Administração do Sistema
            </h1>
            <p className="text-muted-foreground">
              Configurações, gestão de utilizadores e ferramentas técnicas
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="gap-2 shrink-0"
            onClick={() => navigate("/admin")}
            data-testid="back-to-dashboard-btn"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar ao Dashboard
          </Button>
        </div>

        {/* Main Tabs — Administração do Sistema */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="w-full overflow-x-auto scrollbar-hide -mx-1 px-1">
            <TabsList className="inline-flex w-max min-w-full h-auto p-1 gap-1">
              {/* === TABS DE GESTÃO (amber/gold) === */}
              <TabsTrigger
                value="users-mgmt"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-amber-600 dark:text-amber-400"
                data-testid="tab-users-mgmt"
              >
                <Users className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Utilizadores</span>
                <span className="sm:hidden">Users</span>
              </TabsTrigger>
              <TabsTrigger
                value="permissions"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-amber-600 dark:text-amber-400"
                data-testid="tab-permissions"
              >
                <Lock className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Permissões</span>
                <span className="sm:hidden">Perms</span>
              </TabsTrigger>
              <TabsTrigger
                value="config"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-amber-600 dark:text-amber-400"
                data-testid="tab-config"
              >
                <Settings className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Configurações</span>
                <span className="sm:hidden">Config</span>
              </TabsTrigger>
              <TabsTrigger
                value="automation"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-amber-600 dark:text-amber-400"
                data-testid="tab-automation"
              >
                <Zap className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Automações</span>
                <span className="sm:hidden">Auto</span>
              </TabsTrigger>
              <TabsTrigger
                value="empresas"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-amber-600 dark:text-amber-400"
                data-testid="tab-empresas"
              >
                <Building2 className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Empresas</span>
                <span className="sm:hidden">Emp</span>
              </TabsTrigger>

              {/* Separador visual */}
              <div className="w-px h-6 bg-border mx-1 self-center" />

              {/* === TAB FINANÇAS (amber/gold) === */}
              <TabsTrigger
                value="financas"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-amber-600 dark:text-amber-400"
                data-testid="tab-financas"
              >
                <Landmark className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Finanças</span>
                <span className="sm:hidden">Fin</span>
              </TabsTrigger>

              {/* Separador visual */}
              <div className="w-px h-6 bg-border mx-1 self-center" />

              {/* === TAB CUSTOMIZAÇÃO (emerald/green) === */}
              <TabsTrigger
                value="customizacao"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-emerald-600 dark:text-emerald-400"
                data-testid="tab-customizacao"
              >
                <Palette className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Customização</span>
                <span className="sm:hidden">Custom</span>
              </TabsTrigger>

              {/* === TAB COMUNICAÇÕES (sky/blue) === */}
              <TabsTrigger
                value="comunicacoes"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-sky-600 dark:text-sky-400"
                data-testid="tab-comunicacoes"
              >
                <MessageSquare className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Comunicações</span>
                <span className="sm:hidden">Comms</span>
              </TabsTrigger>

              {/* === TAB COMPLIANCE (violet/purple) === */}
              <TabsTrigger
                value="compliance"
                className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-violet-600 dark:text-violet-400"
                data-testid="tab-compliance"
              >
                <ShieldCheck className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">Compliance</span>
                <span className="sm:hidden">Compl</span>
              </TabsTrigger>

              {/* === TAB TÉCNICO (red, exclusiva do admin) === */}
              {isAdmin && (
                <>
                  <div className="w-px h-6 bg-border mx-1 self-center" />
                  <TabsTrigger
                    value="tecnico"
                    className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-red-600 dark:text-red-400"
                    data-testid="tab-tecnico"
                  >
                    <Shield className="h-4 w-4 shrink-0" />
                    <span className="hidden sm:inline">Técnico</span>
                    <span className="sm:hidden">Tech</span>
                  </TabsTrigger>
                </>
              )}
            </TabsList>
          </div>

          {/* ================================================================ */}
          {/* === CONTEÚDO DAS TABS DE GESTÃO (amber/gold) === */}
          {/* ================================================================ */}

          {/* Utilizadores — Gestão completa (UsersManagementPage em modo embedded) */}
          <TabsContent value="users-mgmt" className="mt-6">
            <UsersManagementPage embedded={true} />
          </TabsContent>

          {/* Permissões Granulares — PermissionsTab */}
          <TabsContent value="permissions" className="mt-6">
            <PermissionsTab />
          </TabsContent>

          {/* Configurações Gerais — SystemConfigPage em modo embedded */}
          <TabsContent value="config" className="mt-6">
            <Suspense fallback={<TabLoader />}><SystemConfigPage embedded={true} /></Suspense>
          </TabsContent>

          {/* Automações — AutomationPage em modo embedded */}
          <TabsContent value="automation" className="mt-6">
            <AutomationPage embedded={true} />
          </TabsContent>

          {/* Empresas — CompaniesManagementPage em modo embedded */}
          <TabsContent value="empresas" className="mt-6">
            <Suspense fallback={<TabLoader />}><CompaniesManagementPage embedded={true} /></Suspense>
          </TabsContent>

          {/* ================================================================ */}
          {/* === TAB FINANÇAS — FinanceTab (amber/gold) === */}
          {/* ================================================================ */}
          <TabsContent value="financas" className="mt-6">
            <Suspense fallback={<TabLoader />}><FinanceTab /></Suspense>
          </TabsContent>

          {/* ================================================================ */}
          {/* === TAB CUSTOMIZAÇÃO — Sub-tabs (emerald/green) === */}
          {/* ================================================================ */}
          <TabsContent value="customizacao" className="mt-6">
            <Tabs defaultValue="workflow-statuses" className="w-full">
              <div className="w-full overflow-x-auto scrollbar-hide -mx-1 px-1">
                <TabsList className="inline-flex w-max min-w-full h-auto p-1 gap-1">
                  <TabsTrigger value="workflow-statuses" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                    <GitBranch className="h-4 w-4" />
                    <span className="hidden sm:inline">Estados de Workflow</span>
                    <span className="sm:hidden">Workflow</span>
                  </TabsTrigger>
                  <TabsTrigger value="form-management" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                    <FileText className="h-4 w-4" />
                    <span className="hidden sm:inline">Formulários</span>
                    <span className="sm:hidden">Forms</span>
                  </TabsTrigger>
                  <TabsTrigger value="templates" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                    <LayoutTemplate className="h-4 w-4" />
                    <span className="hidden sm:inline">Templates</span>
                    <span className="sm:hidden">Tmpl</span>
                  </TabsTrigger>

                </TabsList>
              </div>
              <TabsContent value="workflow-statuses" className="mt-4">
                <Suspense fallback={<TabLoader />}><WorkflowStatusesPage embedded={true} /></Suspense>
              </TabsContent>
              <TabsContent value="form-management" className="mt-4">
                <Suspense fallback={<TabLoader />}><FormManagementPage embedded={true} /></Suspense>
              </TabsContent>
              <TabsContent value="templates" className="mt-4">
                <Suspense fallback={<TabLoader />}><TemplatesPage embedded={true} /></Suspense>
              </TabsContent>

            </Tabs>
          </TabsContent>

          {/* ================================================================ */}
          {/* === TAB COMUNICAÇÕES — Sub-tabs (sky/blue) === */}
          {/* ================================================================ */}
          <TabsContent value="comunicacoes" className="mt-6">
            <Tabs defaultValue="email-accounts" className="w-full">
              <div className="w-full overflow-x-auto scrollbar-hide -mx-1 px-1">
                <TabsList className="inline-flex w-max min-w-full h-auto p-1 gap-1">
                  <TabsTrigger value="email-accounts" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                    <Mail className="h-4 w-4" />
                    <span className="hidden sm:inline">Contas de Email</span>
                    <span className="sm:hidden">Email</span>
                  </TabsTrigger>
                  <TabsTrigger value="notifications" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                    <Bell className="h-4 w-4" />
                    <span className="hidden sm:inline">Notificações</span>
                    <span className="sm:hidden">Notif</span>
                  </TabsTrigger>

                  {/* PACOTE BG: Sub-separadores 'Emails de Sistema' e 'Integrações'
                      removidos — estas configurações estão cobertas no
                      EmailAccountsPage (SystemSmtpCard, IndexationImapCard) e
                      no detalhe de cada Empresa (Pacote BF). */}
                </TabsList>
              </div>
              <TabsContent value="email-accounts" className="mt-4">
                <Suspense fallback={<TabLoader />}><EmailAccountsPage embedded={true} /></Suspense>
              </TabsContent>
              <TabsContent value="notifications" className="mt-4">
                <Suspense fallback={<TabLoader />}><NotificationSettingsPage embedded={true} /></Suspense>
              </TabsContent>
            </Tabs>
          </TabsContent>

          {/* ================================================================ */}
          {/* === TAB COMPLIANCE — Sub-tabs (violet/purple) === */}
          {/* ================================================================ */}
          <TabsContent value="compliance" className="mt-6">
            <Tabs defaultValue="rgpd" className="w-full">
              <TabsList>
                <TabsTrigger value="rgpd" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                  <Scale className="h-4 w-4" />
                  <span className="hidden sm:inline">RGPD</span>
                  <span className="sm:hidden">RGPD</span>
                </TabsTrigger>
                <TabsTrigger value="audit" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                  <ClipboardList className="h-4 w-4" />
                  <span className="hidden sm:inline">Auditoria</span>
                  <span className="sm:hidden">Audit</span>
                </TabsTrigger>
              </TabsList>
              <TabsContent value="rgpd" className="mt-4">
                <Suspense fallback={<TabLoader />}><RGPDAdminPage embedded={true} /></Suspense>
              </TabsContent>
              <TabsContent value="audit" className="mt-4">
                <Suspense fallback={<TabLoader />}><AuditTrailPage embedded={true} /></Suspense>
              </TabsContent>
            </Tabs>
          </TabsContent>

          {/* ================================================================ */}
          {/* === TAB TÉCNICO — Sub-tabs (red, exclusivas do admin) === */}
          {/* ================================================================ */}
          {isAdmin && (
            <TabsContent value="tecnico" className="mt-6">
              <Tabs defaultValue="backups" className="w-full">
                <div className="w-full overflow-x-auto scrollbar-hide -mx-1 px-1">
                  <TabsList className="inline-flex w-max min-w-full h-auto p-1 gap-1">
                    <TabsTrigger value="backups" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                      <Shield className="h-4 w-4" />
                      <span className="hidden sm:inline">Backups</span>
                      <span className="sm:hidden">Backup</span>
                    </TabsTrigger>
                    <TabsTrigger value="logs" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                      <AlertTriangle className="h-4 w-4" />
                      <span className="hidden sm:inline">Logs</span>
                      <span className="sm:hidden">Logs</span>
                    </TabsTrigger>
                    <TabsTrigger value="ai-config" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                      <Brain className="h-4 w-4" />
                      <span className="hidden sm:inline">Inteligência Artificial</span>
                      <span className="sm:hidden">AI</span>
                    </TabsTrigger>
                    <TabsTrigger value="bg-jobs" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                      <Activity className="h-4 w-4" />
                      <span className="hidden sm:inline">Processos BG</span>
                      <span className="sm:hidden">BG Jobs</span>
                    </TabsTrigger>
                    <TabsTrigger value="migration" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                      <ArrowRightLeft className="h-4 w-4" />
                      <span className="hidden sm:inline">Migração</span>
                      <span className="sm:hidden">Migr</span>
                    </TabsTrigger>
                  </TabsList>
                </div>

                {/* Backups — BackupsPage em modo embedded */}
                <TabsContent value="backups" className="mt-4">
                  <Suspense fallback={<TabLoader />}><BackupsPage embedded={true} /></Suspense>
                </TabsContent>

                {/* Logs — Sub-tabs com UnifiedLogsPage e DiagnosticsPage */}
                <TabsContent value="logs" className="mt-4">
                  <Tabs defaultValue="system-logs" className="w-full">
                    <TabsList>
                      <TabsTrigger value="system-logs" className="gap-1.5">
                        <AlertTriangle className="h-4 w-4" />
                        Logs do Sistema
                      </TabsTrigger>
                      <TabsTrigger value="diagnostics" className="gap-1.5">
                        <Database className="h-4 w-4" />
                        Diagnósticos
                      </TabsTrigger>
                    </TabsList>
                    <TabsContent value="system-logs" className="mt-4">
                      <Suspense fallback={<TabLoader />}><UnifiedLogsPage embedded={true} /></Suspense>
                    </TabsContent>
                    <TabsContent value="diagnostics" className="mt-4">
                      <Suspense fallback={<TabLoader />}><DiagnosticsPage embedded={true} /></Suspense>
                    </TabsContent>
                  </Tabs>
                </TabsContent>

                {/* Inteligência Artificial — AIConfigPage em modo embedded */}
                <TabsContent value="ai-config" className="mt-4">
                  <Suspense fallback={<TabLoader />}><AIConfigPage embedded={true} /></Suspense>
                </TabsContent>

                {/* Processos BG — BackgroundJobsPage em modo embedded */}
                <TabsContent value="bg-jobs" className="mt-4">
                  <Suspense fallback={<TabLoader />}><BackgroundJobsPage embedded={true} /></Suspense>
                </TabsContent>

                {/* Migração Fase 1 — Separação Cliente ↔ Processo */}
                <TabsContent value="migration" className="mt-4">
                  <ProcessMigrationTab embedded={true} />
                </TabsContent>
              </Tabs>
            </TabsContent>
          )}
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default SystemAdminPanel;
