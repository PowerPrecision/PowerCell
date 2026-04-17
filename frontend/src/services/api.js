/**
 * api.js — Serviço centralizado de comunicação com a API Backend do PowerCell.
 *
 * PORQUÊ: Todas as comunicações frontend→backend passam por este módulo. Centralizar
 * em vez de usar axios diretamente em cada componente permite: (1) tratamento global
 * de erros consistente (401 sessão expirada, 429 rate limiting, 500 erros do servidor),
 * (2) retry automático com exponential backoff para pedidos rate-limited,
 * (3) gestão unificada de tokens JWT, e (4) feedback ao utilizador via toasts.
 * Sem esta camada, cada componente teria tratamento de erros duplicado e inconsistente.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Instância Axios singleton com baseURL configurada via env var.
 * - Interceptor de request: injecta automaticamente o token JWT do localStorage.
 * - Interceptor de response com tratamento por código de estado:
 *   - 401: limpa tokens e redireciona para login (restaura sessão original se em
 *     modo impersonate).
 *   - 403: toast de acesso negado.
 *   - 429: retry automático até 3x com exponential backoff (2s → 4s → 8s) e jitter
 *     aleatório, respeitando o header Retry-When se presente.
 *   - 404: silencioso (pode ser normal em operações condicionais).
 *   - 422: mostra mensagens de validação Pydantic amigáveis.
 *   - 500+: toast genérico de erro de servidor.
 * - Timeout de 90s para operações longas (sincronização de email, uploads grandes).
 * - Upload directo para S3 via pre-signed URLs (3 passos) com suporte a progress via XHR.
 * - Todas as funções de API exportadas como named exports para descoberta automática
 *   em IDEs.
 *
 * @example
 * import { getProcess, updateProcess, getDocuments } from '../services/api';
 *
 * // Uso normal
 * const { data } = await getProcess(processId);
 *
 * // Direct S3 Upload
 * const result = await directS3Upload({
 *   processId: 'proc-123',
 *   file: myFile,
 *   category: 'Financeiros',
 * });
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

// Retry configuration for 429 errors
const MAX_RETRIES = 3;
const INITIAL_RETRY_DELAY = 2000; // 2 seconds
const MAX_RETRY_DELAY = 30000;    // 30 seconds

// Track which URLs are currently retrying to avoid toast spam
const retryingUrls = new Set();

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
    // 429 - TOO MANY REQUESTS (Rate Limit) - Automatic Retry
    // ================================================================
    if (status === 429) {
      // Initialize retry count on config
      config.__retryCount = config.__retryCount || 0;
      const urlKey = `${config.method}:${config.url}`;
      
      if (config.__retryCount < MAX_RETRIES) {
        config.__retryCount += 1;
        
        // Exponential backoff with jitter
        const baseDelay = INITIAL_RETRY_DELAY * Math.pow(2, config.__retryCount - 1);
        const jitter = Math.random() * 1000; // 0-1s random jitter
        const retryDelay = Math.min(baseDelay + jitter, MAX_RETRY_DELAY);
        
        // Read Retry-After header if present
        const retryAfterHeader = parseInt(response.headers["retry-after"], 10);
        const finalDelay = retryAfterHeader > 0 ? (retryAfterHeader * 1000) : retryDelay;
        
        retryingUrls.add(urlKey);
        console.warn(`[API] 429 Rate limited on ${config.url}. Retry ${config.__retryCount}/${MAX_RETRIES} in ${Math.round(finalDelay / 1000)}s`);
        
        return new Promise((resolve) => {
          setTimeout(() => resolve(), finalDelay);
        }).then(() => {
          retryingUrls.delete(urlKey);
          return api(config); // Retry the original request
        });
      }
      
      // All retries exhausted
      retryingUrls.delete(urlKey);
      
      // Only show toast if this URL wasn't already showing one (avoid spam)
      if (!retryingUrls.has(urlKey)) {
        const retryAfter = response.headers["retry-after"] || "alguns segundos";
        toast({
          variant: "destructive",
          title: "Demasiados Pedidos",
          description: `O sistema está ocupado. Tente novamente em ${retryAfter}.`,
        });
      }
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
export const getProcesses = (params = {}) => api.get("/processes", { params });
export const getProcessesPaginated = (params = {}) => api.get("/processes/paginated", { params });
export const getProcess = (id) => api.get(`/processes/${id}`);
export const createProcess = (data) => api.post("/processes", data);
export const searchClients = (q, limit = 10) => api.get("/clients/search", { params: { q, limit } });
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
export const getMyClients = (params = {}) => api.get("/processes/my-clients", { params });

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

// User Email Config (Admin)
export const getUserEmailConfig = (userId) => api.get(`/admin/users/${userId}/email-config`);
export const setUserEmailConfig = (userId, data) => api.post(`/admin/users/${userId}/email-config`, data);
export const testUserEmailConfig = (userId) => api.post(`/admin/users/${userId}/email-config/test`);

// Stats
export const getStats = () => api.get("/stats");

// Activities/Comments
export const getActivities = (processId, limit = 50) => {
  const params = {};
  if (processId) params.process_id = processId;
  params.limit = limit;
  return api.get("/activities", { params });
};
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
export const getProcessTasks = (processId, includeCompleted = false) => 
  api.get("/tasks", { params: { process_id: processId, include_completed: includeCompleted } });
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

// Webmail Stats (per-user, isolated)
export const getWebmailStats = () => api.get("/emails/webmail-stats");

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

// Audit Trail
export const getAuditTrail = (params = {}) => api.get("/audit/trail", { params });
export const getAuditStats = () => api.get("/audit/stats");
export const exportAuditTrail = (params = {}) => api.get("/audit/export", { params, responseType: "blob" });
export const cleanupAuditTrail = (days) => api.post("/audit/cleanup", null, { params: { days } });

// Document Annotations (Anotações Contextuais)
export const getDocumentAnnotations = (documentPath, processId) => 
  api.get("/annotations/document", { params: { document_path: documentPath, process_id: processId } });
export const getProcessAnnotations = (processId, includeResolved = true) => 
  api.get(`/annotations/process/${processId}`, { params: { include_resolved: includeResolved } });
export const createAnnotation = (data) => api.post("/annotations", data);
export const updateAnnotation = (annotationId, data) => api.put(`/annotations/${annotationId}`, data);
export const deleteAnnotation = (annotationId) => api.delete(`/annotations/${annotationId}`);
export const resolveAnnotation = (annotationId, resolved) => 
  api.put(`/annotations/${annotationId}/resolve`, { resolved });
export const getAnnotationStats = (processId) => api.get(`/annotations/process/${processId}/stats`);

// ===== FINANCEIRO =====
export const getFinanceSummary = (params = {}) => api.get("/finance/summary", { params });
export const getFinanceMonthly = (params = {}) => api.get("/finance/monthly", { params });
export const getFinanceCommissions = (params = {}) => api.get("/finance/commissions", { params });
export const getFinancePerformance = (params = {}) => api.get("/finance/performance", { params });
export const getFinanceConfig = () => api.get("/finance/config");
export const updateFinanceConfig = (config) => api.put("/finance/config", config);

// ===== RGPD TEMPLATE =====
export const getRGPDTemplate = () => api.get("/rgpd/admin/template");
export const updateRGPDTemplate = (content) => api.put("/rgpd/admin/template", { content });

// ===== MAGIC LINK (Client Portal) =====
export const generateMagicLink = (processId) => api.post(`/processes/${processId}/magic-link`);
export const sendMagicLinkEmail = (processId) => api.post(`/processes/${processId}/magic-link/send`);

// ===== TTL MIGRATION (Data Lifecycle Management) =====
export const getTTLStatus = () => api.get("/diagnostics/ttl-status");
export const migrateTTLFields = () => api.post("/diagnostics/migrate-ttl-fields");

// ===== DIRECT S3 UPLOAD (Pre-signed URLs) =====
/**
 * Gera uma pre-signed URL para upload direto do frontend para o S3.
 * 
 * @param {Object} data - Dados do upload
 * @param {string} data.process_id - ID do processo
 * @param {string} data.filename - Nome original do ficheiro
 * @param {string} data.content_type - MIME type do ficheiro (ex: "application/pdf")
 * @param {string} [data.category="Outros"] - Categoria destino
 * @param {string} [data.custom_filename] - Nome personalizado para evitar conflitos
 * @returns {Promise} - { upload_url, file_key, expires_at, method, headers }
 */
