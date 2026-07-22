import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import { UploadProgressProvider } from "./contexts/UploadProgressContext";
import { TasksProvider } from "./contexts/TasksContext";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { queryClient } from "./lib/queryClient";
import ImpersonateBanner from "./components/ImpersonateBanner";
import GlobalUploadProgress from "./components/GlobalUploadProgress";
import ErrorBoundary from "./components/ErrorBoundary";
import { hasRole, hasAnyRole, hasPermission, STAFF_ROLES } from "./utils/roleUtils";
import React, { Suspense, Component } from "react";
import * as Sentry from "@sentry/react";
import { FullPageSkeleton } from "./components/ui/skeletons";

// ====================================================================
// PÁGINAS COM CARREGAMENTO IMEDIATO (críticas para UX inicial)
// ====================================================================
// Estas páginas são carregadas imediatamente porque:
// 1. LoginPage - ecrã de entrada, deve aparecer instantaneamente
// 2. PublicClientForm - landing page pública, SEO e primeira impressão
// 3. RGPDPage, TempLinkUploadPage, TempLinkDownloadPage - páginas públicas
import LoginPage from "./pages/LoginPage";
import PublicClientForm from "./pages/PublicClientForm";
import RGPDPage from "./pages/RGPDPage";
import TempLinkUploadPage from "./pages/TempLinkUploadPage";
import TempLinkDownloadPage from "./pages/TempLinkDownloadPage";
import ClientPortal from "./pages/ClientPortal";

// ====================================================================
// PÁGINAS PESADAS COM CODE SPLITTING (lazy loading)
// ====================================================================
// Páginas lazy-loaded para reduzir o bundle inicial:
// - StaffDashboard: 44KB (gráficos e estatísticas)
// - KanbanPage: importa bibliotecas de drag-drop (@dnd-kit)
// - ProcessDetails: 164KB (o maior componente da aplicação!)
const StaffDashboard = React.lazy(() => import("./pages/StaffDashboard"));
const ConsultorDashboard = React.lazy(() => import("./pages/ConsultorDashboard"));
const KanbanPage = React.lazy(() => import("./pages/KanbanPage"));
const ProcessDetails = React.lazy(() => import("./pages/ProcessDetails"));

// ====================================================================
// PÁGINAS COM CODE SPLITTING (lazy loading)
// ====================================================================
const AdminDashboard = React.lazy(() => import("./pages/AdminDashboard"));
const SystemAdminPanel = React.lazy(() => import("./pages/SystemAdminPanel"));
const RGPDAdminPage = React.lazy(() => import("./pages/RGPDAdminPage"));
const StatisticsPage = React.lazy(() => import("./pages/StatisticsPage"));
const UsersManagementPage = React.lazy(() => import("./pages/UsersManagementPage"));
const ProcessesPage = React.lazy(() => import("./pages/ProcessesPage"));
const SettingsPage = React.lazy(() => import("./pages/SettingsPage"));
const FilteredProcessList = React.lazy(() => import("./pages/FilteredProcessList"));
const PendingItemsList = React.lazy(() => import("./pages/PendingItemsList"));
const SystemConfigPage = React.lazy(() => import("./pages/SystemConfigPage"));
const EmailAccountsPage = React.lazy(() => import("./pages/EmailAccountsPage"));
const AIConfigPage = React.lazy(() => import("./pages/AIConfigPage"));
const AITrainingPage = React.lazy(() => import("./pages/AITrainingPage"));
const BackgroundJobsPage = React.lazy(() => import("./pages/BackgroundJobsPage"));
const NotificationSettingsPage = React.lazy(() => import("./pages/NotificationSettingsPage"));
const NotificationsPage = React.lazy(() => import("./pages/NotificationsPage"));
const UnifiedLogsPage = React.lazy(() => import("./pages/UnifiedLogsPage"));
const PropertiesPage = React.lazy(() => import("./pages/PropertiesPage"));
const ClientsPage = React.lazy(() => import("./pages/ClientsPage"));
const LeadsPage = React.lazy(() => import("./pages/LeadsPage"));
const TeamPerformanceDashboard = React.lazy(() => import("./pages/TeamPerformanceDashboard"));
const VisitsPage = React.lazy(() => import("./pages/VisitsPage"));
const MyClientsPage = React.lazy(() => import("./pages/MyClientsPage"));
const ClientDetailPage = React.lazy(() => import("./pages/ClientDetailPage"));
const BackupsPage = React.lazy(() => import("./pages/BackupsPage"));
const MinutasPage = React.lazy(() => import("./pages/MinutasPage"));
const AIInsightsPage = React.lazy(() => import("./pages/AIInsightsPage"));
const AIDataReviewPage = React.lazy(() => import("./pages/AIDataReviewPage"));
const DiagnosticsPage = React.lazy(() => import("./pages/DiagnosticsPage"));
const ExpiringDocumentsDashboard = React.lazy(() => import("./pages/ExpiringDocumentsDashboard"));
const ClientRegistrationsPage = React.lazy(() => import("./pages/ClientRegistrationsPage"));
const WorkflowStatusesPage = React.lazy(() => import("./pages/WorkflowStatusesPage"));
const AutomationPage = React.lazy(() => import("./pages/AutomationPage"));
const ProfilePage = React.lazy(() => import("./pages/ProfilePage"));

