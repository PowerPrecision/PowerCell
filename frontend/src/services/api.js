/**
 * ====================================================================
 * API SERVICE - CREDITOIMO
 * ====================================================================
 * Serviço centralizado para comunicação com a API Backend.
 * 
 * FUNCIONALIDADES:
 * - Instância Axios configurada com interceptors
 * - Global Error Handling (401, 403, 429, 500, etc.)
 * - Retry automático para erros de rede
 * - Toast notifications para erros
 * - Gestão automática de tokens
 * 
 * ====================================================================
 */
import axios from "axios";
import { toast } from "../hooks/use-toast";

// ====================================================================
// CONFIGURAÇÃO
// ====================================================================
// URL do backend - usa variável de ambiente ou fallback para produção
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://powercell.onrender.com";
const API_URL = BACKEND_URL + "/api";

// Criar instância Axios
const api = axios.create({
  baseURL: API_URL,
  timeout: 90000, // 90 segundos - aumentado para operações longas como sincronização de email
  headers: {
    "Content-Type": "application/json",
  },
});

// ====================================================================
// INTERCEPTOR DE REQUEST
// ====================================================================
api.interceptors.request.use(
  (config) => {
    // Adicionar token de autenticação se existir
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Log de debug (apenas em desenvolvimento)
    if (process.env.NODE_ENV === "development") {
      console.debug(`[API] ${config.method?.toUpperCase()} ${config.url}`);
    }
    
    return config;
  },
  (error) => {
    console.error("[API] Request error:", error);
    return Promise.reject(error);
  }
);

// ====================================================================
// INTERCEPTOR DE RESPONSE - GLOBAL ERROR HANDLING
// ====================================================================
api.interceptors.response.use(
  // Sucesso - apenas retorna a response
  (response) => response,
  
  // Erro - tratamento global
  async (error) => {
    const { response, config } = error;
    
    // ================================================================
    // ERRO DE REDE (sem response do servidor)
    // ================================================================
    if (!response) {
      toast({
        variant: "destructive",
        title: "Erro de Conexão",
        description: "Não foi possível conectar ao servidor. Verifique a sua conexão.",
      });
      return Promise.reject(error);
    }
    
    const { status, data } = response;
    const errorMessage = data?.detail || data?.message || "Erro desconhecido";
    
    // ================================================================
    // 401 - NÃO AUTORIZADO (Token inválido/expirado)
    // ================================================================
    if (status === 401) {
      // Não mostrar toast para tentativas de login falhadas
      const isLoginAttempt = config.url?.includes("/auth/login");
      const isStopImpersonate = config.url?.includes("/stop-impersonate");
      
      // Se estiver em modo impersonate e existe originalToken, tentar restaurar
      const originalToken = localStorage.getItem("originalToken");
      if (originalToken) {
        // Estamos em modo impersonate e o token expirou ou stop-impersonate falhou
        // Tentar voltar à conta original automaticamente
        console.log("[API] Token de impersonate expirou ou stop-impersonate falhou, restaurando sessão original...");
        
        // Restaurar token original
        localStorage.setItem("token", originalToken);
        localStorage.removeItem("originalToken");
        
        // Mostrar toast a informar
        toast({
          title: "Sessão de Visualização Terminada",
          description: "Voltou à sua conta de administrador.",
        });
        
        // Redirecionar para admin em vez de login
        setTimeout(() => {
          window.location.href = "/admin";
        }, 1000);
        
        return Promise.reject(error);
      }
      
      if (!isLoginAttempt) {
        toast({
          variant: "destructive",
          title: "Sessão Expirada",
          description: "A sua sessão expirou. Por favor, faça login novamente.",
        });
        
        // Limpar dados de autenticação
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        localStorage.removeItem("originalToken");
        
        // Redirecionar para login (com delay para mostrar toast)
        setTimeout(() => {
          window.location.href = "/login";
        }, 1500);
      }
      
      return Promise.reject(error);
    }
    
    // ================================================================
    // 403 - PROIBIDO (Sem permissão)
    // ================================================================
    if (status === 403) {
      toast({
        variant: "destructive",
        title: "Acesso Negado",
        description: "Não tem permissão para realizar esta ação.",
      });
      return Promise.reject(error);
    }
    
    // ================================================================
    // 429 - TOO MANY REQUESTS (Rate Limit)
    // ================================================================
    if (status === 429) {
      const retryAfter = response.headers["retry-after"] || "alguns segundos";
      
      toast({
        variant: "destructive",
        title: "Demasiados Pedidos",
        description: `O sistema está ocupado. Tente novamente em ${retryAfter}.`,
      });
      return Promise.reject(error);
    }
    
    // ================================================================
    // 404 - NÃO ENCONTRADO
    // ================================================================
    if (status === 404) {
      // Não mostrar toast para 404 (pode ser normal em algumas situações)
      console.warn(`[API] Recurso não encontrado: ${config.url}`);
      return Promise.reject(error);
    }
    
    // ================================================================
    // 422 - ERRO DE VALIDAÇÃO
    // ================================================================
    if (status === 422) {
      // Extrair mensagens de validação
      let validationMessage = "Dados inválidos.";
      
      if (data?.detail && Array.isArray(data.detail)) {
        validationMessage = data.detail
          .map((err) => err.msg || err.message)
          .join(", ");
      } else if (typeof data?.detail === "string") {
        validationMessage = data.detail;
      }
      
      toast({
        variant: "destructive",
        title: "Erro de Validação",
        description: validationMessage,
      });
      return Promise.reject(error);
    }
    
    // ================================================================
    // 500+ - ERROS DE SERVIDOR
    // ================================================================
    if (status >= 500) {
      toast({
        variant: "destructive",
        title: "Erro de Servidor",
        description: "Ocorreu um erro interno. Contacte o suporte se o problema persistir.",
      });
      
      // Log do erro para debugging
      console.error("[API] Server error:", {
        status,
        url: config.url,
        message: errorMessage,
      });
      
      return Promise.reject(error);
    }
    
    // ================================================================
    // OUTROS ERROS (400, etc.)
    // ================================================================
    if (status >= 400) {
      toast({
        variant: "destructive",
        title: "Erro",
        description: errorMessage,
      });
    }
    
    return Promise.reject(error);
  }
);

