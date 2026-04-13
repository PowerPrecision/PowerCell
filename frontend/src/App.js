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
const KanbanPage = React.lazy(() => import("./pages/KanbanPage"));
const ProcessDetails = React.lazy(() => import("./pages/ProcessDetails"));

// ====================================================================
// PÁGINAS COM CODE SPLITTING (lazy loading)
// ====================================================================
const AdminDashboard = React.lazy(() => import("./pages/AdminDashboard"));
const StatisticsPage = React.lazy(() => import("./pages/StatisticsPage"));
const UsersManagementPage = React.lazy(() => import("./pages/UsersManagementPage"));
const ProcessesPage = React.lazy(() => import("./pages/ProcessesPage"));
const SettingsPage = React.lazy(() => import("./pages/SettingsPage"));
const FilteredProcessList = React.lazy(() => import("./pages/FilteredProcessList"));
const PendingItemsList = React.lazy(() => import("./pages/PendingItemsList"));
const SystemConfigPage = React.lazy(() => import("./pages/SystemConfigPage"));
const AIConfigPage = React.lazy(() => import("./pages/AIConfigPage"));
const AITrainingPage = React.lazy(() => import("./pages/AITrainingPage"));
const BackgroundJobsPage = React.lazy(() => import("./pages/BackgroundJobsPage"));
const NotificationSettingsPage = React.lazy(() => import("./pages/NotificationSettingsPage"));
const NotificationsPage = React.lazy(() => import("./pages/NotificationsPage"));
const UnifiedLogsPage = React.lazy(() => import("./pages/UnifiedLogsPage"));
const PropertiesPage = React.lazy(() => import("./pages/PropertiesPage"));
const ClientsPage = React.lazy(() => import("./pages/ClientsPage"));
const LeadsPage = React.lazy(() => import("./pages/LeadsPage"));
const MyClientsPage = React.lazy(() => import("./pages/MyClientsPage"));
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
const ProfileSettingsPage = React.lazy(() => import("./pages/ProfileSettingsPage"));
const FormManagementPage = React.lazy(() => import("./pages/FormManagementPage"));
const AuditTrailPage = React.lazy(() => import("./pages/AuditTrailPage"));
const FinanceDashboard = React.lazy(() => import("./pages/FinanceDashboard"));
const RGPDMigrationPage = React.lazy(() => import("./pages/RGPDMigrationPage"));
const WebmailPage = React.lazy(() => import("./pages/WebmailPage"));

// ====================================================================
// LOADING SKELETON PARA PÁGINAS LAZY
// ====================================================================
const PageLoadingSkeleton = () => (
  <div className="min-h-[400px] flex items-center justify-center bg-background p-6">
    <FullPageSkeleton />
  </div>
);

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
      // Força reload limpo
      window.location.reload();
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

// Staff roles that can access the Kanban dashboard
const STAFF_ROLES = ["consultor", "mediador", "intermediario", "consultor_intermediario", "indexacao", "diretor", "administrativo", "ceo", "admin"];

// Admin roles for automation and system config
const ADMIN_ROLES = ["admin", "ceo"];

const ProtectedRoute = ({ children, allowedRoles }) => {
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

  // Comparação case-insensitive para evitar problemas de formatação
  if (allowedRoles && !allowedRoles.map(r => r.toLowerCase()).includes(user.role?.toLowerCase())) {
    return <Navigate to="/staff" replace />;
  }

  return children;
};

const DashboardRedirect = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  // Admin vai para /admin, todos os outros staff vão para /kanban (Quadro Geral)
  // Isso melhora a performance e foco, evitando carregar o Dashboard completo
  if (user.role === "admin") {
    return <Navigate to="/admin" replace />;
  }
  return <Navigate to="/kanban" replace />;
};

