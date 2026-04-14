/**
 * usePushNotifications — Hook para gestão de notificações push via Web Push API.
 *
 * PORQUÊ: O PowerCell precisa de notificar os utilizadores de eventos importantes
 * (novos processos, prazos próximos, mensagens) mesmo quando o browser está minimizado.
 * As notificações push via Service Worker permitem isto sem necessidade de polling contínuo.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Registo automático do Service Worker: ao montar, verifica suporte e regista o SW.
 * - Verificação de subscrição existente: não cria uma nova subscrição se já existe uma
 *   activa (evita subscrições duplicadas no backend).
 * - Verificação do backend: consulta /api/notifications/push/status para confirmar se a
 *   subscrição está válida do lado do servidor (pode ter sido revogada).
 * - Silenciar erros de VAPID: se a chave VAPID não está configurada, o hook funciona
 *   em modo degradado sem crashar.
 * - Interface explícita enable/disable: o utilizador tem controlo total sobre as notificações.
 *
 * @context {AuthContext} — Consome token para autenticação no backend
 *
 * @returns {Object} Estado e funções de controlo:
 *   - isSupported {boolean} — true se o browser suporta notificações push
 *   - permission {string} — "default", "granted" ou "denied"
 *   - isSubscribed {boolean} — true se há subscrição activa
 *   - loading {boolean} — true durante operações assíncronas
 *   - enableNotifications {Function} — Pedir permissão e subscrever
 *   - disableNotifications {Function} — Cancelar subscrição
 *   - showNotification {Function} — Mostrar notificação local
 */
import { useState, useEffect, useCallback } from 'react';
import pushService from '../services/pushNotifications';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export function usePushNotifications() {
  const [isSupported, setIsSupported] = useState(false);
  const [permission, setPermission] = useState('default');
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [loading, setLoading] = useState(false);

  // Verificar suporte e permissão inicial
  useEffect(() => {
    setIsSupported(pushService.checkSupport());
    setPermission(pushService.getPermissionState());
    
    // Registar service worker automaticamente (apenas registo, sem subscrição)
    if (pushService.checkSupport()) {
      pushService.registerServiceWorker().then((registration) => {
        // Apenas verificar se já existe subscrição activa (não criar nova)
        if (registration) {
          registration.pushManager.getSubscription().then(sub => {
            setIsSubscribed(!!sub);
          }).catch(() => {
            // Silenciar erro de subscrição (VAPID key pode não estar configurada)
          });
        }
      });
    }
    
    // Verificar estado no backend
    checkBackendStatus();
  }, []);

  /**
   * Verificar estado de subscrição no backend
   */
  const checkBackendStatus = async () => {
    const token = localStorage.getItem('token');
    if (!token || !API_URL) return;
    
    try {
      const response = await fetch(`${API_URL}/api/notifications/push/status`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.is_subscribed) {
          setIsSubscribed(true);
        }
      }
    } catch (error) {
      console.warn('Erro ao verificar estado push no backend:', error);
    }
  };

  /**
   * Pedir permissão e subscrever
   */
  const enableNotifications = useCallback(async () => {
    setLoading(true);
    try {
      // Pedir permissão
      const permResult = await pushService.requestPermission();
      setPermission(permResult.permission || 'denied');
      
      if (!permResult.success) {
        return { success: false, error: 'Permissão negada' };
      }

      // Subscrever (inclui registo no backend)
      const subResult = await pushService.subscribe();
      setIsSubscribed(subResult.success);
      
      return subResult;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Desactivar notificações
   */
  const disableNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const result = await pushService.unsubscribe();
      if (result.success) {
        setIsSubscribed(false);
      }
      return result;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Mostrar notificação local
   */
  const showNotification = useCallback(async (title, options = {}) => {
    if (permission !== 'granted') {
      console.warn('Notificações não permitidas');
      return false;
    }
    return pushService.showLocalNotification(title, options);
  }, [permission]);

  return {
    isSupported,
    permission,
    isSubscribed,
    loading,
    enableNotifications,
    disableNotifications,
    showNotification
  };
}

export default usePushNotifications;
