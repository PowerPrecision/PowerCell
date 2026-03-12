/**
 * usePushNotifications Hook
 * Hook React para gerir notificações push
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
    
    // Registar service worker automaticamente
    if (pushService.checkSupport()) {
      pushService.registerServiceWorker().then(() => {
        // Verificar se já está subscrito
        if (pushService.swRegistration) {
          pushService.swRegistration.pushManager.getSubscription().then(sub => {
            setIsSubscribed(!!sub);
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