// ====================================================================
// FUNÇÕES AUXILIARES
// ====================================================================

/**
 * Configura o token de autenticação para todas as requests.
 */
export const setAuthToken = (token) => {
  if (token) {
    localStorage.setItem("token", token);
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    localStorage.removeItem("token");
    delete api.defaults.headers.common["Authorization"];
  }
};

/**
 * Remove o token de autenticação.
 */
export const clearAuthToken = () => {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  delete api.defaults.headers.common["Authorization"];
};

/**
 * Verifica se o utilizador está autenticado.
 */
export const isAuthenticated = () => {
  return !!localStorage.getItem("token");
};


// ====================================================================
// ENDPOINTS DA API
// ====================================================================

// Processes
export const getProcesses = () => api.get("/processes");
export const getProcess = (id) => api.get(`/processes/${id}`);
export const createProcess = (data) => api.post("/processes", data);
export const createClientProcess = (data) => api.post("/processes/create-client", data);
export const updateProcess = (id, data) => api.put(`/processes/${id}`, data);
export const assignProcess = (id, consultorId, mediadorId, indexacaoId) => 
  api.post(`/processes/${id}/assign`, null, {
    params: { consultor_id: consultorId, mediador_id: mediadorId, indexacao_id: indexacaoId }
  });
export const getKanbanBoard = () => api.get("/processes/kanban");
export const moveProcessKanban = (processId, newStatus) => 
  api.put(`/processes/kanban/${processId}/move`, null, {
    params: { new_status: newStatus }
  });
export const getMyClients = () => api.get("/processes/my-clients");

// Deadlines
export const getDeadlines = (processId) => 
  api.get("/deadlines", { params: { process_id: processId } });
export const getAllDeadlines = () => api.get("/deadlines");
export const getMyDeadlines = () => api.get("/deadlines/my-deadlines");
export const getCalendarDeadlines = (consultorId, mediadorId) => 
  api.get("/deadlines/calendar", { 
    params: { consultor_id: consultorId, mediador_id: mediadorId } 
  });
export const createDeadline = (data) => api.post("/deadlines", data);
export const updateDeadline = (id, data) => api.put(`/deadlines/${id}`, data);
export const deleteDeadline = (id) => api.delete(`/deadlines/${id}`);

// Users (Admin)
export const getUsers = (role) => 
  api.get("/users", { params: { role } });
export const createUser = (data) => api.post("/admin/users", data);
export const updateUser = (id, data) => api.put(`/admin/users/${id}`, data);
export const deleteUser = (id) => api.delete(`/admin/users/${id}`);

// Stats
export const getStats = () => api.get("/stats");

// Activities/Comments
export const getActivities = (processId) => 
  api.get("/activities", { params: { process_id: processId } });
export const createActivity = (data) => api.post("/activities", data);
export const deleteActivity = (id) => api.delete(`/activities/${id}`);