export const generateUploadUrl = (data) => api.post("/documents/generate-upload-url", data);

/**
 * Confirma um upload direto para o S3 e regista metadados na base de dados.
 * Deve ser chamado APÓS o upload direto para o S3 ter sido concluído com sucesso.
 * 
 * @param {Object} data - Dados da confirmação
 * @param {string} data.process_id - ID do processo
 * @param {string} data.file_key - Caminho S3 do ficheiro (devolvido pelo generateUploadUrl)
 * @param {string} data.original_filename - Nome original do ficheiro
 * @param {string} data.category - Categoria do documento
 * @param {number} [data.file_size] - Tamanho do ficheiro em bytes
 * @param {string} [data.content_type] - MIME type do ficheiro
 * @returns {Promise} - { success, s3_path, temporary_url }
 */
export const confirmUpload = (data) => api.post("/documents/confirm-upload", data);

/**
 * Faz upload direto para o S3 usando uma pre-signed URL.
 * 
 * @param {string} uploadUrl - URL assinada devolvida pelo generateUploadUrl
 * @param {File|Blob} file - Ficheiro a enviar
 * @param {string} contentType - MIME type do ficheiro
 * @param {Function} [onProgress] - Callback para progresso (progressEvent) => {}
 * @returns {Promise} - { success: true } ou lança erro
 */
