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
 *   - 401: tenta refresh silencioso; se falhar, bloqueia pedidos futuros (axios +
 *     fetch), limpa auth, desliga o WebSocket e redirecciona de imediato para
 *     /login (restaura sessão original se em modo impersonate).
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
import { toast } from "sonner";
import { extractErrorMessage } from "../utils/extractErrorMessage";
// PACOTE DI — helper centralizado para rotas públicas (/portal, /rgpd, /upload, /download)
import { isPublicRoute } from "../utils/publicRoutes";
import {
  forceSessionExpired,
  installFetch401Guard,
  isSessionInvalid,
} from "./sessionExpiry";
import { BACKEND_URL as RESOLVED_BACKEND_URL } from "../utils/apiBaseUrl";
import { normalizarCabecalhosDeFormData } from "../utils/formDataTransport";

// ====================================================================
// CONFIGURAÇÃO
// ====================================================================
// URL do backend — resolvido em `utils/apiBaseUrl.js` (ponto único; um host
// local nunca cai para a API de produção por omissão).
const BACKEND_URL = RESOLVED_BACKEND_URL;
const API_URL = BACKEND_URL + "/api";

// Criar instância Axios
const api = axios.create({
  baseURL: API_URL,
  timeout: 90000, // 90 segundos - aumentado para operações longas como sincronização de email
  headers: {
    // ATENÇÃO: esta predefinição aplica-se TAMBÉM aos pedidos com FormData,
    // e nesse caso o `transformRequest` do Axios converte o FormData em
    // JSON — o ficheiro vira `{}` e o servidor devolve 422. É por isso que
    // o interceptor abaixo anula este cabeçalho quando o corpo é FormData.
    // Ver `utils/formDataTransport.js`.
    "Content-Type": "application/json",
  },
});

// ====================================================================
// REQUEST DEDUPLICATION — Prevents duplicate in-flight requests
// ====================================================================
// React Strict Mode double-mounts components in development, and
// multiple components may call the same API simultaneously (e.g.
// getUpcomingExpiries in both AdminDashboard and StaffDashboard).
// This deduplication layer ensures identical in-flight requests
// share the same Promise, halving the number of actual HTTP calls
// and preventing 429 rate limit errors.
// ====================================================================

const inflightRequests = new Map();

/**
 * Generates a deduplication key from request config.
 * Key format: "METHOD:url?sortedParams"
 */
function getRequestKey(config) {
  const method = (config.method || "get").toLowerCase();
  const url = config.url || "";
  
  // Sort params to ensure consistent keys regardless of insertion order
  if (config.params && typeof config.params === "object") {
    const sortedParams = Object.keys(config.params)
      .sort()
      .map(k => `${k}=${config.params[k]}`)
      .join("&");
    return `${method}:${url}?${sortedParams}`;
  }
  
  return `${method}:${url}`;
}

/**
 * Wraps axios request with deduplication.
 * If an identical request is already in-flight, returns the same Promise.
 */
function deduplicatedRequest(config) {
  const key = getRequestKey(config);
  
  if (inflightRequests.has(key)) {
    // Request already in-flight — return existing promise
    return inflightRequests.get(key);
  }
  
  // Create new request and track it
  const requestPromise = api(config).finally(() => {
    inflightRequests.delete(key);
  });
  
  inflightRequests.set(key, requestPromise);
  return requestPromise;
}

// ====================================================================
// Wrap api.get with deduplication for GET requests only.
// POST/PUT/DELETE are never deduplicated (they must always execute).
// This transparently deduplicates all existing api.get() calls
// (e.g. getUpcomingExpiries, getStats, getProcesses) without
// requiring changes to any exported API functions.
// ====================================================================
api.get = (url, config) => deduplicatedRequest({ method: "get", url, ...config });

// ====================================================================
// AUTH CONTEXT → HEADERS
// Snapshot written by AuthContext so X-Active-Role / X-Company-Id follow
// the selected UCR even if a page overwrites sessionStorage (e.g. "all").
// ====================================================================
let authContextHeaders = { role: null, companyId: null };

export function syncAuthContextHeaders({ role, companyId } = {}) {
  authContextHeaders = {
    role: role || null,
    companyId: companyId || null,
  };
}

