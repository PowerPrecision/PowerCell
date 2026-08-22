/**
 * AuthContext — Contexto de autenticação centralizado com JWT, refresh tokens e impersonificação.
 *
 * PORQUÊ: O PowerCell suporta múltiplos perfis por utilizador (consultor, intermediário,
 * admin, CEO) e a funcionalidade de impersonate permite ao admin visualizar o sistema
 * como outro utilizador sem partilhar credenciais. O refresh token garante sessões
 * longas sem que o utilizador tenha de fazer login repetidamente.
 *
 * DECISÕES ARQUITECTURAIS:
 * - JWT com refresh tokens: o access token tem curta duração e é renovado automaticamente
 *   2 minutos antes de expirar via scheduleTokenRefresh (setTimeout recursivo).
 * - Impressonate: o admin pode assumir a identidade de qualquer utilizador. O token
 *   original é guardado em localStorage ("originalToken") para restauração segura.
 * - Context switching (múltiplos perfis): utilizadores com additional_roles podem alternar
 *   entre perfis sem re-login. O role activo é persistido em sessionStorage.
 * - Logout revoga o refresh token no servidor para segurança.
 * - Tokens armazenados em localStorage (persistência) e activeRole em sessionStorage
 *   (sessão do browser).
 *
 * @context {AuthContext} — Fornecido via AuthProvider em App.js
 * @hook {useAuth} — Hook para consumir o contexto em componentes React
 *
 * @returns {Object} Estado e funções do contexto de autenticação:
 *   - user, token, loading, login, register, logout,
 *   - isImpersonating, originalAdminName,
 *   - impersonate, stopImpersonating,
 *   - activeRole, switchActiveRole, effectiveRole
 *
 * @example
 * // No componente raiz (App.js)
 * <AuthProvider>
 *   <AppRoutes />
 * </AuthProvider>
 *
 * // Em qualquer componente protegido
 * const { user, token, logout } = useAuth();
 */
import { createContext, useState, useEffect, useCallback, useRef, useContext, useMemo } from "react";
import api, { setAuthToken, clearAuthToken } from "../services/api";
import { hasRole } from "../utils/roleUtils";
import { collectUserRoles, getUserCompanyRecords } from "../utils/userProfiles";
// PACOTE DI — helper centralizado para rotas públicas (/portal, /rgpd, /upload, /download)
import { isPublicRoute } from "../utils/publicRoutes";

const AuthContext = createContext(null);

// ── Brand Theme Helper ──
// Aplica classe de tema no <html> consoante a empresa do utilizador.
// "Power Real Estate" ou null = tema por defeito (sem classe extra)
// "Precision Crédito" = adiciona .theme-precision que sobrepõe --color-brand
function applyBrandTheme(company) {
  document.documentElement.classList.remove('theme-precision');
  if (company && company.toLowerCase().includes('precision')) {
    document.documentElement.classList.add('theme-precision');
  }
}

const API_URL = process.env.REACT_APP_BACKEND_URL + "/api";

