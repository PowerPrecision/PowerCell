/**
 * SystemAdminPanel — Painel de Administração do Sistema (separado do dashboard operacional).
 *
 * PORQUÊ: O AdminDashboard misturava tabs de negócio (Visão Geral, Calendário, etc.)
 * com tabs de administração/configuração do sistema (Utilizadores, Configurações, Backups, etc.).
 * Esta separação cria um painel dedicado à gestão administrativa e técnica, enquanto
 * o AdminDashboard mantém apenas as funcionalidades operacionais de negócio.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Tabs organizadas em duas categorias visuais:
 *   1. GESTÃO (amber/gold): Utilizadores, Permissões, Configurações, Automações —
 *      visíveis para admin e CEO.
 *   2. TÉCNICO (red): Segurança & Backups, Logs & Diagnósticos — visíveis APENAS
 *      para o role "admin" (não CEO). Estas tabs envolvem operações de baixo nível
 *      (backup da BD, logs de erro, diagnósticos) que não são relevantes para o CEO.
 * - Sub-tabs na tab "Logs & Diagnósticos" para separar UnifiedLogsPage de DiagnosticsPage.
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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { useAuth } from "../contexts/AuthContext";
import { 
  Users, Settings, Zap, Shield, AlertTriangle, Database, Lock, ArrowLeft
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { hasRole } from "../utils/roleUtils";

// Embedded pages
import UsersManagementPage from "./UsersManagementPage";
import SystemConfigPage from "./SystemConfigPage";
import AutomationPage from "./AutomationPage";
import PermissionsTab from "../components/admin/PermissionsTab";
import BackupsPage from "./BackupsPage";
import UnifiedLogsPage from "./UnifiedLogsPage";
import DiagnosticsPage from "./DiagnosticsPage";

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

              {/* === TABS TÉCNICAS (red, exclusivas do admin) === */}
              {isAdmin && (
                <>
                  <div className="w-px h-6 bg-border mx-1 self-center" />
                  <TabsTrigger
                    value="backups"
                    className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-red-600 dark:text-red-400"
                    data-testid="tab-backups"
                  >
                    <Shield className="h-4 w-4 shrink-0" />
                    <span className="hidden sm:inline">Segurança & Backups</span>
                    <span className="sm:hidden">Backup</span>
                  </TabsTrigger>
                  <TabsTrigger
                    value="logs"
                    className="gap-1.5 text-xs sm:text-sm whitespace-nowrap flex-shrink-0 px-2 sm:px-3 text-red-600 dark:text-red-400"
                    data-testid="tab-logs"
                  >
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span className="hidden sm:inline">Logs & Diagnósticos</span>
                    <span className="sm:hidden">Logs</span>
                  </TabsTrigger>
                </>
              )}
            </TabsList>
          </div>

          {/* === CONTEÚDO DAS TABS DE GESTÃO === */}

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

          {/* === CONTEÚDO DAS TABS TÉCNICAS (exclusivas do admin) === */}

          {/* Segurança e Backups — BackupsPage em modo embedded */}
          {isAdmin && (
            <TabsContent value="backups" className="mt-6">
              <BackupsPage embedded={true} />
            </TabsContent>
          )}

          {/* Logs e Diagnósticos — Sub-tabs com UnifiedLogsPage e DiagnosticsPage */}
          {isAdmin && (
            <TabsContent value="logs" className="mt-6">
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
          )}
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default SystemAdminPanel;