// ====================================================================
// INTERCEPTOR DE REQUEST
// ====================================================================
api.interceptors.request.use(
  (config) => {
    // Pacote DX — sessão inválida: não enviar mais pedidos HTTP (corta polling 401)
    if (isSessionInvalid()) {
      return Promise.reject(new axios.CanceledError("Session expired"));
    }

    // FormData: anular o `Content-Type` para o browser gerar o `boundary`.
    // Omitir NÃO chega — a predefinição da instância é `application/json` e
    // o Axios converteria o FormData em JSON. Ponto único de propósito:
    // três funções tinham este defeito e nenhuma parecia errada.
    normalizarCabecalhosDeFormData(config);

    // Adicionar token de autenticação se existir
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Injetar X-Active-Role para Context Isolation.
    // PACOTE DM: não sobrescrever se o pedido já definiu o header
    // (ex.: Área Pessoal a gravar no UCR de uma tab que não é a empresa activa).
    // Prefer AuthContext (selected UCR role) over sessionStorage, which
    // ProcessesPage used to overwrite with the sentinel "all".
    const activeRole = authContextHeaders.role
      || sessionStorage.getItem("activeRole")
      || localStorage.getItem("activeRole");
    const existingRole = typeof config.headers.get === "function"
      ? config.headers.get("X-Active-Role")
      : config.headers["X-Active-Role"];
    if (activeRole && !existingRole) {
      config.headers["X-Active-Role"] = activeRole;
    }

    // PACOTE AR: Injetar X-Company-Id para Contexto Multi-Empresa.
    // Ler de localStorage (persiste entre sessões) com fallback para
    // sessionStorage (retrocompatibilidade).
    // PACOTE DM: respeitar override por-pedido (ProfileRoleTab / EmailConfigForm).
    const activeCompanyId = authContextHeaders.companyId
      || localStorage.getItem("active_company_id")
      || sessionStorage.getItem("activeCompanyId");
    const existingCompany = typeof config.headers.get === "function"
      ? config.headers.get("X-Company-Id")
      : config.headers["X-Company-Id"];
    if (activeCompanyId && !existingCompany) {
      config.headers["X-Company-Id"] = activeCompanyId;
    }

    // Log de debug (apenas em desenvolvimento)
    if (process.env.NODE_ENV === "development") {
      console.debug(
        `[API] ${config.method?.toUpperCase()} ${config.url}`,
        config.headers["X-Active-Role"] ? `[role=${config.headers["X-Active-Role"]}]` : "",
        config.headers["X-Company-Id"] ? `[company=${config.headers["X-Company-Id"]}]` : ""
      );
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

// ====================================================================
// SILENT TOKEN REFRESH (single-flight)
// ====================================================================
// Quando um access token expira, um pedido devolve 401. Em vez de forçar
// logout imediato, tentamos renovar o token com o refresh_token e repetir
// o pedido original UMA vez. Várias respostas 401 concorrentes partilham a
// mesma promessa de refresh (single-flight) para não gastar/rodar o
// refresh_token múltiplas vezes.
//
// Usa axios "cru" (não a instância `api`) para o pedido de refresh, de forma
// a não reentrar neste próprio interceptor.
// ====================================================================
let refreshPromise = null;

async function performTokenRefresh() {
  const currentRefreshToken = localStorage.getItem("refreshToken");
  if (!currentRefreshToken) return null;

  const currentToken = localStorage.getItem("token");
  const headers = { "Content-Type": "application/json" };
  if (currentToken) {
    headers["Authorization"] = `Bearer ${currentToken}`;
  }

  try {
    const resp = await axios.post(
      `${API_URL}/auth/refresh`,
      { refresh_token: currentRefreshToken },
      { headers }
    );
    const data = resp?.data;
    if (data?.access_token) {
      localStorage.setItem("token", data.access_token);
      if (data.refresh_token) {
        localStorage.setItem("refreshToken", data.refresh_token);
      }
      return data.access_token;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Retorna a promessa de refresh partilhada (single-flight).
 * Se já houver um refresh em curso, devolve a mesma promessa.
 *
 * FIX (Set 2026 — secure token refresh): exportada para o AuthContext.
 * O backend roda o refresh_token (single-use: rotate_refresh_token revoga
 * o token antigo). Antes desta exportação, o timer preventivo do
 * AuthContext fazia um fetch próprio a /auth/refresh — dois refreshes
 * concorrentes (timer + interceptor reativo a um 401 de polling em
 * background) rodavam o MESMO token: o segundo recebia 401 e disparava
 * `forceSessionExpired()` (logout + redirect) com a sessão ainda válida.
 * Com a exportação, TODOS os mecanismos (timer, interceptor Axios e
 * fetch-guard) partilham esta mesma promessa — um único refresh por token.
 */
export function getRefreshedToken() {
  if (!refreshPromise) {
    refreshPromise = performTokenRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

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
      toast.error("Erro de Conexão", {
        description: "Não foi possível conectar ao servidor. Verifique a sua conexão.",
      });
      return Promise.reject(error);
    }
    
    const { status, data } = response;
    // PACOTE 10 — extractErrorMessage: o backend passa a devolver detail
    // ESTRUTURADO (dict com message/existing_client_id/matched_fields) no
    // 409 de cliente duplicado. Sem isto, o toast genérico receberia um
    // objecto em `description` (React error #31). Aceita string, array
    // Pydantic e objecto {msg|message}.
    const errorMessage = extractErrorMessage(
      data?.detail ?? data?.message,
      "Erro desconhecido"
    );
    
    // ================================================================
    // 401 - NÃO AUTORIZADO (Token inválido/expirado)
    // ================================================================
    if (status === 401) {
      // Não mostrar toast para tentativas de login falhadas
      const isLoginAttempt = config.url?.includes("/auth/login");
      
      // Se estiver em modo impersonate e existe originalToken, tentar restaurar
      const originalToken = localStorage.getItem("originalToken");
      if (originalToken) {
        // Estamos em modo impersonate e o token expirou ou stop-impersonate falhou
        // Tentar voltar à conta original automaticamente
        // Restaurar token original
        localStorage.setItem("token", originalToken);
        localStorage.removeItem("originalToken");
        
        // Mostrar toast a informar
        toast.info("Sessão de Visualização Terminada", {
          description: "Voltou à sua conta de administrador.",
        });
        
        // Redirecionar para admin em vez de login
        setTimeout(() => {
          window.location.href = "/admin";
        }, 1000);
        
        return Promise.reject(error);
      }

      // ============================================================
      // REFRESH SILENCIOSO: tentar renovar o token e repetir o pedido
      // original UMA vez antes de terminar a sessão. Evita logout
      // desnecessário quando só o access token expirou mas o
      // refresh_token ainda é válido.
      // ============================================================
      const isRefreshCall = config.url?.includes("/auth/refresh");
      // PACOTE DI — todas as rotas públicas dispensam refresh + redirect.
      // Não tentamos refresh silencioso em /portal, /rgpd, /upload, /download
      // porque essas rotas usam tokens próprios (URL/magic link) e não o
      // token de staff global — o refresh seria inútil e o redirect quebraria
      // a experiência pública.
      const isOnPublicRouteForRefresh = isPublicRoute();
      const hasRefreshToken = !!localStorage.getItem("refreshToken");

      if (!isLoginAttempt && !isRefreshCall && !isOnPublicRouteForRefresh && hasRefreshToken && !config._retry) {
        config._retry = true;
        const newToken = await getRefreshedToken();
        if (newToken) {
          config.headers = config.headers || {};
          config.headers.Authorization = `Bearer ${newToken}`;
          // Repetir o pedido original com o novo token.
          return api(config);
        }
        // Refresh falhou → cair no fluxo de logout abaixo.
      }

      if (!isLoginAttempt) {
        // Pacote DX — bloqueia pedidos futuros, limpa auth, desliga WS e
        // redirecciona de imediato (rotas públicas: só limpa token staff).
        forceSessionExpired();
      }

      return Promise.reject(error);
    }
    
    // ================================================================
    // 403 - PROIBIDO (Sem permissão)
    // ================================================================
    if (status === 403) {
      // `skipErrorToast` também vale aqui (antes só era honrado nos 500+).
      // Há ecrãs em que a falta de permissão NÃO é um erro genérico a
      // anunciar com um toast: o gestor de documentos, por exemplo, mostra
      // um aviso localizado dentro da própria tab (PACOTE 11) e o resto do
      // processo continua navegável. Um toast global por cima disso diria
      // duas vezes a mesma coisa, a segunda sem contexto.
      if (!config?.skipErrorToast) {
        toast.error("Acesso Negado", {
          description: "Não tem permissão para realizar esta ação.",
        });
      }
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
        toast.error("Demasiados Pedidos", {
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
      
      toast.error("Erro de Validação", {
        description: validationMessage,
      });
      return Promise.reject(error);
    }
    
    // ================================================================
    // 500+ - ERROS DE SERVIDOR
    // ================================================================
    if (status >= 500) {
      // Show the actual error detail from backend when available,
      // otherwise show generic message
      const serverDetail = extractErrorMessage(data?.detail, "");
      const isGenericError = !serverDetail || serverDetail === "Erro interno do servidor";
      const description = isGenericError
        ? "Ocorreu um erro interno. Contacte o suporte se o problema persistir."
        : serverDetail;

      const skipToast = config?.skipErrorToast;
      if (!skipToast) {
        toast.error("Erro de Servidor", { description });
      }

      // Log do erro para debugging
      console.error("[API] Server error:", {
        status,
        url: config.url,
        message: errorMessage,
        detail: data?.detail,
      });

      return Promise.reject(error);
    }
    
    // ================================================================
    // OUTROS ERROS (400, 409, etc.)
    // ================================================================
    // PACOTE 10 — `skipErrorToast` (já usado nos 500+): componentes que
    // tratam o erro eles próprios (ex.: banner bloqueante de cliente
    // duplicado no CreateClientModal) evitam o toast duplicado do
    // interceptor e mostram feedback contextual próprio.
    if (status >= 400) {
      if (!config?.skipErrorToast) {
        toast.error("Erro", { description: errorMessage });
      }
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

// Pacote DX — interceptar fetch() cru (webmail-stats, chat unread, etc.)
installFetch401Guard(getRefreshedToken);

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

/**
 * Catálogo de etiquetas em uso (ponto 15) — alimenta o `datalist` do
 * editor e o filtro das listagens. O âmbito de rede é aplicado no
 * servidor: uma lista de etiquetas sem isolamento seria uma fuga nova.
 */
export const getProcessLabels = () => api.get("/processes/labels");
export const getMyProcesses = (params = {}) => api.get("/processes/me", { params });
export const getProcessesPaginated = (params = {}) => api.get("/processes/paginated", { params });
export const getProcess = (id) => api.get(`/processes/${id}`);
export const createProcess = (data) => api.post("/processes", data);
export const searchClients = (q, limit = 10) => api.get("/clients/search", { params: { q, limit } });
export const createClientProcess = (data) => api.post("/processes/create-client", data);
export const updateProcess = (id, data) => api.put(`/processes/${id}`, data);
/**
 * Ponto 17 — vizinhos de um processo na listagem de origem (Camada 3).
 *
 * Só é chamado na FRONTEIRA da página: dentro da página aberta o
 * contexto que veio da listagem já responde sem pedido nenhum.
 * `params` é um `URLSearchParams` e vai INTACTO — um
 * `Object.fromEntries` perderia as chaves repetidas (`labels`), e a
 * vizinhança passaria a ser calculada sobre outro filtro, em silêncio.
 */
export const getProcessNeighbours = (id, params) =>
  api.get(`/processes/${id}/neighbours`, { params });
export const assignProcess = (id, {
  consultorIds,
  mediadorIds,
  indexacaoId,
  parceiroId,
  consultorId,
  mediadorId,
} = {}) => {
  const params = {};
  if (Array.isArray(consultorIds)) {
    params.consultor_ids = consultorIds.filter(Boolean).join(",");
  } else if (consultorId) {
    params.consultor_id = consultorId;
  }
  if (Array.isArray(mediadorIds)) {
    params.mediador_ids = mediadorIds.filter(Boolean).join(",");
  } else if (mediadorId) {
    params.mediador_id = mediadorId;
  }
  if (indexacaoId !== undefined && indexacaoId !== null) {
    params.indexacao_id = indexacaoId;
  }
  if (parceiroId !== undefined && parceiroId !== null) {
    params.parceiro_id = parceiroId;
  }
  return api.post(`/processes/${id}/assign`, null, { params });
};
/**
 * Quadro Kanban.
 *
 * Passa pelo cliente Axios de propósito: o interceptor injecta
 * `X-Company-Id` e `X-Active-Role`, sem os quais o backend responde
 * sobre o papel BASE do utilizador e não sobre o perfil ACTIVO. Três
 * `fetch` crus chamavam este endpoint — quinta instância do incidente
 * de 2026-09-21. Guarda: `components/kanbanTransport.test.js`.
 *
 * @param {URLSearchParams|object} [params] — filtros do quadro.
 */
export const getKanbanBoard = (params) =>
  // `URLSearchParams` segue INTACTO: o Axios serializa-o como está. Um
  // `Object.fromEntries` aqui perdia as chaves repetidas — e `labels`
  // é enviado uma vez por etiqueta, pelo que o filtro do ponto 15
  // passaria a ver só a última.
  api.get("/processes/kanban", { params });
export const moveProcessKanban = (processId, newStatus) => 
  api.put(`/processes/kanban/${processId}/move`, null, {
    params: { new_status: newStatus }
  });
export const getMyClients = (params = {}) => api.get("/processes/my-clients", { params });
export const markProcessIndexed = (processId) =>
  api.post(`/processes/${processId}/mark-indexed`);
// PACOTE 9 — Toggle "Indexado" (header dos Detalhes do Processo): liga/desliga
// is_indexed via endpoint dedicado (ON reutiliza o fluxo canónico do
// mark-indexed; OFF reverte o flag com histórico + broadcast WS).
export const setProcessIndexed = (processId, isIndexed) =>
  api.post(`/processes/${processId}/set-indexed`, { is_indexed: !!isIndexed });
// FIX (Pacote K): adicionar deleteProcess e restoreProcess para suportar o
// botão "Restaurar" na lista de processos eliminados.
export const deleteProcess = (processId) => api.delete(`/processes/${processId}`);
export const restoreProcess = (processId) => api.post(`/processes/${processId}/restore`);
// PACOTE 11 (Eixo 4) — restauro rápido de cliente no ecrã de detalhes
// (banner "Restaurar" quando o registo está eliminado). Simétrico do
// DELETE /clients/{id}: cascata restaura processos/documentos/tarefas/RGPD.
export const restoreClient = (clientId) => api.post(`/clients/${clientId}/restore`);

// Visits
export const getVisits = (processId) => api.get("/visits", { params: { process_id: processId } });

// Excel Export Permission
export const getExportPermission = (companyId = "default") =>
  api.get("/system-config/public/export-permission", { params: { company_id: companyId } });

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
/** Pacote FA — edição de eventos do calendário (PUT /deadlines/{id}). */
export const updateDeadline = (id, data) => api.put(`/deadlines/${id}`, data);
/** Pacote FA — eliminação de eventos do calendário (DELETE /deadlines/{id}). */
export const deleteDeadline = (id) => api.delete(`/deadlines/${id}`);

// Users (Admin)
export const getUsers = (role, { forAssignment } = {}) =>
  api.get("/users", {
    params: {
      ...(role ? { role } : {}),
      ...(forAssignment ? { for_assignment: true } : {}),
    },
  });
/** Staff para dropdowns de atribuição (sem admin/indexação). Pacote DT. */
export const getStaffUsers = () => api.get("/users/staff");
export const createUser = (data) => api.post("/admin/users", data);
export const updateUser = (id, data) => api.put(`/admin/users/${id}`, data);
export const deleteUser = (id) => api.delete(`/admin/users/${id}`);

// User Email Config (Admin)
export const getUserEmailConfig = (userId) => api.get(`/admin/users/${userId}/email-config`);
export const setUserEmailConfig = (userId, data) => api.post(`/admin/users/${userId}/email-config`, data);
export const testUserEmailConfig = (userId) => api.post(`/admin/users/${userId}/email-config/test`);

// Contas de email do próprio utilizador (Pacote DN.4)
export const listMyEmailAccounts = (companyId) =>
  api.get("/users/me/email-accounts", {
    params: companyId ? { company_id: companyId } : {},
    headers: companyId && companyId !== "default" ? { "X-Company-Id": companyId } : {},
  });
export const addMyEmailAccount = (data, companyId) =>
  api.post("/users/me/email-accounts", data, {
    params: companyId ? { company_id: companyId } : {},
    headers: companyId && companyId !== "default" ? { "X-Company-Id": companyId } : {},
  });
export const updateMyEmailAccount = (accountId, data) =>
  api.put(`/users/me/email-accounts/${accountId}`, data);
export const deleteMyEmailAccount = (accountId) =>
  api.delete(`/users/me/email-accounts/${accountId}`);
export const setPrimaryEmailAccount = (accountId) =>
  api.post(`/users/me/email-accounts/${accountId}/set-primary`);

// Stats
export const getStats = () => api.get("/stats");
export const getCommunicationsFeed = () => api.get("/stats/communications");

// Team Performance (Admin/CEO) — desempenho da equipa por período
export const getTeamPerformance = (params = {}) => api.get("/admin/team-performance", { params });

// Activities/Comments
export const getActivities = (processId, limit = 50) => {
  const params = {};
  if (processId) params.process_id = processId;
  params.limit = limit;
  return api.get("/activities", { params });
};
export const createActivity = (data) => api.post("/activities", data);
export const addProcessObservationNote = (processId, text) =>
  api.post(`/processes/${processId}/observation-notes`, { text });
export const deleteActivity = (id) => api.delete(`/activities/${id}`);

// History
export const getHistory = (processId) => 
  api.get("/history", { params: { process_id: processId } });
export const getProcessTimeline = (processId, limit = 40) =>
  api.get(`/processes/${processId}/timeline`, { params: { limit } });

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

// ====================================================================
// DOCUMENTOS S3 — gestor de ficheiros do processo
// ====================================================================
// Estas funções existem para que o `S3FileManager` deixe de fazer `fetch`
// cru. O interceptor do Axios injecta `Authorization`, `X-Company-Id` e
// `X-Active-Role`; um `fetch` só leva o que lhe escreverem à mão, e o que
// lhe escreviam era só o token. Sem `X-Company-Id`, `get_active_company_id_async`
// cai em `user.company` (o NOME, não o id) — o mesmo mecanismo do incidente
// de 2026-09-21. Ver AGENTS.md e `sendDocumentation.test.js`.
//
// O `responseType: "blob"` é indispensável nas que devolvem ficheiros: sem
// ele o Axios tenta interpretar bytes como texto e o PDF chega corrompido.

// ── Listagem, upload e remoção ──
// `skipErrorToast` no 403: quem não pode ver os documentos recebe um aviso
// LOCALIZADO dentro da tab (PACOTE 11); um toast global por cima seria a
// mesma informação duas vezes, a segunda sem contexto.
export const getProcessS3Files = (processId) =>
  api.get(`/documents/client/${processId}/files`, { skipErrorToast: true });
export const uploadProcessS3File = (processId, formData) =>
  api.post(`/documents/client/${processId}/upload`, formData, {
    // O `Content-Type` é tratado pelo interceptor (`formDataTransport`):
    // omiti-lo aqui NÃO bastava, porque a predefinição da instância é
    // `application/json` e o Axios convertia o FormData em JSON — era esta
    // a origem do 422 `Field required` em `file` e `category`.
    skipErrorToast: true,
  });
export const deleteProcessS3File = (processId, filePath) =>
  api.delete(`/documents/client/${processId}/file`, {
    params: { file_path: filePath },
    skipErrorToast: true,
  });
export const bulkDeleteProcessS3Files = (processId, filePaths) =>
  api.post(`/documents/client/${processId}/bulk-delete`, { file_paths: filePaths }, {
    skipErrorToast: true,
  });
export const bulkDownloadS3Files = (payload) =>
  api.post("/documents/bulk-download", payload, {
    responseType: "blob",
    skipErrorToast: true,
  });

// ── Explorador global de ficheiros (`/ficheiros`) ──
// Reaberto ao staff no Épico 10, com isolamento por rede decidido no
// servidor (`services/s3_explorer_scope.py`). Passou a falar por Axios: um
// `fetch` cru perde o `X-Company-Id` / `X-Active-Role` (incidente de
// 2026-09-21), e num endpoint cujo resultado depende do contexto isso
// deixou de ser um detalhe.
//
// `skipErrorToast` nas seis: a página mostra o erro LOCALIZADO (403 sem
// permissões, 404 pasta fora do âmbito, 503 S3 por configurar), e um toast
// global por cima seria a mesma informação duas vezes, a segunda sem
// contexto.
export const getS3FolderContents = (folderPath) =>
  api.get("/admin/s3-folder-contents", {
    params: { folder_path: folderPath || "" },
    skipErrorToast: true,
  });
export const uploadS3ExplorerFile = (formData) =>
  // Sem `Content-Type`: o interceptor anula-o para o browser gerar o
  // `boundary` (ver `utils/formDataTransport.js`).
  api.post("/admin/s3-upload", formData, { skipErrorToast: true });
export const downloadS3ExplorerFile = (path) =>
  api.get("/admin/s3-download", {
    params: { path },
    responseType: "blob",
    skipErrorToast: true,
  });
export const renameS3ExplorerEntry = (payload) =>
  api.post("/admin/s3-rename", payload, { skipErrorToast: true });
export const deleteS3ExplorerEntry = (payload) =>
  api.post("/admin/s3-delete", payload, { skipErrorToast: true });
export const createS3ExplorerFolder = (payload) =>
  api.post("/admin/s3-create-folder", payload, { skipErrorToast: true });

// ── Proxy de conteúdo (é o que evita o CORS do S3) ──
// NUNCA substituir por um URL pré-assinado do bucket: o download directo
// falha no browser por falta de cabeçalhos CORS no bucket, e foi por isso
// que este proxy existe.
export const getS3FileContent = (filePath) =>
  api.get(`/documents/proxy/${encodeURIComponent(filePath)}`, {
    responseType: "blob",
    skipErrorToast: true,
  });

// ── Conflitos e movimentação ──
export const checkS3UploadConflict = (payload) =>
  api.post("/documents/check-upload-conflict", payload, { skipErrorToast: true });
export const checkS3MoveConflict = (payload) =>
  api.post("/documents/check-move-conflict", payload, { skipErrorToast: true });
export const moveS3File = (processId, payload) =>
  api.post(`/documents/move-file/${processId}`, payload, { skipErrorToast: true });
export const checkEmployerNif = (nif) =>
  api.get(`/documents/check-employer-nif/${nif}`, { skipErrorToast: true });

// ── Ferramentas de IA (backend exige admin/CEO/diretor) ──
// É aqui que o `X-Active-Role` conta: sem ele o backend resolve o papel
// pelo JWT e um utilizador multi-perfil recebe 403 no perfil errado.
export const aiAnalyzeS3Documents = (processId, formData) =>
  api.post(`/documents/ai-analyze/${processId}`, formData, { skipErrorToast: true });
// Épico 9 — extracção por ficheiro. Recebe o CAMINHO S3 e devolve os dados
// lidos, comparados com a ficha. Não grava nada: quem grava continua a ser
// `aiApplyS3Suggestions`, depois de o consultor confirmar no diálogo.
export const extractDocumentData = (processId, s3Path) =>
  api.post(
    `/processes/${processId}/documents/extract`,
    { s3_path: s3Path },
    { skipErrorToast: true },
  );
export const aiApplyS3Suggestions = (processId, suggestions) =>
  api.post(`/documents/ai-apply-suggestions/${processId}`, suggestions, {
    skipErrorToast: true,
  });
export const organizeS3Documents = (processId, payload) =>
  api.post(`/documents/organize/${processId}`, payload, { skipErrorToast: true });
export const categorizeAllS3Documents = (processId) =>
  api.post(`/documents/categorize-all/${processId}`, {}, { skipErrorToast: true });
export const renameAllS3DocumentsSmart = (processId) =>
  api.post(`/documents/rename-all-smart/${processId}`, {}, { skipErrorToast: true });
export const renameS3DocumentSmart = (processId, payload) =>
  api.post(`/documents/rename-smart/${processId}`, payload, { skipErrorToast: true });

// ── Mapeamento cliente ↔ pasta S3 (admin) ──
export const getClientS3Mappings = (search) =>
  api.get("/admin/client-s3-mappings", {
    params: { search: search || "" },
    skipErrorToast: true,
  });
export const saveClientS3Mapping = (processId, s3Folder) =>
  api.post("/admin/client-s3-mappings", null, {
    params: s3Folder
      ? { process_id: processId, s3_folder: s3Folder }
      : { process_id: processId },
    skipErrorToast: true,
  });

// ── Geração de minutas a partir do processo ──
export const generateProcessTemplate = (processId, template) =>
  api.get(`/templates/process/${processId}/generate/${template}/download`, {
    responseType: "blob",
    skipErrorToast: true,
  });

/**
 * Lê o corpo de erro de um pedido feito com `responseType: "blob"`.
 *
 * ARMADILHA QUE ISTO RESOLVE: com `responseType: "blob"`, o Axios devolve
 * o corpo como Blob TAMBÉM quando o pedido falha. `error.response.data.detail`
 * fica `undefined` e a mensagem do servidor desaparece em silêncio — o
 * utilizador vê "Erro ao gerar minuta" em vez da lista de campos em falta.
 *
 * @param {any} error - O erro apanhado do Axios.
 * @returns {Promise<object>} O corpo em JSON, ou `{}` se não for legível.
 */
export const readBlobErrorBody = async (error) => {
  const corpo = error?.response?.data;
  if (!corpo) return {};
  if (typeof Blob !== "undefined" && corpo instanceof Blob) {
    try {
      return JSON.parse(await corpo.text());
    } catch {
      return {};
    }
  }
  return typeof corpo === "object" ? corpo : {};
};

// Notas de voz do consultor (Épico 7)
// Vai pelo `api` do Axios e nunca por `fetch` cru: só o interceptor injecta
// o token e os cabeçalhos de empresa/papel (ver AGENTS.md, incidente
// 2026-09-21). O backend responde de imediato com o `task_id` — a
// transcrição e a extração correm em background.
export const uploadVoiceNote = (processId, file, onProgress) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.post(`/processes/${processId}/voice-notes`, formData, {
    // Sem `Content-Type` à mão: o interceptor anula-o e o browser gera o
    // `boundary`. Escrever "multipart/form-data" sem boundary só funcionava
    // porque o Axios o limpava lá dentro — depender disso é depender de um
    // pormenor interno da biblioteca.
    onUploadProgress: (evento) => {
      if (!onProgress || !evento.total) return;
      onProgress(Math.round((evento.loaded * 100) / evento.total));
    },
  });
};
export const getVoiceNotes = (processId) =>
  api.get(`/processes/${processId}/voice-notes`);

// S3 Document Storage (Current)
export const getClientS3Files = (processId) => 
  api.get(`/documents/client/${processId}/files`);
// `uploadClientS3File` foi REMOVIDA: duplicava `uploadProcessS3File` para o
// mesmo endpoint, não tinha um único chamador (nem na história do
// repositório) e escrevia o `Content-Type` à mão. Uma segunda porta para o
// mesmo sítio é onde o defeito seguinte se instala sem ser visto.
export const deleteClientS3File = (processId, filePath) => 
  api.delete(`/documents/client/${processId}/file`, { params: { file_path: filePath } });
export const getS3DownloadUrl = (processId, filePath) => 
  api.get(`/documents/client/${processId}/download`, { params: { file_path: filePath } });

// AI Document Analysis
export const analyzeDocument = (data) => api.post("/ai/analyze-document", data);
export const analyzeOneDriveDocument = (data) => api.post("/ai/analyze-onedrive-document", data);
export const getSupportedDocuments = () => api.get("/ai/supported-documents");
export const getProcessAiAnalysis = (processId) =>
  api.get(`/processes/${processId}/analyze`);
export const generateProcessAiAnalysis = (processId, force = false) =>
  api.post(`/processes/${processId}/analyze`, null, {
    params: { force },
    skipErrorToast: true,
  });
export const getProcessAiAgentAnalysis = (processId) =>
  api.get(`/ai-agent/analyze/${processId}`);

// PACOTE DJ — Revisão Human-in-the-Loop de Documentos
// A IA sugere metadados (categoria, validade, nome, filename) em campos `suggested_*`
// paralelos; o consultor aprova/rejeita via 4 endpoints dedicados.
// O fluxo antigo (`/documents/ai-analyze/{process_id}`) escrevia directamente em `ai_*`
// e auto-aplicava; este novo fluxo pede revisão explícita antes de aplicar.
export const analyzeDocumentForReview = (docId) =>
  api.post(`/documents/${docId}/ai-analyze-review`);
export const applyAIReview = (docId, data) =>
  api.post(`/documents/${docId}/apply-ai-review`, data);
export const rejectAIReview = (docId, data) =>
  api.post(`/documents/${docId}/reject-ai-review`, data);
export const getPendingReviews = (processId) =>
  api.get(`/documents/process/${processId}/pending-review`);

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
export const getAdminUsers = (role, { forAssignment } = {}) =>
  api.get("/admin/users", {
    params: {
      ...(role ? { role } : {}),
      ...(forAssignment ? { for_assignment: true } : {}),
    },
  });
/** Lista completa para a Tab Utilizadores da Administração (Pacote EB).
 *  Sem `for_assignment` — inclui admin, indexação e inativos. */
export const getAllAdminUsers = () => api.get("/admin/users");

/**
 * Painel de administração: utilizadores paginados, com pesquisa
 * server-side por nome, email ou empresa (ponto 11).
 *
 * Endpoint SEPARADO de `/admin/users` de propósito — esse serve também
 * as dropdowns de atribuição, que precisam da lista inteira. Paginar o
 * partilhado partia-as em silêncio.
 */
export const getAdminUsersPaginated = (params = {}) =>
  api.get("/admin/users/paginated", { params });
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
export const getActiveBackgroundTasks = () => api.get("/tasks/active");
export const acknowledgeBackgroundTask = (taskId) => api.post(`/tasks/${taskId}/acknowledge`);
export const cancelBackgroundTask = (taskId) => api.delete(`/tasks/${taskId}/cancel`);

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

// ====================================================================
// WEBMAIL (Ponto 8, Fase 2) — TUDO pelo Axios, zero `fetch` cru
// ====================================================================
//
// O `WebmailPage` tinha 28 chamadas `fetch` com um `webmailHeaders()` a
// escrever `Authorization`, `X-Company-Id` e `X-Active-Role` à mão —
// SEXTA instância do incidente de 2026-09-21. O interceptor que injecta
// esses cabeçalhos vive no cliente Axios; um `fetch` cru só leva o que
// lhe escreverem, e o que lá faltar muda silenciosamente a conta de
// email usada e o âmbito da caixa.
//
// `company_id` (Fase 1) vai em `params` como qualquer outro filtro: é o
// separador que manda, não o header.

export const getWebmailEmails = (params) =>
  api.get("/emails/webmail", { params });

// `box`/`company_id` opcionais. Mantém a assinatura antiga (uma string
// solta = a caixa) para não partir os chamadores que já existiam.
export const getWebmailStats = (boxOuParams) => {
  const params =
    typeof boxOuParams === "string"
      ? (boxOuParams ? { box: boxOuParams } : {})
      : (boxOuParams || {});
  return api.get("/emails/webmail-stats", { params });
};

/** Ponto 8 — as empresas do utilizador: um separador por cada. */
export const getWebmailCompanies = () => api.get("/emails/webmail/companies");

export const syncWebmail = (params) =>
  api.post("/emails/webmail/sync", null, { params });
export const syncWebmailUser = (params) =>
  api.post("/emails/webmail/sync-user", null, { params });
export const getEmailJobStatus = (jobId) => api.get(`/emails/jobs/${jobId}`);

export const getPersonalEmailAccounts = () =>
  api.get("/users/me/email-accounts", { params: { scope: "all" } });

// ── Etiquetas e pastas ──
export const getEmailLabels = () => api.get("/emails/labels");
export const getEmailFolders = () => api.get("/emails/folders");
export const createEmailFolder = (data) => api.post("/emails/folders", data);
export const updateEmailFolder = (folderId, data) =>
  api.put(`/emails/folders/${folderId}`, data);
export const deleteEmailFolder = (folderId) =>
  api.delete(`/emails/folders/${folderId}`);
export const moveEmailsToFolder = (data) =>
  api.post("/emails/emails/move-to-folder", data);
export const applyEmailLabels = (data) => api.post("/emails/labels/apply", data);

// ── Um email ──
export const getWebmailEmail = (emailId) => api.get(`/emails/${emailId}`);
export const markEmail = (emailId, data) =>
  api.post(`/emails/${emailId}/mark`, data);
export const deleteEmailPermanent = (emailId) =>
  api.delete(`/emails/${emailId}/permanent`);
export const associateEmailToProcess = (data) =>
  api.post("/emails/associate", data);

// ── Envio ──
export const sendWebmailEmail = (payload, account) =>
  api.post("/emails/send", payload, { params: account ? { account } : {} });
export const cancelEmailSend = (sendId) =>
  api.post(`/emails/${sendId}/cancel-send`);

// O Content-Type é deliberadamente omitido: o Axios tem de o gerar com o
// `boundary` — ver `utils/formDataTransport.js` e o interceptor de pedido.
export const uploadEmailAttachment = (formData) =>
  api.post("/emails/attachments/upload", formData);

// `responseType: "blob"` faz o corpo de ERRO vir também como Blob — ler
// com `readBlobErrorBody`, senão a mensagem do servidor desaparece.
export const downloadWebmailAttachment = (attachmentId, params) =>
  api.get(`/webmail/attachments/${encodeURIComponent(attachmentId)}`, {
    params,
    responseType: "blob",
    skipErrorToast: true,
  });

// Clients
export const getClients = (params = {}) => {
    const cleanParams = Object.fromEntries(
        Object.entries(params).filter(([_, v]) => v !== '' && v !== null && v !== undefined)
    );
    return api.get("/clients", { params: cleanParams });
};
export const getClient = (id) => api.get(`/clients/${id}`);
export const getClientFiles = (clientId) => api.get(`/documents/client/${clientId}/files`);
/**
 * Cria um novo cliente.
 * PACOTE 10 — aceita config axios opcional (ex.: { skipErrorToast: true }
 * para os formulários que mostram banner próprio de cliente duplicado
 * no 409 em vez do toast genérico do interceptor).
 * @param {object} data - Payload do cliente (nome, email, nif, telefone, fonte...)
 * @param {object} [config] - Config axios (skipErrorToast, headers, ...)
 */
export const createClient = (data, config) => api.post("/clients", data, config);
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

// ===== FINANCEIRO (Legacy Dashboard) =====
export const getFinanceSummary = (params = {}) => api.get("/finance/summary", { params });
export const getFinanceMonthly = (params = {}) => api.get("/finance/monthly", { params });
export const getFinanceCommissions = (params = {}) => api.get("/finance/commissions", { params });
export const exportFinanceCommissionsCSV = (params = {}) => api.get("/finance/commissions/export", { params, responseType: "blob" });
export const getFinancePerformance = (params = {}) => api.get("/finance/performance", { params });
export const getFinanceConfig = () => api.get("/finance/config");
export const updateFinanceConfig = (config) => api.put("/finance/config", config);

// ===== FINANCEIRO — Módulo Fase 2 (FinanceConfig + ProcessFinance) =====
// FinanceConfig (configuração de honorários por empresa)
export const getFinanceConfigs = (params = {}) => api.get("/finance/configs", { params });
export const getFinanceConfigById = (configId) => api.get(`/finance/configs/${configId}`);
export const createFinanceConfig = (data) => api.post("/finance/configs", data);
export const updateFinanceConfigById = (configId, data) => api.put(`/finance/configs/${configId}`, data);
export const deleteFinanceConfigById = (configId) => api.delete(`/finance/configs/${configId}`);

// ProcessFinance (registos financeiros por processo — snapshots)
export const getProcessFinances = (params = {}) => api.get("/finance/processes", { params });
export const getProcessFinanceById = (financeId) => api.get(`/finance/processes/${financeId}`);
export const createProcessFinance = (data) => api.post("/finance/processes", data);
export const updateProcessFinance = (financeId, data) => api.put(`/finance/processes/${financeId}`, data);
export const getProcessFinanceSummary = (params = {}) => api.get("/finance/processes/summary", { params });

// Pool Distribution (modelo global_pool — fecho de mês)
export const getPoolDistribution = (params = {}) => api.get("/finance/pool-distribution", { params });
export const exportPoolDistributionCSV = (params = {}) => api.get("/finance/pool-distribution/export", { params, responseType: "blob" });

// ===== RGPD TEMPLATE =====
export const getRGPDTemplate = () => api.get("/rgpd/admin/template");
export const updateRGPDTemplate = (content) => api.put("/rgpd/admin/template", { content });

// PACOTE DE — Download RGPD pré-preenchido (PDF para assinatura manual)
// PACOTE 5 — `titular` define o titular alvo do PDF RGPD pré-preenchido:
// "first" (1º titular, default) ou "second" (2º titular).
export const downloadRGPDF = (processId, titular = "first") =>
  api.get(`/rgpd/pdf/${processId}`, {
    params: { titular },
    responseType: "blob",
  });

// ===== MINUTA TEMPLATE =====
export const getMinutaTemplate = () => api.get("/rgpd/admin/minuta-template");
export const updateMinutaTemplate = (content) => api.put("/rgpd/admin/minuta-template", { content });
export const getMinutaTemplateVersions = () => api.get("/rgpd/admin/minuta-template/versions");
export const getMinutaTemplateVersion = (versionId) => api.get(`/rgpd/admin/minuta-template/versions/${versionId}`);

// ===== RGPD TEMPLATE VERSIONS =====
export const getRGPDTemplateVersions = () => api.get("/rgpd/admin/template/versions");
export const getRGPDTemplateVersion = (versionId) => api.get(`/rgpd/admin/template/versions/${versionId}`);

// ===== MAGIC LINK (Client Portal) =====
export const generateMagicLink = (processId) => api.post(`/processes/${processId}/generate-magic-link`);
export const sendMagicLinkEmail = (processId) => api.post(`/processes/${processId}/generate-magic-link/send`);
// PACOTE DC — Reenviar acesso ao Portal por client_id (resolve o process_id ativo internamente)
export const resendPortalAccess = (clientId) => api.post(`/clients/${clientId}/resend-portal-access`);

// ===== IMPERSONATE CLIENT (Ver como Cliente) =====
// FIX (Pacote K): o ProcessDetails.js importa impersonateClient mas este export
// não existia, causando erro de build no CI ("impersonateClient is not exported
// by src/services/api.js"). Reutiliza o endpoint generate-magic-link (que já
// filtra is_deleted e devolve 404 para processos eliminados) e mapeia a
// resposta para incluir `url` — que é o campo que o handler em ProcessDetails.js
// espera (res?.data?.url).
export const impersonateClient = (processId) =>
  api.post(`/processes/${processId}/generate-magic-link`).then((res) => ({
    ...res,
    data: {
      ...res.data,
      url: res.data?.magic_link || res.data?.link || res.data?.url,
    },
  }));

// Impersonate — "Ver como Cliente": devolve URL com ?token=JWT para auto-login no Portal
// (Pacote M) Usa o endpoint dedicado /portal/impersonate/{id} que devolve o JWT na query
// string, permitindo auto-login imediato no ClientPortal (sem passar pelo ecrã de login).
export const impersonateClientPortal = (processId) =>
  api.get(`/portal/impersonate/${processId}`);

// ===== PORTAL DOCUMENT REQUESTS (Admin manages client doc requests) =====
export const getPortalDocRequests = (processId) => api.get(`/documents/portal-requests/${processId}`);
export const createPortalDocRequest = (processId, data) => api.post(`/documents/portal-requests/${processId}`, data);
export const updatePortalDocRequest = (processId, documentId, data) => api.put(`/documents/portal-requests/${processId}/${documentId}`, data);
export const deletePortalDocRequest = (processId, documentId) => api.delete(`/documents/portal-requests/${processId}/${documentId}`);

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

// ===== MURAL DA EQUIPA (Announcements) =====
export const getAnnouncements = (limit = 50) => api.get("/announcements", { params: { limit } });
export const createAnnouncement = (data) => api.post("/announcements", data);
export const deleteAnnouncement = (id) => api.delete(`/announcements/${id}`);
export const toggleAnnouncementLike = (id) => api.post(`/announcements/${id}/like`);
export const markAnnouncementRead = (id) => api.post(`/announcements/${id}/read`);
export const getAnnouncementReaders = (id) => api.get(`/announcements/readers/${id}`);

// ===== PROCESS MIGRATION (Fase 1: Separação Cliente ↔ Processo) =====
export const getProcessMigrationStatus = () => api.get("/admin/process-migration/status");
export const dryRunProcessMigration = () => api.post("/admin/process-migration/dry-run");
export const runProcessMigration = () => api.post("/admin/process-migration/run");
export const rollbackProcessMigration = () => api.post("/admin/process-migration/rollback");

// ===== SYSTEM CHANGELOG (Mural de Atualizações gerado por IA) =====
export const getSystemChangelogs = (limit = 5) => api.get("/system/changelog", { params: { limit } });
export const generateChangelogAI = (data = {}) => api.post("/system/changelog/generate-ai", data);
export const diagnoseChangelog = () => api.get("/system/changelog/diagnose");

// ===== COMPANIES CRUD (Multi-Tenant — Gestão de Empresas) =====
// ── Automações (Lote 4, ponto 14) ──────────────────────────────────
// Pelo cliente Axios, nunca por `fetch`: o interceptor é o único sítio
// que injecta `X-Company-Id` / `X-Active-Role`, e a página das
// Automações fazia cinco chamadas cruas — quinta instância do incidente
// de 2026-09-21.
export const getAutomationRules = (activeOnly = false) =>
  api.get("/admin/automation/rules", { params: activeOnly ? { active_only: true } : {} });
export const createAutomationRule = (data) => api.post("/admin/automation/rules", data);
export const updateAutomationRule = (id, data) =>
  api.put(`/admin/automation/rules/${id}`, data);
export const deleteAutomationRule = (id) => api.delete(`/admin/automation/rules/${id}`);
// `getWorkflowStatuses` já existe mais acima neste ficheiro — não repetir.
// Sinais vitais do motor de background (leitura).
export const getAutomationsEngineStatus = () => api.get("/automations");

/**
 * Empresas do âmbito do utilizador (a sua REDE), paginadas.
 *
 * O `page`/`size` fecha o tecto de 200 que truncava em silêncio: à
 * empresa 201 a UI respondia que ela não existe (ponto 11).
 */
export const getCompanies = (search, { page, size } = {}) =>
  api.get("/admin/companies", {
    params: {
      ...(search ? { search } : {}),
      ...(page ? { page } : {}),
      ...(size ? { size } : {}),
    },
  });
export const getCompany = (id) => api.get(`/admin/companies/${id}`);
export const createCompany = (data) => api.post("/admin/companies", data);
export const updateCompany = (id, data) => api.put(`/admin/companies/${id}`, data);
export const testCompanyEmailConnection = (data) => api.post("/admin/companies/test-email-connection", data);
export const deleteCompany = (id) => api.delete(`/admin/companies/${id}`);
export const uploadCompanyLogo = (id, file) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.post(`/admin/companies/${id}/logo`, formData);
};

// ===== USER COMPANY ROLES (UCR — acessos multi-empresa) =====
export const getUserCompanyRoles = (params = {}) =>
  api.get("/admin/user-company-roles", { params });
export const getUserRoles = (userId) => api.get(`/admin/users/${userId}/roles`);
export const createUserCompanyRole = (data) =>
  api.post("/admin/user-company-roles", data);
export const assignUserRole = (userId, data) =>
  api.post(`/admin/users/${userId}/roles`, data);
export const updateUserCompanyRole = (roleId, data) =>
  api.put(`/admin/user-company-roles/${roleId}`, data);
export const deleteUserCompanyRole = (roleId, userId) =>
  userId
    ? api.delete(`/admin/users/${userId}/roles/${roleId}`)
    : api.delete(`/admin/user-company-roles/${roleId}`);

// ===== COMPANY EMAIL CONFIG (IMAP/SMTP por empresa — Pacote AS) =====
export const getCompanyEmailConfig = (companyName) =>
  api.get(`/admin/company-email-configs/${encodeURIComponent(companyName)}`);
export const upsertCompanyEmailConfig = (data) =>
  api.post("/admin/company-email-configs", data);
export const deleteCompanyEmailConfig = (companyName) =>
  api.delete(`/admin/company-email-configs/${encodeURIComponent(companyName)}`);

// ===== CLIENT REGISTRATIONS (Admin — registos do formulário público) =====
export const getClientRegistrations = (params = {}) =>
  api.get("/admin/client-registrations", { params });
export const getClientRegistration = (processId) =>
  api.get(`/admin/client-registrations/${processId}`);
export const updateClientRegistration = (processId, data) =>
  api.put(`/admin/client-registrations/${processId}`, data);
export const deleteClientRegistration = (processId) =>
  api.delete(`/admin/client-registrations/${processId}`);
export const getClientRegistrationsStats = () =>
  api.get("/admin/client-registrations/stats/summary");

// ===== BACKGROUND JOBS (Centro de Operações — importações/análises em massa) =====
export const getBackgroundJobs = (status) =>
  api.get("/ai/bulk/background-jobs", { params: status ? { status } : {} });
export const getBackgroundJob = (jobId) =>
  api.get(`/ai/bulk/background-jobs/${jobId}`);
export const getBackgroundJobMetrics = (days = 7) =>
  api.get("/ai/bulk/background-jobs/metrics", { params: { days } });
export const getBackgroundJobNotifications = (unreadOnly = true) =>
  api.get("/ai/bulk/background-jobs/notifications", { params: { unread_only: unreadOnly } });
export const markBackgroundJobNotificationRead = (notificationId) =>
  api.put(`/ai/bulk/background-jobs/notifications/${notificationId}/read`);
export const clearBackgroundJobNotifications = () =>
  api.delete("/ai/bulk/background-jobs/notifications/clear");
export const deleteBackgroundJob = (jobId) =>
  api.delete(`/ai/bulk/background-jobs/${jobId}`);
export const cancelBackgroundJob = (jobId) =>
  api.post(`/ai/bulk/background-jobs/${jobId}/cancel`);
export const pauseBackgroundJob = (jobId) =>
  api.post(`/ai/bulk/background-jobs/${jobId}/pause`);
export const resumeBackgroundJob = (jobId) =>
  api.post(`/ai/bulk/background-jobs/${jobId}/resume`);
export const cleanupStuckBackgroundJobs = (hours = 2) =>
  api.post("/ai/bulk/background-jobs/cleanup-stuck", null, { params: { hours } });
export const clearFinishedBackgroundJobs = () =>
  api.delete("/ai/bulk/background-jobs");
export const clearAllBackgroundJobs = () =>
  api.post("/ai/bulk/background-jobs/clear-all");

// Export da instância axios configurada (para uso directo se necessário)
export default api;
