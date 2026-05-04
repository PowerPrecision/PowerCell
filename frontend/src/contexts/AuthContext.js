/**
 * AuthContext — Contexto de autenticação centralizado com JWT, refresh tokens e impersonificação.
 *
 * PORQUÊ: O PowerCell suporta múltiplos perfis por utilizador (consultor, mediador,
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

const AuthContext = createContext(null);

const API_URL = process.env.REACT_APP_BACKEND_URL + "/api";

// Constantes para refresh tokens
const TOKEN_REFRESH_THRESHOLD = 2 * 60 * 1000; // 2 minutos antes de expirar
const TOKEN_CHECK_INTERVAL = 60 * 1000; // Verificar a cada 60 segundos

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [refreshToken, setRefreshToken] = useState(localStorage.getItem("refreshToken"));
  const [loading, setLoading] = useState(true);
  const [isImpersonating, setIsImpersonating] = useState(false);
  const [originalAdminName, setOriginalAdminName] = useState(null);
  const [activeRole, setActiveRole] = useState(null);
  const refreshTimeoutRef = useRef(null);
  const activeRoleInitialized = useRef(false);

  // Função para decodificar JWT e obter expiração
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
    if (token) {
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

      // Initialize activeRole only once (not on every fetchUser call)
      if (!activeRoleInitialized.current) {
        const savedRole = sessionStorage.getItem("activeRole");
        const allRoles = [userData.role, ...(userData.additional_roles || [])];
        if (savedRole && allRoles.includes(savedRole)) {
          setActiveRole(savedRole);
        } else {
          setActiveRole(userData.role);
          sessionStorage.setItem("activeRole", userData.role);
        }
        activeRoleInitialized.current = true;
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
      // Não chamar logout aqui - o interceptor já trata 401
      if (error.response?.status !== 401) {
        logout();
      }
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
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

    // Reset activeRole to primary role on login
    const primaryRole = userData.role;
    setActiveRole(primaryRole);
    sessionStorage.setItem("activeRole", primaryRole);
    activeRoleInitialized.current = true;
    
    // Agendar refresh
    scheduleTokenRefresh(access_token);
    
    return userData;
  };

  const register = async (name, email, password, phone) => {
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
  };

  const logout = async () => {
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
    setOriginalAdminName(null);

    // Clear active role on logout
    sessionStorage.removeItem("activeRole");
    setActiveRole(null);
    activeRoleInitialized.current = false;
  };

  // Impersonate - ver como outro utilizador
  const impersonate = async (userId) => {
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
      
      return userData;
    } catch (error) {
      console.error("Error impersonating:", error);
      throw error;
    }
  };

  // Terminar impersonate e voltar à conta original
  const stopImpersonating = async () => {
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
  };

  // Context Switching - Múltiplos Perfis
  const switchActiveRole = useCallback((newRole) => {
    if (!newRole) return;
    setActiveRole(newRole);
    // Persist to sessionStorage for reload survival
    sessionStorage.setItem("activeRole", newRole);
  }, []);

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
    refreshUser,
    effectiveRole: activeRole || user?.role,
  }), [user, token, loading, login, register, logout, isImpersonating, originalAdminName, impersonate, stopImpersonating, activeRole, switchActiveRole, refreshUser]);

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