// Componente para redirecionar a rota raiz baseado no estado de autenticação
const RootRedirect = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  // Se autenticado, redireciona para /kanban (Quadro Geral)
  // Isso melhora a performance e foco no fluxo de trabalho principal
  if (user) {
    if (user.role === "admin") {
      return <Navigate to="/admin" replace />;
    }
    return <Navigate to="/kanban" replace />;
  }

  // Se não autenticado, mostra o formulário público
  return <PublicClientForm />;
};

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
          <Suspense fallback={<PageLoadingSkeleton />}>
          <Routes>
          {/* Root redirect - shows form or redirects to dashboard based on auth */}
          <Route path="/" element={<RootRedirect />} />
          {/* Public client registration form - explicit route */}
          <Route path="/registo" element={<PublicClientForm />} />
          {/* Consultant form preview - view form without filling */}
          <Route path="/formulario-consultor" element={<PublicClientForm previewMode={true} />} />
          
          {/* RGPD Public Page - for client consent signature */}
          <Route path="/rgpd/:token" element={<RGPDPage />} />
          
          {/* Temporary Link Upload - for client document upload */}
          <Route path="/upload/:token" element={<TempLinkUploadPage />} />
          
          {/* Temporary Link Download - for client document download */}
          <Route path="/download/:token" element={<TempLinkDownloadPage />} />
          
          {/* Client Portal - Magic Link (passwordless, no auth required) */}
          <Route path="/portal/:token" element={<ClientPortal />} />
          
          {/* Staff login */}
          <Route path="/login" element={<LoginPage />} />
          
          {/* Dashboard redirect */}
          <Route path="/dashboard" element={<DashboardRedirect />} />
          
          {/* Kanban Page - Primary landing page for staff */}
          <Route
            path="/kanban"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <KanbanPage />
              </ProtectedRoute>
            }
          />

          {/* Staff Dashboard (Consultor, Mediador, Diretor, Administrativo, CEO) */}
          <Route
            path="/staff"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <StaffDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Admin Dashboard - Full access */}
          <Route
            path="/admin"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <AdminDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Statistics Page - Staff and Admin */}
          <Route
            path="/estatisticas"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <StatisticsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Finance Dashboard - Admin and CEO only */}
          <Route
            path="/financeiro"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <FinanceDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Users Management Page - Admin and CEO */}
          <Route
            path="/utilizadores"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <UsersManagementPage />
              </ProtectedRoute>
            }
          />
          
          {/* Processes Page - Staff and Admin */}
          <Route
            path="/processos"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <ProcessesPage />
              </ProtectedRoute>
            }
          />
          
          {/* Properties Page - Staff and Admin */}
          <Route
            path="/imoveis"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <PropertiesPage />
              </ProtectedRoute>
            }
          />
          
          {/* Clients Page - Staff and Admin */}
          <Route
            path="/clientes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <ClientsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Leads Page - Staff and Admin */}
          <Route
            path="/leads"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <LeadsPage />
              </ProtectedRoute>
            }
          />
          
          {/* My Clients - For Consultors, Intermediários e Indexação */}
          <Route
            path="/meus-clientes"
            element={
              <ProtectedRoute allowedRoles={["consultor", "intermediario", "mediador", "consultor_intermediario", "admin", "ceo", "indexacao"]}>
                <MyClientsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Process Details - Staff and Admin */}
          <Route
            path="/processo/:id"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <ProcessDetails />
              </ProtectedRoute>
            }
          />
          <Route
            path="/process/:id"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <ProcessDetails />
              </ProtectedRoute>
            }
          />
          
          {/* Settings Page - Staff and Admin */}
          <Route
            path="/definicoes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <SettingsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Profile Page - All authenticated users */}
          <Route
            path="/perfil"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <ProfilePage />
              </ProtectedRoute>
            }
          />
          
          {/* Workflow Statuses - Admin and CEO */}
          <Route
            path="/workflow-estados"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <WorkflowStatusesPage />
              </ProtectedRoute>
            } />
            <Route path="/automation" element={
              <ProtectedRoute allowedRoles={ADMIN_ROLES}>
                <AutomationPage />
              </ProtectedRoute>
            }
          />
          
          {/* Profile Settings - Admin and CEO */}
          <Route
            path="/configuracoes-perfis"
            element={
              <ProtectedRoute allowedRoles={ADMIN_ROLES}>
                <ProfileSettingsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Form Management - Admin and CEO */}
          <Route
            path="/gestao-formulario"
            element={
              <ProtectedRoute allowedRoles={ADMIN_ROLES}>
                <FormManagementPage />
              </ProtectedRoute>
            }
          />
          
          {/* Expiring Documents Dashboard - All Staff (filtered by role) */}
          <Route
            path="/validades"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <ExpiringDocumentsDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* System Configuration - Admin and CEO only */}
          <Route
            path="/configuracoes"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <SystemConfigPage />
              </ProtectedRoute>
            }
          />
          
          {/* AI Configuration - Admin only */}
          <Route
            path="/configuracoes/ia"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <AIConfigPage />
              </ProtectedRoute>
            }
          />
          
          {/* AI Training - Admin only */}
          <Route
            path="/configuracoes/treino-ia"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <AITrainingPage />
              </ProtectedRoute>
            }
          />
          
          {/* Background Jobs - Admin only */}
          <Route
            path="/admin/processos-background"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <BackgroundJobsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Notification Settings - Admin only */}
          <Route
            path="/configuracoes/notificacoes"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <NotificationSettingsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Notifications Page - All staff */}
          <Route
            path="/notificacoes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <NotificationsPage />
              </ProtectedRoute>
            }
          />
          
          {/* System Logs (Unified) - Admin only */}
          <Route
            path="/admin/logs"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <UnifiedLogsPage />
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
                <BackupsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Diagnósticos - Admin only */}
          <Route
            path="/diagnosticos"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <DiagnosticsPage />
              </ProtectedRoute>
            }
          />
          
          {/* Minutas - All staff */}
          <Route
            path="/minutas"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <MinutasPage />
              </ProtectedRoute>
            }
          />

          {/* RGPD Admin - Redirecionado para Configurações > RGPD */}
          <Route
            path="/admin/rgpd"
            element={<Navigate to="/configuracoes?tab=rgpd" replace />}
          />

          {/* Client Registrations - All staff (Registo de Clientes) */}
          <Route
            path="/registos-clientes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <ClientRegistrationsPage />
              </ProtectedRoute>
            }
          />
          
          {/* AI Insights - Admin and CEO only */}
          <Route
            path="/ai-insights"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <AIInsightsPage />
              </ProtectedRoute>
            }
          />
          
          {/* AI Data Review - Admin, CEO and Administrative only */}
          <Route
            path="/revisao-dados-ia"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo", "administrativo"]}>
                <AIDataReviewPage />
              </ProtectedRoute>
            }
          />

          {/* Audit Trail - Admin and CEO */}
          <Route
            path="/auditoria"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <AuditTrailPage />
              </ProtectedRoute>
            }
          />

          {/* RGPD Migration - Admin, CEO and Diretor */}
          <Route
            path="/admin/migracao-rgpd"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo", "diretor"]}>
                <RGPDMigrationPage />
              </ProtectedRoute>
            }
          />
          
          {/* Webmail - Email Client - Staff */}
          <Route
            path="/webmail"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <WebmailPage />
              </ProtectedRoute>
            }
          />
          
          {/* Filtered Process List - Staff and Admin */}
          <Route
            path="/processos-filtrados"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <FilteredProcessList />
              </ProtectedRoute>
            }
          />
          
          {/* Pending Items List - Staff and Admin */}
          <Route
            path="/pendentes"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <PendingItemsList />
              </ProtectedRoute>
            }
          />
          
          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
        </Suspense>
        </LazyChunkErrorBoundary>
        </Sentry.ErrorBoundary>
        <ImpersonateBanner />
        <GlobalUploadProgress />
      </BrowserRouter>
      <Toaster position="bottom-right" richColors closeButton offset="20px" />
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
