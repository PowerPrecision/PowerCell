/**
 * Push Notifications Service
 * Serviço para gerir notificações push no browser
 */

const VAPID_PUBLIC_KEY = process.env.REACT_APP_VAPID_PUBLIC_KEY;
const API_URL = process.env.REACT_APP_BACKEND_URL;

class PushNotificationService {
  constructor() {
    this.swRegistration = null;
    this.isSupported = 'serviceWorker' in navigator && 'PushManager' in window;
  }

  /**
   * Verificar se as notificações push são suportadas
   */
  checkSupport() {
    return this.isSupported;
  }

  /**
   * Verificar permissão actual
   */
  getPermissionState() {
    if (!this.isSupported) return 'unsupported';
    return Notification.permission;
  }

  /**
   * Registar Service Worker
   */
  async registerServiceWorker() {
    if (!this.isSupported) {
      console.warn('Push notifications não suportadas neste browser');
      return null;
    }

    try {
      const registration = await navigator.serviceWorker.register('/sw-push.js', {
        scope: '/'
      });
      console.log('Service Worker registado:', registration);
      this.swRegistration = registration;
      return registration;
    } catch (error) {
      console.error('Erro ao registar Service Worker:', error);
      return null;
    }
  }

  /**
   * Pedir permissão para notificações
   */
  async requestPermission() {
    if (!this.isSupported) {
      return { success: false, error: 'Não suportado' };
    }

    try {
      const permission = await Notification.requestPermission();
      console.log('Permissão de notificações:', permission);
      return { success: permission === 'granted', permission };
    } catch (error) {
      console.error('Erro ao pedir permissão:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Obter token de autenticação do localStorage
   */
  getAuthToken() {
    return localStorage.getItem('token');
  }

  /**
   * Subscrever para notificações push
   */
  async subscribe() {
    if (!this.swRegistration) {
      await this.registerServiceWorker();
    }

    if (!this.swRegistration) {
      return { success: false, error: 'Service Worker não registado' };
    }

    try {
      // Verificar subscrição existente
      let subscription = await this.swRegistration.pushManager.getSubscription();
      
      if (!subscription) {
        // Criar nova subscrição
        const options = {
          userVisibleOnly: true
        };

        // Adicionar VAPID key se disponível
        if (VAPID_PUBLIC_KEY) {
          options.applicationServerKey = this.urlBase64ToUint8Array(VAPID_PUBLIC_KEY);
        }

        subscription = await this.swRegistration.pushManager.subscribe(options);
        console.log('Nova subscrição criada:', subscription);
      }

      // Enviar subscrição para o backend
      const token = this.getAuthToken();
      if (token && API_URL) {
        try {
          const response = await fetch(`${API_URL}/api/notifications/push/subscribe`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
              endpoint: subscription.endpoint,
              keys: {
                p256dh: subscription.getKey ? btoa(String.fromCharCode.apply(null, new Uint8Array(subscription.getKey('p256dh')))) : null,
                auth: subscription.getKey ? btoa(String.fromCharCode.apply(null, new Uint8Array(subscription.getKey('auth')))) : null
              },
              expirationTime: subscription.expirationTime
            })
          });
          
          if (response.ok) {
            console.log('Subscrição registada no backend');
          } else {
            console.warn('Erro ao registar subscrição no backend:', response.status);
          }
        } catch (backendError) {
          console.warn('Erro ao comunicar com backend:', backendError);
          // Continuar mesmo sem backend - notificações locais funcionam
        }
      }
      
      return { success: true, subscription };
    } catch (error) {
      console.error('Erro ao subscrever:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Cancelar subscrição
   */
  async unsubscribe() {
    if (!this.swRegistration) {
      return { success: true };
    }

    try {
      const subscription = await this.swRegistration.pushManager.getSubscription();
      if (subscription) {
        // Notificar backend antes de cancelar
        const token = this.getAuthToken();
        if (token && API_URL) {
          try {
            await fetch(`${API_URL}/api/notifications/push/unsubscribe`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
              },
              body: JSON.stringify({
                endpoint: subscription.endpoint,
                keys: {
                  p256dh: subscription.getKey ? btoa(String.fromCharCode.apply(null, new Uint8Array(subscription.getKey('p256dh')))) : null,
                  auth: subscription.getKey ? btoa(String.fromCharCode.apply(null, new Uint8Array(subscription.getKey('auth')))) : null
                }
              })
            });
          } catch (backendError) {
            console.warn('Erro ao notificar backend:', backendError);
          }
        }
        
        await subscription.unsubscribe();
        console.log('Subscrição cancelada');
      }
      return { success: true };
    } catch (error) {
      console.error('Erro ao cancelar subscrição:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Mostrar notificação local (sem push server)
   */
  async showLocalNotification(title, options = {}) {
    if (Notification.permission !== 'granted') {
      console.warn('Permissão de notificações não concedida');
      return false;
    }

    const defaultOptions = {
      icon: '/logo192.png',
      badge: '/logo192.png',
      vibrate: [100, 50, 100],
      tag: 'creditoimo-local',
      requireInteraction: false,
      ...options
    };

    try {
      if (this.swRegistration) {
        // Usar service worker para mostrar notificação
        await this.swRegistration.showNotification(title, defaultOptions);
      } else {
        // Fallback para notificação nativa
        new Notification(title, defaultOptions);
      }
      return true;
    } catch (error) {
      console.error('Erro ao mostrar notificação:', error);
      return false;
    }
  }

  /**
   * Converter VAPID key de base64 para Uint8Array
   */
  urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
      .replace(/-/g, '+')
      .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }
}

// Singleton instance
const pushService = new PushNotificationService();

export default pushService;
export { PushNotificationService };
