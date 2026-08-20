/**
 * sessionExpiry.js — Logout forçado e bloqueio de pedidos após sessão inválida.
 *
 * PORQUÊ: Tokens expirados geravam loops de reconexão WebSocket (HTTP 403 / close
 * 4001-4002) e polling HTTP (401 em /emails/webmail-stats, 404 em /notifications).
 * Sem um intercetor global, o frontend continuava a bater no servidor.
 *
 * DECISÕES:
 * - Flag de módulo `sessionInvalid`: após falha de auth confirmada, axios e fetch
 *   rejeitam pedidos futuros sem ir à rede.
 * - `forceSessionExpired` é idempotente (um toast, um redirect).
 * - Rotas públicas (/portal, /rgpd, /upload, /download) limpam o token de staff
 *   mas NÃO redireccionam nem bloqueiam fetch — usam tokens próprios.
 * - Redirect imediato via location.replace (sem setTimeout) para cortar polling.
 */

import { toast } from "sonner";
import { isPublicRoute } from "../utils/publicRoutes.js";

export const WS_CLOSE_TOKEN_EXPIRED = 4001;
export const WS_CLOSE_TOKEN_INVALID = 4002;
export const WS_CLOSE_POLICY_VIOLATION = 1008;
export const WS_CLOSE_HTTP_FORBIDDEN = 4403;

const AUTH_LOCAL_KEYS = [
  "token",
  "refreshToken",
  "user",
  "originalToken",
  "active_company_id",
];
const AUTH_SESSION_KEYS = ["activeRole", "activeCompanyId"];

const AUTH_REASON_RE = /403|401|unauthorized|forbidden|token expir|token inv[aá]lid|authentication|sess[aã]o expir/i;

let sessionInvalid = false;
let expiryInProgress = false;
const cleanupCallbacks = new Set();

export function isSessionInvalid() {
  return sessionInvalid;
}

/** Test helper — resets module state between unit tests. */
export function resetSessionExpiryForTests() {
  sessionInvalid = false;
  expiryInProgress = false;
  cleanupCallbacks.clear();
}

export function registerSessionCleanup(callback) {
  if (typeof callback === "function") {
    cleanupCallbacks.add(callback);
  }
  return () => cleanupCallbacks.delete(callback);
}

export function clearStaffAuthStorage() {
  AUTH_LOCAL_KEYS.forEach((key) => {
    try {
      localStorage.removeItem(key);
    } catch {
      // ignore quota / private-mode errors
    }
  });
  AUTH_SESSION_KEYS.forEach((key) => {
    try {
      sessionStorage.removeItem(key);
    } catch {
      // ignore
    }
  });
}

/**
 * Detecta fecho WebSocket por falha de autenticação (códigos custom 4001/4002
 * ou handshake HTTP 403, que os browsers reportam como 1006 + reason).
 */
export function isAuthWebSocketClose(event) {
  if (!event) return false;
  const code = Number(event.code);
  if (
    code === WS_CLOSE_TOKEN_EXPIRED
    || code === WS_CLOSE_TOKEN_INVALID
    || code === WS_CLOSE_POLICY_VIOLATION
    || code === WS_CLOSE_HTTP_FORBIDDEN
    || code === 403
    || code === 401
  ) {
    return true;
  }
  const reason = String(event.reason || "");
  return AUTH_REASON_RE.test(reason);
}

function runCleanupCallbacks() {
  cleanupCallbacks.forEach((cb) => {
    try {
      cb();
    } catch (err) {
      console.warn("[sessionExpiry] cleanup callback failed:", err);
    }
  });
}

/**
 * Termina a sessão de staff: bloqueia pedidos, limpa storage, desliga WS e
 * redirecciona para /login. Seguro chamar várias vezes (no-op após a primeira).
 */
