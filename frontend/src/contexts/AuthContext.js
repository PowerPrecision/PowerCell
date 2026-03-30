import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import api, { setAuthToken, clearAuthToken } from "../services/api";

const AuthContext = createContext(null);

const API_URL = process.env.REACT_APP_BACKEND_URL + "/api";

// Constantes para refresh tokens
const TOKEN_REFRESH_THRESHOLD = 2 * 60 * 1000; // 2 minutos antes de expirar
const TOKEN_CHECK_INTERVAL = 60 * 1000; // Verificar a cada 60 segundos

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [refreshToken, setRefreshToken] = useState(localStorage.getItem("refreshToken"));
  const [loading, setLoading] = useState(true);
  const [isImpersonating, setIsImpersonating] = useState(false);
  const [originalAdminName, setOriginalAdminName] = useState(null);
  const refreshTimeoutRef = useRef(null);

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
      const response = await fetch(`${API_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
      const redirectPage = userData.role === "admin" ? "/admin" : "/staff";
      window.location.href = redirectPage;
      
      return userData;
    } catch (error) {
      console.error("Error stopping impersonate:", error);
      // Não redirecionar para login - apenas propagar o erro para o componente tratar
      throw error;
    }
  };

  return (
    <AuthContext.Provider
      value={{ 
        user, 
        token, 
        loading, 
        login, 
        register, 
        logout,
        isImpersonating,
        originalAdminName,
        impersonate,
        stopImpersonating
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
