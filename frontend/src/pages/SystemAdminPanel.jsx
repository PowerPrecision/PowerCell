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
import { useState } from "react";
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
  // Emails de Sistema / Integrações (movidos para Comunicações)
  MailCheck, Plug,
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

// Embedded pages — Gestão
import UsersManagementPage from "./UsersManagementPage";
import SystemConfigPage from "./SystemConfigPage";
import AutomationPage from "./AutomationPage";
import PermissionsTab from "../components/admin/PermissionsTab";

// Embedded pages — Customização
import WorkflowStatusesPage from "./WorkflowStatusesPage";
import FormManagementPage from "./FormManagementPage";
import TemplatesPage from "./TemplatesPage";


// Embedded pages — Comunicações
import EmailAccountsPage from "./EmailAccountsPage";
import NotificationSettingsPage from "./NotificationSettingsPage";
// Secções movidas de SystemConfigPage para Comunicações
import { SystemEmailsSection, IntegrationsConfigSection } from "./SystemConfigPage";

// Embedded pages — Compliance
import RGPDAdminPage from "./RGPDAdminPage";
import AuditTrailPage from "./AuditTrailPage";

// Embedded pages — Técnico (admin only)
import BackupsPage from "./BackupsPage";
import UnifiedLogsPage from "./UnifiedLogsPage";
import DiagnosticsPage from "./DiagnosticsPage";
import AIConfigPage from "./AIConfigPage";
import BackgroundJobsPage from "./BackgroundJobsPage";
import ProcessMigrationTab from "../components/admin/ProcessMigrationTab";
import FinanceTab from "../components/admin/FinanceTab";
import CompaniesManagementPage from "./CompaniesManagementPage";

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
            <SystemConfigPage embedded={true} />
          </TabsContent>

          {/* Automações — AutomationPage em modo embedded */}
          <TabsContent value="automation" className="mt-6">
            <AutomationPage embedded={true} />
          </TabsContent>

          {/* Empresas — CompaniesManagementPage em modo embedded */}
          <TabsContent value="empresas" className="mt-6">
            <CompaniesManagementPage embedded={true} />
          </TabsContent>

          {/* ================================================================ */}
          {/* === TAB FINANÇAS — FinanceTab (amber/gold) === */}
          {/* ================================================================ */}
          <TabsContent value="financas" className="mt-6">
            <FinanceTab />
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
                <WorkflowStatusesPage embedded={true} />
              </TabsContent>
              <TabsContent value="form-management" className="mt-4">
                <FormManagementPage embedded={true} />
              </TabsContent>
              <TabsContent value="templates" className="mt-4">
                <TemplatesPage embedded={true} />
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

                  {/* Separador visual */}
                  <div className="w-px h-6 bg-border mx-1 self-center" />

                  <TabsTrigger value="system-emails" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                    <MailCheck className="h-4 w-4" />
                    <span className="hidden sm:inline">Emails de Sistema</span>
                    <span className="sm:hidden">SMTP</span>
                  </TabsTrigger>
                  <TabsTrigger value="integrations" className="gap-1.5 text-xs sm:text-sm whitespace-nowrap">
                    <Plug className="h-4 w-4" />
                    <span className="hidden sm:inline">Integrações</span>
                    <span className="sm:hidden">Integ</span>
                  </TabsTrigger>
                </TabsList>
              </div>
              <TabsContent value="email-accounts" className="mt-4">
                <EmailAccountsPage embedded={true} />
              </TabsContent>
              <TabsContent value="notifications" className="mt-4">
                <NotificationSettingsPage embedded={true} />
              </TabsContent>
              <TabsContent value="system-emails" className="mt-4">
                <SystemEmailsSection token={localStorage.getItem("token")} />
              </TabsContent>
              <TabsContent value="integrations" className="mt-4">
                <IntegrationsConfigSection />
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
                <RGPDAdminPage embedded={true} />
              </TabsContent>
              <TabsContent value="audit" className="mt-4">
                <AuditTrailPage embedded={true} />
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
                  <BackupsPage embedded={true} />
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
                      <UnifiedLogsPage embedded={true} />
                    </TabsContent>
                    <TabsContent value="diagnostics" className="mt-4">
                      <DiagnosticsPage embedded={true} />
                    </TabsContent>
                  </Tabs>
                </TabsContent>

                {/* Inteligência Artificial — AIConfigPage em modo embedded */}
                <TabsContent value="ai-config" className="mt-4">
                  <AIConfigPage embedded={true} />
                </TabsContent>

                {/* Processos BG — BackgroundJobsPage em modo embedded */}
                <TabsContent value="bg-jobs" className="mt-4">
                  <BackgroundJobsPage embedded={true} />
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