// Constantes para refresh tokens
const TOKEN_REFRESH_THRESHOLD = 2 * 60 * 1000; // 2 minutos antes de expirar
// Verificar a cada 60 segundos

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [, setRefreshToken] = useState(localStorage.getItem("refreshToken"));
  const [loading, setLoading] = useState(true);
  const [isImpersonating, setIsImpersonating] = useState(false);
  const [originalAdminName, setOriginalAdminName] = useState(null);
  const [activeRole, setActiveRole] = useState(null);
  const [activeCompanyId, setActiveCompanyId] = useState(null);
  const refreshTimeoutRef = useRef(null);
  const activeRoleInitialized = useRef(false);
  const activeCompanyInitialized = useRef(false);

  // Função para decodificar JWT e obter expiração
  // (stable — empty deps, no outer references)
  const getTokenExpiry = useCallback((token) => {
    if (!token) return null;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.exp ? payload.exp * 1000 : null; // Converter para ms
    } catch {
      return null;
    }
  }, []);

  // Função para renovar tokens
  const refreshTokens = useCallback(async () => {
    const currentRefreshToken = localStorage.getItem("refreshToken");
    if (!currentRefreshToken) {
      return false;
    }

    try {
      // Incluir o token actual no Authorization header para que o backend
      // possa preservar metadados de impersonate (se existirem)
      const currentToken = localStorage.getItem("token");
      const headers = { 'Content-Type': 'application/json' };
      if (currentToken) {
        headers['Authorization'] = `Bearer ${currentToken}`;
      }

      const response = await fetch(`${API_URL}/auth/refresh`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ refresh_token: currentRefreshToken })
      });

      if (!response.ok) {
        throw new Error('Refresh failed');
      }

      const data = await response.json();
      
      // Actualizar tokens
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("refreshToken", data.refresh_token);
      setAuthToken(data.access_token);
      setToken(data.access_token);
      setRefreshToken(data.refresh_token);
      
      return true;
    } catch (error) {
      console.error("Token refresh failed:", error);
      return false;
    }
  }, []);

  // Agendar próximo refresh
  const scheduleTokenRefresh = useCallback((accessToken) => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
    }

    const expiry = getTokenExpiry(accessToken);
    if (!expiry) return;

    const now = Date.now();
    const timeUntilRefresh = expiry - now - TOKEN_REFRESH_THRESHOLD;

    if (timeUntilRefresh > 0) {
      refreshTimeoutRef.current = setTimeout(async () => {
        const success = await refreshTokens();
        if (success) {
          const newToken = localStorage.getItem("token");
          scheduleTokenRefresh(newToken);
        }
      }, timeUntilRefresh);
    }
  }, [getTokenExpiry, refreshTokens]);

  useEffect(() => {
    // PACOTE DI — todas as rotas públicas (não só /portal) dispensam fetchUser.
    // Isto evita que um token de staff expirado dispare o interceptor 401
    // que redirecionaria para /login, quebrando links RGPD/upload/download
    // públicos abertos por consultores com sessão staff ativa.
    const isOnPublicRoute = isPublicRoute();

    if (token && !isOnPublicRoute) {
      setAuthToken(token);
      fetchUser();
      scheduleTokenRefresh(token);
    } else {
      setLoading(false);
    }

    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
    };
  }, [token, scheduleTokenRefresh]);

  const fetchUser = async () => {
    try {
      const response = await api.get("/auth/me");
      const userData = response.data;
      setUser(userData);

      // ── Brand Theme: aplica classe de tema consoante a empresa ──
      applyBrandTheme(userData.company);

      // Initialize activeRole only once (not on every fetchUser call)
      if (!activeRoleInitialized.current) {
        const savedRole = sessionStorage.getItem("activeRole");
        const allRoles = collectUserRoles(userData);
        if (savedRole && allRoles.includes(savedRole)) {
          setActiveRole(savedRole);
        } else {
          setActiveRole(userData.role);
          sessionStorage.setItem("activeRole", userData.role);
        }
        activeRoleInitialized.current = true;
      }
      
      // Initialize activeCompanyId only once
      if (!activeCompanyInitialized.current) {
        const savedCompanyId = localStorage.getItem("active_company_id")
          || sessionStorage.getItem("activeCompanyId");
        const companies = getUserCompanyRecords(userData);

        // PACOTE AS: Garantir que temos o currentActiveRole para comparar
        let currentActiveRole = activeRole || userData.role;
        if (!activeRoleInitialized.current) {
          currentActiveRole = sessionStorage.getItem("activeRole") || userData.role;
        }

        if (companies.length > 0) {
          if (savedCompanyId && companies.some(c => c.company_id === savedCompanyId)) {
            // Empresa guardada ainda é válida — manter
            setActiveCompanyId(savedCompanyId);
            localStorage.setItem("active_company_id", savedCompanyId);
          } else {
            // PACOTE AS: Procurar empresa que corresponde ao role ativo.
            // Se não encontrar, fallback para is_default ou primeira.
            const matchingCompany = companies.find(c => c.role === currentActiveRole)
              || companies.find(c => c.is_default)
              || companies[0];
            const companyId = matchingCompany.company_id;
            setActiveCompanyId(companyId);
            localStorage.setItem("active_company_id", companyId);
            sessionStorage.setItem("activeCompanyId", companyId);
            applyBrandTheme(matchingCompany.company_name || userData.company);
          }
        } else {
          // PACOTE DF — remove "default" fallback; se não há UCRs reais,
          // activeCompanyId fica null. A página de Perfil e o ContextSwitcher
          // lidam com este caso (mostram mensagem "sem perfis atribuídos").
          // Não escrever "null" no localStorage — seria interpretado como
          // string "null" pelo interceptor api.js.
          const fallbackId = userData.company || null;
          if (fallbackId) {
            setActiveCompanyId(fallbackId);
            localStorage.setItem("active_company_id", fallbackId);
            sessionStorage.setItem("activeCompanyId", fallbackId);
          } else {
            // PACOTE DF — limpar state e storage para não reutilizar lixo
            setActiveCompanyId(null);
            localStorage.removeItem("active_company_id");
            sessionStorage.removeItem("activeCompanyId");
          }
        }
        activeCompanyInitialized.current = true;
      }
      
      // Verificar se está em modo impersonate
      if (userData.is_impersonated) {
        setIsImpersonating(true);
        setOriginalAdminName(userData.impersonated_by_name);
      } else {
        setIsImpersonating(false);
        setOriginalAdminName(null);
      }
    } catch (error) {
      console.error("Error fetching user:", error);
      // PACOTE DI — em rotas públicas, 401 do fetchUser não redireciona.
      // O utilizador pode ter aberto um link RGPD/upload/download com um
      // token de staff expirado em localStorage; essas rotas usam tokens
      // próprios (URL) e não devem disparar logout nem redirect.
      if (error.response?.status === 401 && isPublicRoute()) {
        setLoading(false);
        return;
      }
      // Não chamar logout aqui - o interceptor já trata 401
      if (error.response?.status !== 401) {
        logout();
      }
    } finally {
      setLoading(false);
    }
  };

  // ── FIX: wrap in useCallback to stabilise AuthContext value ──
  // Without useCallback, these functions are recreated on every render,
  // which makes the context `value` useMemo recalculate every render,
  // which creates a new object reference, which causes ALL consumers
  // to re-render in a cascade. This is the ROOT CAUSE of the #310 error.
  const login = useCallback(async (email, password) => {
    // Login com refresh tokens (login-v2) - rota segura obrigatória
    const response = await api.post("/auth/login-v2", {
      email,
      password,
    });
    const { access_token, refresh_token, user: userData } = response.data;
    
    // Guardar ambos os tokens
    localStorage.setItem("token", access_token);
    localStorage.setItem("refreshToken", refresh_token);
    setAuthToken(access_token);
    setToken(access_token);
    setRefreshToken(refresh_token);
    setUser(userData);
    setIsImpersonating(false);
    setOriginalAdminName(null);

    // ── Brand Theme ──
    applyBrandTheme(userData.company);

    // Reset activeRole to primary role on login
    const primaryRole = userData.role;
    setActiveRole(primaryRole);
    sessionStorage.setItem("activeRole", primaryRole);
    activeRoleInitialized.current = true;
    
    // Agendar refresh
    scheduleTokenRefresh(access_token);
    
    return userData;
  }, [scheduleTokenRefresh]);

  const register = useCallback(async (name, email, password, phone) => {
    const response = await api.post("/auth/register", {
      name,
      email,
      password,
      phone,
    });
    const { access_token, user: userData } = response.data;
    setAuthToken(access_token);
    setToken(access_token);
    setUser(userData);
    return userData;
  }, []);

  const logout = useCallback(async () => {
    // Tentar revogar refresh token no servidor
    const currentRefreshToken = localStorage.getItem("refreshToken");
    if (currentRefreshToken) {
      try {
        await api.post("/auth/logout", { refresh_token: currentRefreshToken });
      } catch (error) {
        // Ignorar erros de logout - limpar local de qualquer forma
        console.warn("Logout server error (ignorado):", error);
      }
    }
    
    // Limpar timeout de refresh
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
    }
    
    // Limpar estado local
    localStorage.removeItem("token");
    localStorage.removeItem("refreshToken");
    clearAuthToken();
    setToken(null);
    setRefreshToken(null);
    setUser(null);
    setIsImpersonating(false);
    document.documentElement.classList.remove('theme-precision');
    setOriginalAdminName(null);

    // Clear active role and company on logout
    sessionStorage.removeItem("activeRole");
    sessionStorage.removeItem("activeCompanyId");
    setActiveRole(null);
    setActiveCompanyId(null);
    activeRoleInitialized.current = false;
    activeCompanyInitialized.current = false;
  }, []);

  const applyUserContext = useCallback((userData) => {
    const primaryRole = userData?.role || "consultor";
    setActiveRole(primaryRole);
    sessionStorage.setItem("activeRole", primaryRole);
    activeRoleInitialized.current = true;

    const companies = getUserCompanyRecords(userData);
    const matchingCompany = companies.find((c) => c.is_default)
      || companies.find((c) => c.role === primaryRole)
      || companies[0];
    const companyId = matchingCompany?.company_id || userData?.company || null;
    if (companyId) {
      setActiveCompanyId(companyId);
      localStorage.setItem("active_company_id", companyId);
      sessionStorage.setItem("activeCompanyId", companyId);
      applyBrandTheme(matchingCompany?.company_name || userData?.company);
    } else {
      setActiveCompanyId(null);
      localStorage.removeItem("active_company_id");
      sessionStorage.removeItem("activeCompanyId");
    }
    activeCompanyInitialized.current = true;
  }, []);

  // Impersonate - ver como outro utilizador
  const impersonate = useCallback(async (userId) => {
    try {
      const response = await api.post(`/admin/impersonate/${userId}`);
      const { access_token, user: userData } = response.data;
      
      // Guardar token original para poder voltar
      localStorage.setItem("originalToken", localStorage.getItem("token"));
      setAuthToken(access_token);
      setToken(access_token);
      setUser(userData);
      setIsImpersonating(true);
      setOriginalAdminName(userData.impersonated_by_name);
      // PACOTE DM: o nav e os headers devem reflectir o utilizador impersonado,
      // nunca o activeRole de admin que ficou no sessionStorage.
      applyUserContext(userData);
      
      return userData;
    } catch (error) {
      console.error("Error impersonating:", error);
      throw error;
    }
  }, [applyUserContext]);

  // Terminar impersonate e voltar à conta original
  const stopImpersonating = useCallback(async () => {
    try {
      const response = await api.post("/admin/stop-impersonate");
      const data = response.data;
      
      if (!data || !data.access_token) {
        throw new Error("Resposta inválida do servidor");
      }
      
      const { access_token, user: userData } = data;
      
      // Restaurar token original
      localStorage.removeItem("originalToken");
      setAuthToken(access_token);
      setToken(access_token);
      setUser(userData);
      setIsImpersonating(false);
      setOriginalAdminName(null);
      applyUserContext(userData);
      
      // Redirecionar para a página apropriada baseado no role
      const redirectPage = hasRole(userData, "admin") ? "/admin" : "/staff";
      window.location.href = redirectPage;
      
      return userData;
    } catch (error) {
      console.error("Error stopping impersonate:", error);
      
      // Se o servidor diz que não está em modo impersonate (ex: token foi
      // renovado e perdeu metadados), limpar o estado local e restaurar o
      // token original se existir.
      if (error.response?.status === 400) {
        const originalToken = localStorage.getItem("originalToken");
        if (originalToken) {
          localStorage.setItem("token", originalToken);
          localStorage.removeItem("originalToken");
          setAuthToken(originalToken);
          setToken(originalToken);
        }
        setIsImpersonating(false);
        setOriginalAdminName(null);
        // Re-buscar dados do utilizador para actualizar o estado
        try {
          const meResponse = await api.get("/auth/me");
          setUser(meResponse.data);
          window.location.href = "/admin";
        } catch {
          window.location.href = "/admin";
        }
        return;
      }
      
      throw error;
    }
  }, [applyUserContext]);

  // Pacote FH / C6: persistir UCR activo em /auth/active-company (user+company+role).
  const persistActiveCompany = useCallback(async (companyId, role) => {
    if (!companyId || !role) return;
    try {
      await api.post("/auth/active-company", { company_id: companyId, role });
    } catch (error) {
      console.warn("[AuthContext] Erro ao definir empresa/cargo ativo no backend:", error);
    }
  }, []);

  // ── Context Switching — Múltiplos Perfis ──
  // Recebe newRole e opcionalmente newCompanyId. Se newCompanyId não for
  // fornecido, infere a empresa a partir dos UCRs (companies / company_roles).
  // Pacote DP: actualiza React state + storage (incl. localStorage company)
  // para que páginas como "Os Meus Processos" voltem a pedir a API sem
  // depender de hard-reload. O interceptor lê os headers no pedido seguinte.
  const switchActiveRole = useCallback((newRole, newCompanyId = null) => {
    if (!newRole) return;

    let resolvedCompanyId = newCompanyId;
    if (!resolvedCompanyId) {
      const matchingCompany = getUserCompanyRecords(user).find((c) => c.role === newRole);
      if (matchingCompany) {
        resolvedCompanyId = matchingCompany.company_id;
      }
    }

    sessionStorage.setItem("activeRole", newRole);
    setActiveRole(newRole);

    if (resolvedCompanyId) {
      sessionStorage.setItem("activeCompanyId", resolvedCompanyId);
      localStorage.setItem("active_company_id", resolvedCompanyId);
      setActiveCompanyId(resolvedCompanyId);
      const matching = getUserCompanyRecords(user).find(
        (c) => c.company_id === resolvedCompanyId,
      );
      if (matching?.company_name) {
        applyBrandTheme(matching.company_name);
      }
      persistActiveCompany(resolvedCompanyId, newRole);
    }
  }, [user, persistActiveCompany]);

  // Context Switching - Múltiplas Empresas
  const switchActiveCompany = useCallback(async (companyId) => {
    if (!companyId) return;

    // PACOTE AR: guardar em localStorage (persiste entre sessões) E sessionStorage
    // (retrocompatibilidade). O interceptor api.js lê de localStorage primeiro.
    localStorage.setItem("active_company_id", companyId);
    sessionStorage.setItem("activeCompanyId", companyId);
    setActiveCompanyId(companyId);

    // Atualizar brand theme antes do reload para feedback visual imediato
    const companies = getUserCompanyRecords(user);
    const target = companies.find(c => c.company_id === companyId);
    if (target) {
      applyBrandTheme(target.company_name);
    }

    const role = target?.role || activeRole || user?.role;
    await persistActiveCompany(companyId, role);

    // PACOTE AR: Hard reload para limpar toda a cache (TanStack Query, estado
    // de componentes, etc.) e evitar fugas de dados da empresa anterior na UI.
    // É a forma mais segura num CRM multi-empresa.
    window.location.reload();
  }, [user, activeRole, persistActiveCompany]);

  // Refresh user data from /auth/me (e.g. after email config save)
  const refreshUser = useCallback(async () => {
    try {
      const response = await api.get("/auth/me");
      setUser(response.data);
    } catch (error) {
      console.error("Error refreshing user:", error);
    }
  }, []);

  // Memoize context value to prevent unnecessary re-renders of all consumers
  // when unrelated state changes. Without useMemo, every setState call creates
  // a new object reference, causing ALL useContext(AuthContext) consumers
  // to re-render even if the values they use haven't changed.
  const value = useMemo(() => ({
    user,
    token,
    loading,
    login,
    register,
    logout,
    isImpersonating,
    originalAdminName,
    impersonate,
    stopImpersonating,
    activeRole,
    switchActiveRole,
    activeCompanyId,
    switchActiveCompany,
    refreshUser,
    effectiveRole: activeRole || user?.role,
    effectiveCompanyId: activeCompanyId || user?.company,
  }), [user, token, loading, login, register, logout, isImpersonating, originalAdminName, impersonate, stopImpersonating, activeRole, switchActiveRole, activeCompanyId, switchActiveCompany, refreshUser]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