export function forceSessionExpired({ silent = false } = {}) {
  if (expiryInProgress) return;
  expiryInProgress = true;

  const onPublicRoute = typeof window !== "undefined" && isPublicRoute();

  if (!onPublicRoute) {
    sessionInvalid = true;
  }

  runCleanupCallbacks();
  clearStaffAuthStorage();

  if (onPublicRoute) {
    expiryInProgress = false;
    return;
  }

  if (!silent && typeof window !== "undefined" && window.location?.pathname !== "/login") {
    toast.error("Sessão Expirada", {
      description: "A sua sessão expirou. Por favor, faça login novamente.",
    });
  }

  if (typeof window !== "undefined" && window.location?.pathname !== "/login") {
    window.location.replace("/login");
  }
}

export function resolveRequestUrl(input) {
  if (!input) return "";
  if (typeof input === "string") return input;
  if (typeof URL !== "undefined" && input instanceof URL) return input.href;
  if (typeof input === "object" && input.url) return input.url;
  return "";
}

export function isAuthExemptUrl(url) {
  if (!url) return true;
  return /\/api\/auth\/login(?:-v2)?(?:\?|$|\/)/.test(url)
    || /\/api\/auth\/register(?:\?|$|\/)/.test(url)
    || /\/api\/auth\/refresh(?:\?|$|\/)/.test(url)
    || /\/api\/public\//.test(url)
    || /\/api\/temp-links\/public\//.test(url);
}

export function isStaffApiUrl(url) {
  if (!url) return false;
  if (/amazonaws\.com|googleapis\.com|sentry\.io/i.test(url)) return false;
  return url.includes("/api/");
}

function readHeader(headers, name) {
  if (!headers) return null;
  const lower = name.toLowerCase();
  if (typeof headers.get === "function") {
    return headers.get(name) || headers.get(lower);
  }
  if (Array.isArray(headers)) {
    const hit = headers.find(([key]) => String(key).toLowerCase() === lower);
    return hit ? hit[1] : null;
  }
  return headers[name] || headers[lower] || headers.Authorization || null;
}

export function requestUsedStaffToken(input, init = {}) {
  let token = null;
  try {
    token = localStorage.getItem("token");
  } catch {
    return false;
  }
  if (!token) return false;
  const header = readHeader(init?.headers, "Authorization")
    || (input && typeof input === "object" ? readHeader(input.headers, "Authorization") : null);
  return typeof header === "string" && header.includes(token);
}

function withBearerToken(input, init, token) {
  const headers = new Headers(
    init?.headers || (input && typeof input === "object" ? input.headers : undefined) || {},
  );
  headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

/**
 * Wrapper de window.fetch: bloqueia pedidos após sessão inválida e trata 401
 * de APIs staff (refresh silencioso uma vez, depois logout forçado).
 */
export function createAuthFetch(originalFetch, { getRefreshedToken } = {}) {
  return async function authFetch(input, init = {}, isRetry = false) {
    if (sessionInvalid) {
      const abortError = typeof DOMException === "function"
        ? new DOMException("Session expired", "AbortError")
        : new Error("Session expired");
      return Promise.reject(abortError);
    }

    const response = await originalFetch(input, init);
    if (response.status !== 401 || isRetry) {
      return response;
    }

    const url = resolveRequestUrl(input);
    if (!isStaffApiUrl(url) || isAuthExemptUrl(url)) {
      return response;
    }
    if (typeof window !== "undefined" && isPublicRoute()) {
      return response;
    }
    if (!requestUsedStaffToken(input, init)) {
      return response;
    }

    if (typeof getRefreshedToken === "function") {
      const newToken = await getRefreshedToken();
      if (newToken) {
        const nextInit = withBearerToken(input, init, newToken);
        return authFetch(input, nextInit, true);
      }
    }

    forceSessionExpired();
    return response;
  };
}

export function installFetch401Guard(getRefreshedToken) {
  if (typeof window === "undefined" || window.__pcFetch401Guard) return;
  if (typeof window.fetch !== "function") return;
  window.__pcFetch401Guard = true;
  const originalFetch = window.fetch.bind(window);
  window.fetch = createAuthFetch(originalFetch, { getRefreshedToken });
}