export const uploadDirectToS3 = async (uploadUrl, file, contentType, onProgress = null) => {
  const response = await fetch(uploadUrl, {
    method: 'PUT',
    body: file,
    headers: {
      'Content-Type': contentType,
    },
    // Usar XMLHttpRequest para suportar progress
    ...(onProgress ? { signal: null } : {})
  });
  
  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`S3 upload failed: ${response.status} - ${errorText}`);
  }
  
  return { success: true };
};

/**
 * Faz upload direto para o S3 com suporte a progress.
 * Versão que usa XMLHttpRequest para suportar onUploadProgress.
 * 
 * @param {string} uploadUrl - URL assinada devolvida pelo generateUploadUrl
 * @param {File|Blob} file - Ficheiro a enviar
 * @param {string} contentType - MIME type do ficheiro
 * @param {Function} [onProgress] - Callback para progresso (percent) => {}
 * @returns {Promise} - { success: true } ou lança erro
 */
export const uploadDirectToS3WithProgress = (uploadUrl, file, contentType, onProgress = null) => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    
    // Configurar progress callback
    if (onProgress) {
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      });
    }
    
    // Configurar completion
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve({ success: true });
      } else {
        reject(new Error(`S3 upload failed: ${xhr.status} - ${xhr.responseText}`));
      }
    });
    
    // Configurar error handling
    xhr.addEventListener('error', () => {
      reject(new Error('S3 upload failed: Network error'));
    });
    
    xhr.addEventListener('abort', () => {
      reject(new Error('S3 upload aborted'));
    });
    
    // Iniciar upload
    xhr.open('PUT', uploadUrl);
    xhr.setRequestHeader('Content-Type', contentType);
    xhr.send(file);
  });
};

/**
 * Fluxo completo de Direct S3 Upload com tratamento de erros.
 * 
 * @param {Object} options - Opções do upload
 * @param {string} options.processId - ID do processo
 * @param {File} options.file - Ficheiro a enviar
 * @param {string} options.category - Categoria destino
 * @param {string} [options.customFilename] - Nome personalizado
 * @param {Function} [options.onProgress] - Callback para progresso (percent) => {}
 * @returns {Promise} - { success, s3_path, temporary_url, normalized_filename }
 */
export const directS3Upload = async (options) => {
  const { processId, file, category, customFilename, onProgress } = options;
  
  try {
    // Passo 1: Obter pre-signed URL
    const urlResponse = await generateUploadUrl({
      process_id: processId,
      filename: file.name,
      content_type: file.type || 'application/octet-stream',
      category: category || 'Outros',
      custom_filename: customFilename,
    });
    
    const { upload_url, file_key, normalized_filename } = urlResponse.data;
    
    // Passo 2: Fazer upload direto para S3
    await uploadDirectToS3WithProgress(
      upload_url, 
      file, 
      file.type || 'application/octet-stream',
      onProgress
    );
    
    // Passo 3: Confirmar upload no backend
    const confirmResponse = await confirmUpload({
      process_id: processId,
      file_key: file_key,
      original_filename: file.name,
      category: category || 'Outros',
      file_size: file.size,
      content_type: file.type,
    });
    
    return {
      success: true,
      s3_path: confirmResponse.data.s3_path,
      temporary_url: confirmResponse.data.temporary_url,
      normalized_filename: normalized_filename,
    };
    
  } catch (error) {
    console.error('[DirectS3Upload] Error:', error);
    throw error;
  }
};

// Announcements (Mural da Equipa)
export const getAnnouncements = () => api.get("/announcements");
export const createAnnouncement = (content) => api.post("/announcements", { content });

// Export da instância axios configurada (para uso directo se necessário)
export default api;