const FormManagementPage = React.lazy(() => import("./pages/FormManagementPage"));
const AuditTrailPage = React.lazy(() => import("./pages/AuditTrailPage"));
const FinanceDashboard = React.lazy(() => import("./pages/FinanceDashboard"));
const RGPDMigrationPage = React.lazy(() => import("./pages/RGPDMigrationPage"));
const WebmailPage = React.lazy(() => import("./pages/WebmailPage"));
const DraftsPage = React.lazy(() => import("./pages/DraftsPage"));
const TemplatesPage = React.lazy(() => import("./pages/TemplatesPage"));
const FilesExplorerPage = React.lazy(() => import("./pages/FilesExplorerPage"));
const BranchPerformancePage = React.lazy(() => import("./pages/BranchPerformancePage"));

// ====================================================================
// LOADING SKELETON PARA PÁGINAS LAZY
// ====================================================================
function PageLoadingSkeleton() {
  return (
    <div className="min-h-[400px] flex items-center justify-center bg-background p-6">
      <FullPageSkeleton />
    </div>
  );
}

// ====================================================================
// ROUTE BOUNDARY — Combina Suspense + ErrorBoundary por rota
// ====================================================================
// Cada lazy-loaded route fica envolvida pelo seu próprio ErrorBoundary.
// Se uma página crashar, APENAS essa página mostra erro — o menu,
// sidebar e resto da app continuam a funcionar.
// ====================================================================
function RouteBoundary({ children, name }) {
  return (
    <ErrorBoundary variant="page" moduleName={name}>
      <Suspense fallback={<PageLoadingSkeleton />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}

// ====================================================================
// ERROR BOUNDARY PARA ERROS DE CHUNK (Lazy Loading)
// ====================================================================
// Quando o Vite divide o código em chunks, se uma nova versão for
// deployada enquanto um utilizador tem a aba aberta, o browser pode
// tentar carregar um chunk que já não existe.
// Este Error Boundary deteta esse erro e faz reload suavemente.
// ====================================================================
class LazyChunkErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    // Verifica se é um erro de chunk loading
    const isChunkError =
      error?.name === "ChunkLoadError" ||
      error?.code === "MODULE_NOT_FOUND" ||
      error?.message?.includes("Failed to fetch dynamically imported module") ||
      error?.message?.includes("Loading chunk") ||
      error?.message?.includes("Loading CSS chunk") ||
      error?.message?.includes("text/html") ||
      error?.message?.includes("MIME type") ||
      error?.message?.includes("Unexpected token") ||
      error?.message?.includes("Script error");

    if (isChunkError) {
      console.warn("[LazyChunkErrorBoundary] Erro de chunk detetado, a recarregar página...");
      // Limpa a cache do Vite se existir
      if (typeof window !== "undefined" && window.__vite__ && window.__vite__.clearCache) {
        window.__vite__.clearCache();
      }
      // Força reload limpo com cache-busting para evitar ciclo infinito
      // (CDN/browser podem servir index.html em cache com hashes antigos)
      window.location.replace(
        window.location.pathname +
        window.location.search +
        (window.location.search.includes('?') ? '&' : '?') +
        '_t=' + Date.now()
      );
      return { hasError: true, error };
    }

    // Para outros erros, deixa propagar para o Sentry
    return { hasError: false, error };
  }

  componentDidCatch(error, errorInfo) {
    // Se não for erro de chunk, reporta ao Sentry
    if (!this.state.hasError) {
      Sentry.captureException(error, { contexts: { react: { componentStack: errorInfo.componentStack } } });
    }
  }

  render() {
    if (this.state.hasError) {
      // Enquanto recarrega, mostra loading
      return <PageLoadingSkeleton />;
    }
    return this.props.children;
  }
}

