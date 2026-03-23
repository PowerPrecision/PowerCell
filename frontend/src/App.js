import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import { UploadProgressProvider } from "./contexts/UploadProgressContext";
import ImpersonateBanner from "./components/ImpersonateBanner";
import GlobalUploadProgress from "./components/GlobalUploadProgress";
import React, { Suspense } from "react";
import { FullPageSkeleton } from "./components/ui/skeletons";

// ====================================================================
// PÁGINAS COM CARREGAMENTO IMEDIATO (críticas para UX)
// ====================================================================
import LoginPage from "./pages/LoginPage";
import PublicClientForm from "./pages/PublicClientForm";
import StaffDashboard from "./pages/StaffDashboard";
import ProcessDetails from "./pages/ProcessDetails";
import RGPDPage from "./pages/RGPDPage";
import TempLinkUploadPage from "./pages/TempLinkUploadPage";
import TempLinkDownloadPage from "./pages/TempLinkDownloadPage";

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
const NIFMappingsPage = React.lazy(() => import("./pages/NIFMappingsPage"));
const NotificationSettingsPage = React.lazy(() => import("./pages/NotificationSettingsPage"));
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
const RGPDAdminPage = React.lazy(() => import("./pages/RGPDAdminPage"));
const ClientRegistrationsPage = React.lazy(() => import("./pages/ClientRegistrationsPage"));
const WorkflowStatusesPage = React.lazy(() => import("./pages/WorkflowStatusesPage"));

// ====================================================================
// LOADING SKELETON PARA PÁGINAS LAZY
// ====================================================================
const PageLoadingSkeleton = () => (
  <div className="min-h-[400px] flex items-center justify-center bg-background p-6">
    <FullPageSkeleton />
  </div>
);

// IdealistaImportPage movido para modal na página de Leads
import "./App.css";

// Staff roles that can access the Kanban dashboard
const STAFF_ROLES = ["consultor", "mediador", "intermediario", "consultor_intermediario", "gestor_documentos", "indexacao", "diretor", "administrativo", "ceo", "admin"];

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

  if (allowedRoles && !allowedRoles.includes(user.role)) {
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

  // Admin vai para /admin, CEO vai para /staff (menu limitado)
  if (user.role === "admin") {
    return <Navigate to="/admin" replace />;
  }
  return <Navigate to="/staff" replace />;
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

  // Se autenticado, redireciona para o dashboard apropriado
  if (user) {
    if (user.role === "admin") {
      return <Navigate to="/admin" replace />;
    }
    return <Navigate to="/staff" replace />;
  }

  // Se não autenticado, mostra o formulário público
  return <PublicClientForm />;
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <UploadProgressProvider>
        <BrowserRouter>
        <Suspense fallback={<PageLoadingSkeleton />}>
        <Routes>
          {/* Root redirect - shows form or redirects to dashboard based on auth */}
          <Route path="/" element={<RootRedirect />} />
          {/* Public client registration form - explicit route */}
          <Route path="/registo" element={<PublicClientForm />} />
          
          {/* RGPD Public Page - for client consent signature */}
          <Route path="/rgpd/:token" element={<RGPDPage />} />
          
          {/* Temporary Link Upload - for client document upload */}
          <Route path="/upload/:token" element={<TempLinkUploadPage />} />
          
          {/* Temporary Link Download - for client document download */}
          <Route path="/download/:token" element={<TempLinkDownloadPage />} />
          
          {/* Staff login */}
          <Route path="/login" element={<LoginPage />} />
          
          {/* Dashboard redirect */}
          <Route path="/dashboard" element={<DashboardRedirect />} />
          
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
          
          {/* My Clients - For Consultors and Intermediários */}
          <Route
            path="/meus-clientes"
            element={
              <ProtectedRoute allowedRoles={["consultor", "intermediario", "mediador", "consultor_intermediario", "admin", "ceo"]}>
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
          
          {/* Workflow Statuses - Admin and CEO */}
          <Route
            path="/workflow-estados"
            element={
              <ProtectedRoute allowedRoles={["admin", "ceo"]}>
                <WorkflowStatusesPage />
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
          
          {/* System Configuration - Admin only */}
          <Route
            path="/configuracoes"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
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
          
          {/* NIF Mappings - Admin only */}
          <Route
            path="/admin/mapeamentos-nif"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <NIFMappingsPage />
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

          {/* RGPD Admin - Admin and Staff */}
          <Route
            path="/admin/rgpd"
            element={
              <ProtectedRoute allowedRoles={STAFF_ROLES}>
                <RGPDAdminPage />
              </ProtectedRoute>
            }
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
        <ImpersonateBanner />
        <GlobalUploadProgress />
      </BrowserRouter>
      <Toaster position="bottom-right" richColors closeButton offset="20px" />
      </UploadProgressProvider>
    </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