// History
export const getHistory = (processId) => 
  api.get("/history", { params: { process_id: processId } });

// Workflow Statuses
export const getWorkflowStatuses = () => api.get("/admin/workflow-statuses");
export const createWorkflowStatus = (data) => api.post("/admin/workflow-statuses", data);
export const updateWorkflowStatus = (id, data) => api.put(`/admin/workflow-statuses/${id}`, data);
export const deleteWorkflowStatus = (id) => api.delete(`/admin/workflow-statuses/${id}`);

// OneDrive Links (Manual)
export const getProcessOneDriveLinks = (processId) => 
  api.get(`/onedrive/links/${processId}`);
export const addProcessOneDriveLink = (processId, data) => 
  api.post(`/onedrive/links/${processId}`, data);
export const deleteProcessOneDriveLink = (processId, linkId) => 
  api.delete(`/onedrive/links/${processId}/${linkId}`);

// OneDrive (Legacy - API based) - DEPRECATED, use S3 instead
export const getOneDriveFiles = (folder) => 
  api.get("/onedrive/files", { params: { folder } });
export const getClientOneDriveFiles = (clientName, subfolder) => 
  api.get(`/onedrive/files/${encodeURIComponent(clientName)}`, { params: { subfolder } });
export const getOneDriveDownloadUrl = (itemId) => 
  api.get(`/onedrive/download/${itemId}`);
export const getOneDriveStatus = () => api.get("/onedrive/status");

// S3 Document Storage (Current)
export const getClientS3Files = (processId) => 
  api.get(`/documents/client/${processId}/files`);
export const uploadClientS3File = (processId, formData, onProgress) => 
  api.post(`/documents/client/${processId}/upload`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: onProgress
  });
export const deleteClientS3File = (processId, filePath) => 
  api.delete(`/documents/client/${processId}/file`, { params: { file_path: filePath } });
export const getS3DownloadUrl = (processId, filePath) => 
  api.get(`/documents/client/${processId}/download`, { params: { file_path: filePath } });

// AI Document Analysis
export const analyzeDocument = (data) => api.post("/ai/analyze-document", data);
export const analyzeOneDriveDocument = (data) => api.post("/ai/analyze-onedrive-document", data);
export const getSupportedDocuments = () => api.get("/ai/supported-documents");

// Document Expiry Management
export const getDocumentExpiries = (processId) => 
  api.get("/documents/expiry", { params: { process_id: processId } });
export const getUpcomingExpiries = (days = 30) => 
  api.get("/documents/expiry/upcoming", { params: { days } });
export const createDocumentExpiry = (data) => api.post("/documents/expiry", data);
export const updateDocumentExpiry = (id, data) => api.put(`/documents/expiry/${id}`, data);
export const deleteDocumentExpiry = (id) => api.delete(`/documents/expiry/${id}`);
export const getDocumentTypes = () => api.get("/documents/types");

// Alerts & Notifications
export const getNotifications = (unreadOnly = false) => 
  api.get("/alerts/notifications", { params: { unread_only: unreadOnly } });
export const markNotificationRead = (id) => 
  api.put(`/alerts/notifications/${id}/read`);
export const getProcessAlerts = (processId) => 
  api.get(`/processes/${processId}/alerts`);
export const getAlertsByProcess = (processId) => 
  api.get(`/alerts/process/${processId}`);
export const createDeedReminder = (processId, deedDate) => 
  api.post(`/alerts/deed-reminder/${processId}`, null, { params: { deed_date: deedDate } });

// Admin - Impersonate
export const impersonateUser = (userId) => api.post(`/admin/impersonate/${userId}`);
export const stopImpersonate = () => api.post("/admin/stop-impersonate");

// Admin Users (CRUD completo)
export const getAdminUsers = (role) => api.get("/admin/users", { params: { role } });
export const createAdminUser = (data) => api.post("/admin/users", data);
export const updateAdminUser = (id, data) => api.put(`/admin/users/${id}`, data);
export const deleteAdminUser = (id) => api.delete(`/admin/users/${id}`);

// Tasks
export const getTasks = (params = {}) => api.get("/tasks", { params });
export const getMyTasks = (includeCompleted = false) => 
  api.get("/tasks/my-tasks", { params: { include_completed: includeCompleted } });
export const getProcessTasks = (processId) => 
  api.get("/tasks", { params: { process_id: processId } });
export const createTask = (data) => api.post("/tasks", data);
export const updateTask = (id, data) => api.put(`/tasks/${id}`, data);
export const completeTask = (id) => api.put(`/tasks/${id}/complete`);
export const reopenTask = (id) => api.put(`/tasks/${id}/reopen`);
export const deleteTask = (id) => api.delete(`/tasks/${id}`);