// IdealistaImportPage movido para modal na página de Leads
import "./App.css";

// Admin roles for automation and system config
const ADMIN_ROLES = ["admin", "ceo"];

function ProtectedRoute({ children, allowedRoles, requiredCapability }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Verificação de role (compatibilidade existente)
  if (allowedRoles && !allowedRoles.some(r => hasRole(user, r))) {
    return <Navigate to="/staff" replace />;
  }

  // Verificação de capability granular (se especificada)
  if (requiredCapability && !hasPermission(user, requiredCapability)) {
    return <Navigate to="/staff" replace />;
  }

  return children;
}

function DashboardRedirect() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  // Admin e CEO vão para /admin (Painel de Administração), todos os outros staff vão para /staff
  if (hasRole(user, "admin") || hasRole(user, "ceo")) {
    return <Navigate to="/admin" replace />;
  }
  return <Navigate to="/staff" replace />;
}

// Componente para redirecionar a rota raiz baseado no estado de autenticação
function RootRedirect() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  // Se autenticado, redireciona para o dashboard adequado
  if (user) {
    if (hasRole(user, "admin") || hasRole(user, "ceo")) {
      return <Navigate to="/admin" replace />;
    }
    return <Navigate to="/staff" replace />;
  }

  // Se não autenticado, mostra o formulário público
  return (
    <ErrorBoundary variant="page" moduleName="Formulário Público">
      <PublicClientForm />
    </ErrorBoundary>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <UploadProgressProvider>
          <TasksProvider>
          <BrowserRouter>
          <Sentry.ErrorBoundary fallback={ErrorFallback}>
          <LazyChunkErrorBoundary>
          <Routes>
          {/* Root redirect - shows form or redirects to dashboard based on auth */}
          <Route path="/" element={<RootRedirect />} />
          {/* Public client registration form - explicit route */}
          <Route path="/registo" element={<ErrorBoundary variant="page" moduleName="Registo"><PublicClientForm /></ErrorBoundary>} />
          {/* Consultant form preview - view form without filling */}
          <Route path="/formulario-consultor" element={<ErrorBoundary variant="page" moduleName="Pré-visualização Formulário"><PublicClientForm previewMode={true} /></ErrorBoundary>} />
          
          {/* RGPD Public Page - for client consent signature */}
          <Route path="/rgpd/:token" element={<ErrorBoundary variant="page" moduleName="RGPD"><RGPDPage /></ErrorBoundary>} />
          
          {/* Temporary Link Upload - for client document upload */}
          <Route path="/upload/:token" element={<ErrorBoundary variant="page" moduleName="Upload Temporário"><TempLinkUploadPage /></ErrorBoundary>} />
          
          {/* Temporary Link Download - for client document download */}
          <Route path="/download/:token" element={<ErrorBoundary variant="page" moduleName="Download Temporário"><TempLinkDownloadPage /></ErrorBoundary>} />
          
          {/* Client Portal - Magic Link (passwordless, no auth required) */}
          <Route path="/portal/:token" element={<ErrorBoundary variant="page" moduleName="Portal do Cliente"><ClientPortal /></ErrorBoundary>} />
          
          {/* /portal — ecrã de login OTP (novo fluxo NIF + OTP) */}
          <Route path="/portal" element={<ErrorBoundary variant="page" moduleName="Portal do Cliente"><ClientPortal /></ErrorBoundary>} />
          
          {/* Staff login */}
          <Route path="/login" element={<LoginPage />} />
          
          {/* Dashboard redirect */}
          <Route path="/dashboard" element={<DashboardRedirect />} />
          
          {/* Kanban Page - Primary landing page for staff */}
          <Route
            path="/kanban"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Kanban">
                  <KanbanPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* Staff Dashboard (Consultor, Mediador, Diretor, Administrativo, CEO) - Resumo/KPIs */}
          <Route
            path="/staff"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Dashboard Consultor">
                  <ConsultorDashboard />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* /staff-dashboard redirect → canonical /staff */}
          <Route path="/staff-dashboard" element={<Navigate to="/staff" replace />} />
          
          {/* Admin Dashboard - Painel Operacional (admin + CEO) */}
          <Route
            path="/admin"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Dashboard Operacional">
                  <AdminDashboard />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Team Performance Dashboard - Executivo (admin + CEO) */}
          <Route
            path="/admin/desempenho"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Desempenho da Equipa">
                  <TeamPerformanceDashboard />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* System Admin Panel - Configurações do Sistema (admin + CEO) */}
          <Route
            path="/system-admin"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Painel de Administração do Sistema">
                  <SystemAdminPanel />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Statistics Page - Staff and Admin */}
          <Route
            path="/estatisticas"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Estatísticas">
                  <StatisticsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Branch Performance (Pacote S) - Staff com STATS_VIEW */}
          <Route
            path="/performance-balcoes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Performance de Balcões">
                  <BranchPerformancePage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* Finance Dashboard - All Staff */}
          <Route
            path="/financeiro"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Financeiro">
                  <FinanceDashboard />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Finance Settings — REDIRECT to SystemAdminPanel > Tab Finanças */}
          <Route path="/finance/settings" element={<Navigate to="/system-admin" replace />} />
          
          {/* Users Management Page - Admin and CEO */}
          <Route
            path="/utilizadores"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Gestão de Utilizadores">
                  <UsersManagementPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Processes Page - Staff and Admin */}
          <Route
            path="/processos"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Processos">
                  <ProcessesPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* Alias: sidebar navega para /lista-processos */}
          <Route
            path="/lista-processos"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Processos">
                  <ProcessesPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Properties Page - Staff and Admin */}
          <Route
            path="/imoveis"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Imóveis">
                  <PropertiesPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Visits Page - Staff and Admin */}
          <Route
            path="/visitas"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Visitas">
                  <VisitsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Clients Page - Staff and Admin */}
          <Route
            path="/clientes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Clientes">
                  <ClientsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Leads Page - Staff and Admin */}
          <Route
            path="/leads"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Leads">
                  <LeadsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* My Clients - For Consultors, Intermediários e Indexação */}
          <Route
            path="/meus-clientes"
            element={
              <ProtectedRoute allowedRoles={["consultor", "intermediario", "admin", "ceo", "indexacao"]}>
                <RouteBoundary name="Meus Clientes">
                  <MyClientsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Client Detail Page - Staff and Admin */}
          <Route
            path="/cliente/:id"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Ficha do Cliente">
                  <ClientDetailPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Process Details - Staff and Admin */}
          <Route
            path="/processo/:id"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Detalhes do Processo">
                  <ProcessDetails />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          <Route
            path="/process/:id"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Detalhes do Processo">
                  <ProcessDetails />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Settings Page - Staff and Admin */}
          <Route
            path="/definicoes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Definições">
                  <SettingsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Profile Page - All authenticated users */}
          <Route
            path="/perfil"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Perfil">
                  <ProfilePage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Workflow Statuses - Admin and CEO */}
          <Route
            path="/workflow-estados"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Estados de Workflow">
                  <WorkflowStatusesPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          <Route path="/automation" element={
              <ProtectedRoute allowedRoles={ADMIN_ROLES}>
                <RouteBoundary name="Automação">
                  <AutomationPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Form Management - Admin and CEO */}
          <Route
            path="/gestao-formulario"
            element={
              <ProtectedRoute allowedRoles={ADMIN_ROLES}>
                <RouteBoundary name="Gestão de Formulário">
                  <FormManagementPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* Templates / Destinatarios - Admin, CEO, Administrativo */}
          <Route
            path="/templates"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo", "administrativo"]}>
                <RouteBoundary name="Templates">
                  <TemplatesPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* Rascunhos (Drafts) - Acesso via capability DRAFT_VIEW */}
          <Route
            path="/rascunhos"
            element={
              <ProtectedRoute requiredCapability="DRAFT_VIEW">
                <RouteBoundary name="Rascunhos">
                  <DraftsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* Expiring Documents Dashboard - All Staff (filtered by role) */}
          <Route
            path="/validades"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Validade de Documentos">
                  <ExpiringDocumentsDashboard />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* System Configuration - Admin and CEO only */}
          <Route
            path="/configuracoes"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Configurações do Sistema">
                  <SystemConfigPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Email Accounts Management - Admin and CEO only */}
          <Route
            path="/contas-email"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Contas de Email">
                  <EmailAccountsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* AI Configuration - Admin only */}
          <Route
            path="/configuracoes/ia"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <RouteBoundary name="Configuração IA">
                  <AIConfigPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* AI Training - Admin only */}
          <Route
            path="/configuracoes/treino-ia"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <RouteBoundary name="Treino IA">
                  <AITrainingPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Background Jobs - Admin only */}
          <Route
            path="/admin/processos-background"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <RouteBoundary name="Processos em Background">
                  <BackgroundJobsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Notification Settings - Admin only */}
          <Route
            path="/configuracoes/notificacoes"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <RouteBoundary name="Configurações de Notificações">
                  <NotificationSettingsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Notifications Page - All staff */}
          <Route
            path="/notificacoes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Notificações">
                  <NotificationsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* System Logs (Unified) - Admin only */}
          <Route
            path="/admin/logs"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <RouteBoundary name="Logs do Sistema">
                  <UnifiedLogsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Redirect old import logs route to unified logs */}
          <Route
            path="/admin/logs-importacao"
            element={<Navigate to="/admin/logs" replace />}
          />
          
          {/* Backups Management - Admin only */}
          <Route
            path="/admin/backups"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <RouteBoundary name="Backups">
                  <BackupsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Diagnósticos - Admin only */}
          <Route
            path="/diagnosticos"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Diagnósticos">
                  <DiagnosticsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Minutas - Staff excepto indexacao */}
          <Route
            path="/minutas"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo", "diretor", "administrativo", "consultor", "intermediario"]}>
                <RouteBoundary name="Minutas">
                  <MinutasPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* RGPD Admin - Redirecionar para página dedicada */}
          <Route
            path="/admin/rgpd"
            element={<Navigate to="/rgpd-admin" replace />}
          />

          {/* Client Registrations - All staff (Registo de Clientes) */}
          <Route
            path="/registos-clientes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Registos de Clientes">
                  <ClientRegistrationsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* AI Insights - Admin and CEO only */}
          <Route
            path="/ai-insights"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="AI Insights">
                  <AIInsightsPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* AI Data Review - Admin, CEO and Administrative only */}
          <Route
            path="/revisao-dados-ia"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo", "administrativo"]}>
                <RouteBoundary name="Revisão de Dados IA">
                  <AIDataReviewPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* Audit Trail - Admin and CEO */}
          <Route
            path="/auditoria"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <RouteBoundary name="Auditoria">
                  <AuditTrailPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* RGPD Admin - Página dedicada de RGPD */}
          <Route
            path="/rgpd-admin"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo", "administrativo"]}>
                <RouteBoundary name="Administração RGPD">
                  <RGPDAdminPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* RGPD Migration - Admin, CEO and Diretor */}
          <Route
            path="/admin/migracao-rgpd"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo", "diretor"]}>
                <RouteBoundary name="Migração RGPD">
                  <RGPDMigrationPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Webmail - Email Client - Staff */}
          <Route
            path="/webmail"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Webmail">
                  <WebmailPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Filtered Process List - Staff and Admin */}
          <Route
            path="/processos-filtrados"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Processos Filtrados">
                  <FilteredProcessList />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Pending Items List - Staff and Admin */}
          <Route
            path="/pendentes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Itens Pendentes">
                  <PendingItemsList />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />
          
          {/* Ficheiros - File Explorer (S3) */}
          <Route
            path="/ficheiros"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RouteBoundary name="Explorador de Ficheiros">
                  <FilesExplorerPage />
                </RouteBoundary>
              </ProtectedRoute>
            }
          />

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
        </LazyChunkErrorBoundary>
        </Sentry.ErrorBoundary>
        <ImpersonateBanner />
        <GlobalUploadProgress />
      </BrowserRouter>
      <Toaster position="bottom-right" richColors closeButton offset="20px" visibleToasts={5} />
      </TasksProvider>
      </UploadProgressProvider>
    </AuthProvider>
      </ThemeProvider>
      {/* React Query DevTools - apenas em desenvolvimento */}
      {process.env.NODE_ENV === 'development' && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}

// Error Boundary fallback - mostrado quando React crasha
function ErrorFallback({ error, componentStack, resetError, eventId }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-4">
      <div className="max-w-md w-full text-center space-y-4">
        <div className="mx-auto w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center">
          <svg className="w-8 h-8 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Algo correu mal</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Ocorreu um erro inesperado. O nosso equipa foi notificada automaticamente.
        </p>
        <div className="flex gap-3 justify-center">
          <button
            onClick={resetError}
            className="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 text-sm font-medium"
          >
            Tentar novamente
          </button>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            Recarregar página
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;