// Emails
export const getProcessEmails = (processId, direction = null) => 
  api.get(`/emails/process/${processId}`, { params: { direction } });
export const getEmailStats = (processId) => api.get(`/emails/stats/${processId}`);
export const createEmail = (data) => api.post("/emails", data);
export const updateEmail = (id, data) => api.put(`/emails/${id}`, data);
export const deleteEmail = (id) => api.delete(`/emails/${id}`);
export const syncProcessEmails = (processId, days = 30) => 
  api.post(`/emails/sync/${processId}`, null, { params: { days } });
export const sendEmailViaServer = (data) => api.post("/emails/send", null, { params: data });
export const testEmailConnection = (account = null) => 
  api.get("/emails/test-connection", { params: { account } });
export const getEmailAccounts = () => api.get("/emails/accounts");

// Emails Monitorizados
export const getMonitoredEmails = (processId) => api.get(`/emails/monitored/${processId}`);
export const addMonitoredEmail = (processId, email) => 
  api.post(`/emails/monitored/${processId}`, null, { params: { email } });
export const removeMonitoredEmail = (processId, email) => 
  api.delete(`/emails/monitored/${processId}/${encodeURIComponent(email)}`);

// Auto-Email Drafts (Rascunhos Automáticos)
export const getAutoDrafts = (limit = 20) => 
  api.get("/emails/drafts", { params: { limit } });
export const getAutoDraftStats = () => api.get("/emails/drafts/stats");
export const editAutoDraft = (draftId, data) => api.put(`/emails/drafts/${draftId}`, data);
export const sendAutoDraft = (draftId, account = "power") => 
  api.post(`/emails/drafts/${draftId}/send`, null, { params: { account } });
export const deleteAutoDraft = (draftId) => api.delete(`/emails/drafts/${draftId}`);
export const createAutoDraft = (processId, docType) =>
  api.post("/emails/drafts/create", { process_id: processId, doc_type: docType });

// Trello
export const getTrelloStatus = () => api.get("/trello/status");
export const syncProcessWithTrello = (processId) => api.post(`/trello/sync/${processId}`);

// Clients
export const getClients = (params = {}) => api.get("/clients", { params });
export const getClient = (id) => api.get(`/clients/${id}`);
export const createClient = (data) => api.post("/clients", data);
export const updateClient = (id, data) => api.put(`/clients/${id}`, data);
export const deleteClient = (id) => api.delete(`/clients/${id}`);

// Leads
export const getLeadsByStatus = () => api.get("/leads/by-status");
export const getLeads = (params = {}) => api.get("/leads", { params });
export const getLead = (id) => api.get(`/leads/${id}`);
export const createLead = (data) => api.post("/leads", data);
export const updateLead = (id, data) => api.put(`/leads/${id}`, data);
export const deleteLead = (id) => api.delete(`/leads/${id}`);
export const scrapePropertyUrl = (url) => api.post("/leads/scrape-url", { url });

// Properties
export const getProperties = (params = {}) => api.get("/properties", { params });
export const getProperty = (id) => api.get(`/properties/${id}`);
export const createProperty = (data) => api.post("/properties", data);
export const updateProperty = (id, data) => api.put(`/properties/${id}`, data);
export const deleteProperty = (id) => api.delete(`/properties/${id}`);

// GDPR
export const getGdprStatistics = () => api.get("/gdpr/statistics");
export const getGdprEligible = (params = {}) => api.get("/gdpr/eligible", { params });
export const anonymizeData = (data) => api.post("/gdpr/anonymize", data);
export const runGdprBatch = (data) => api.post("/gdpr/batch", data);
export const exportGdprData = (processId) => api.get(`/gdpr/export/${processId}`);
export const getGdprAudit = (params = {}) => api.get("/gdpr/audit", { params });

// Backup
export const getBackupStatistics = () => api.get("/backup/statistics");
export const triggerBackup = (data) => api.post("/backup/trigger", data);
export const getBackupHistory = (params = {}) => api.get("/backup/history", { params });

// Temporary Links (for document upload/download)
export const createTempLink = (data) => api.post("/temp-links/create", data, {
  headers: { 'Content-Type': 'multipart/form-data' }
});
export const getProcessTempLinks = (processId) => api.get(`/temp-links/process/${processId}`);
export const cancelTempLink = (linkId) => api.post(`/temp-links/${linkId}/cancel`);
export const deleteTempLink = (linkId) => api.delete(`/temp-links/${linkId}`);

// Export da instância axios configurada (para uso directo se necessário)
export default api;
