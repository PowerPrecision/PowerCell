/**
 * ====================================================================
 * WEBSOCKET SINGLETON MANAGER + HOOK - CREDITOIMO
 * ====================================================================
 * 
 * ARQUITECTURA:
 * - WebSocketManager: Singleton module-level que gere uma única conexão
 * - useWebSocket(): Hook React que se subscreve ao singleton
 * 
 * VANTAGENS:
 * - Uma única conexão WebSocket por sessão (não importa quantos
 *   componentes chamem useWebSocket())
 * - Reference counting: conecta no 1º subscriber, desconecta no último
 * - Exponential backoff na reconexão
 * - Heartbeat para manter conexão activa
 * - Proteção contra React StrictMode double-mount
 * ====================================================================
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';

// Tipos de eventos WebSocket
export const WSEventType = {
  // Notificações
  NEW_NOTIFICATION: 'new_notification',
  NOTIFICATION_READ: 'notification_read',
  ALL_NOTIFICATIONS_READ: 'all_notifications_read',
  
  // Processos
  PROCESS_CREATED: 'process_created',
  PROCESS_UPDATED: 'process_updated',
  PROCESS_STATUS_CHANGED: 'process_status_changed',
  PROCESS_ASSIGNED: 'process_assigned',
  PROCESS_MOVED: 'process_moved',
  PROCESS_LOCKED: 'process_locked',
  PROCESS_UNLOCKED: 'process_unlocked',
  
  // Documentos
  DOCUMENT_EXPIRING: 'document_expiring',
  DOCUMENT_UPLOADED: 'document_uploaded',
  
  // Eventos/Prazos
  DEADLINE_CREATED: 'deadline_created',
  DEADLINE_UPDATED: 'deadline_updated',
  DEADLINE_REMINDER: 'deadline_reminder',
  
  // Sistema
  HEARTBEAT: 'heartbeat',
  CONNECTION_STATUS: 'connection_status',
  USER_ONLINE: 'user_online',
  USER_OFFLINE: 'user_offline',
};

const INITIAL_RECONNECT_INTERVAL = 1000;
const MAX_RECONNECT_INTERVAL = 30000;
const HEARTBEAT_INTERVAL = 30000;
const POLLING_INTERVAL = 30000;
const MAX_WS_FAILS = 3;

// ====================================================================
// WEBSOCKET MANAGER (Singleton — module level)
// ====================================================================
class WebSocketManager {
  constructor() {
    this.ws = null;
    this.token = null;
    this.isConnected = false;
    this.connectionError = null;
    this.lastMessage = null;

    // State listeners (React setState wrappers)
    this._stateListeners = new Set();

    // Event handlers registry
    this._eventHandlers = {};

    // Reconnection state
    this._reconnectTimeout = null;
    this._reconnectAttempts = 0;
    this._reconnectInterval = INITIAL_RECONNECT_INTERVAL;

    // Heartbeat
    this._heartbeatInterval = null;

    // Polling fallback
    this._pollingInterval = null;
    this._wsFailCount = 0;

    // Reference counting
    this._subscriberCount = 0;
    this._isConnecting = false;
  }

  /**
   * Obter URL do WebSocket
   */
  _getUrl() {
    const backendUrl = process.env.REACT_APP_BACKEND_URL;
    if (!backendUrl) return null;

    try {
      const url = new URL(backendUrl);
      const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${wsProtocol}//${url.host}/api/ws/notifications?token=${this.token}`;
    } catch (e) {
      const wsProtocol = backendUrl.startsWith('https') ? 'wss' : 'ws';
      const wsUrl = backendUrl.replace(/^https?:\/\//, `${wsProtocol}://`);
      return `${wsUrl}/api/ws/notifications?token=${this.token}`;
    }
  }

  /**
   * Notificar todos os listeners de mudança de estado
   */
  _notifyStateListeners() {
    this._stateListeners.forEach(listener => listener({
      isConnected: this.isConnected,
      connectionError: this.connectionError,
      lastMessage: this.lastMessage,
    }));
  }

  // ====================================================================
  // HEARTBEAT
  // ====================================================================
  _startHeartbeat() {
    this._stopHeartbeat();
    this._heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, HEARTBEAT_INTERVAL);
  }

  _stopHeartbeat() {
    if (this._heartbeatInterval) {
      clearInterval(this._heartbeatInterval);
      this._heartbeatInterval = null;
    }
  }

  // ====================================================================
  // POLLING FALLBACK
  // ====================================================================
  _startPolling() {
    if (this._pollingInterval) return;
    this._pollingInterval = setInterval(async () => {
      if (!this.token) return;
      try {
        const apiUrl = process.env.REACT_APP_BACKEND_URL;
        const response = await fetch(`${apiUrl}/api/notifications?unread=true&limit=10`, {
          headers: { Authorization: `Bearer ${this.token}` }
        });
        if (response.ok) {
          const data = await response.json();
          const notifications = data.notifications || data;
          if (Array.isArray(notifications)) {
            notifications.forEach(n => {
              this._dispatchEvent(WSEventType.NEW_NOTIFICATION, n);
            });
          }
        }
      } catch (e) {
        // Silent fail
      }
    }, POLLING_INTERVAL);
  }

  _stopPolling() {
    if (this._pollingInterval) {
      clearInterval(this._pollingInterval);
      this._pollingInterval = null;
      this._wsFailCount = 0;
    }
  }

  // ====================================================================
  // EVENT DISPATCHING
  // ====================================================================
  _dispatchEvent(type, payload, rawData) {
    // Notify registered handlers
    const handlers = this._eventHandlers[type];
    if (handlers) {
      handlers.forEach(handler => handler(payload, rawData));
    }
  }

  /**
   * Processar mensagem recebida
   */
  _handleMessage(event) {
    try {
      const data = JSON.parse(event.data);
      this.lastMessage = data;
      const { type, data: payload } = data;

      // Dispatch to all registered handlers
      this._dispatchEvent(type, payload, data);

      // Notify state listeners (for lastMessage update)
      this._notifyStateListeners();

      // System-level logging (minimal)
      switch (type) {
        case WSEventType.CONNECTION_STATUS:
          if (payload.status === 'connected') {
            console.log('WebSocket: Conectado com sucesso', payload);
          }
          break;
        case WSEventType.HEARTBEAT:
          break;
        default:
          break;
      }
    } catch (error) {
      console.error('WebSocket: Erro ao processar mensagem:', error);
    }
  }

  // ====================================================================
  // CONNECT / DISCONNECT
  // ====================================================================
  connect(token) {
    if (!token) return;

    this.token = token;

    // Already connected or connecting
    if (this._isConnecting) return;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

    // Clean up stale connection
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      if (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN) {
        this.ws.close(1000, 'Nova conexão');
      }
      this.ws = null;
    }

    const url = this._getUrl();
    if (!url) return;

    this._isConnecting = true;
    console.log('WebSocket: Conectando a', url.replace(/token=.*/, 'token=***'));

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log('WebSocket: Conexão estabelecida');
        this._isConnecting = false;
        this._reconnectAttempts = 0;
        this._reconnectInterval = INITIAL_RECONNECT_INTERVAL;
        this.isConnected = true;
        this.connectionError = null;
        this._wsFailCount = 0;
        this._stopPolling();
        this._startHeartbeat();
        this._notifyStateListeners();
        this._dispatchEvent(WSEventType.CONNECTION_STATUS, {
          status: 'connected',
          user_id: null,
        });
      };

      this.ws.onmessage = (event) => this._handleMessage(event);

      this.ws.onclose = (event) => {
        console.log('WebSocket: Conexão fechada', event.code, event.reason);
        this._isConnecting = false;
        this.isConnected = false;
        this._stopHeartbeat();
        this._notifyStateListeners();

        // Auto-reconnect unless intentional close
        if (event.code !== 1000 && event.code !== 4001 && this._subscriberCount > 0) {
          const delay = this._reconnectInterval;
          this._reconnectAttempts++;
          this._reconnectInterval = Math.min(this._reconnectInterval * 2, MAX_RECONNECT_INTERVAL);
          console.log(`WebSocket: Reconectando em ${delay / 1000}s... (tentativa ${this._reconnectAttempts})`);
          this._reconnectTimeout = setTimeout(() => this.connect(this.token), delay);
        }
      };

      this.ws.onerror = () => {
        this._isConnecting = false;
        this.connectionError = 'Erro na conexão WebSocket';
        this._wsFailCount++;
        if (this._wsFailCount >= MAX_WS_FAILS) {
          this._startPolling();
        }
        this._notifyStateListeners();
      };

    } catch (error) {
      this._isConnecting = false;
      this.connectionError = error.message;
      this._notifyStateListeners();
    }
  }

  disconnect() {
    if (this._reconnectTimeout) {
      clearTimeout(this._reconnectTimeout);
      this._reconnectTimeout = null;
    }

    this._isConnecting = false;
    this._reconnectAttempts = 0;
    this._reconnectInterval = INITIAL_RECONNECT_INTERVAL;
    this._stopHeartbeat();

    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close(1000, 'Desconexão intencional');
      this.ws = null;
    }

    this.isConnected = false;
    this.token = null;
  }

  /**
   * Increment subscriber count and connect if first subscriber
   */
  addSubscriber(token) {
    this._subscriberCount++;
    if (this._subscriberCount === 1 && !this.isConnected) {
      this.connect(token);
    }
    return this._subscriberCount;
  }

  /**
   * Decrement subscriber count and disconnect if last subscriber
   */
  removeSubscriber() {
    this._subscriberCount = Math.max(0, this._subscriberCount - 1);
    if (this._subscriberCount === 0) {
      this.disconnect();
      this._stopPolling();
    }
    return this._subscriberCount;
  }

  // ====================================================================
  // PUBLIC API (called by hook instances)
  // ====================================================================

  sendMessage(type, data = {}) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, ...data }));
      return true;
    }
    return false;
  }

  /**
   * Registar handler de evento
   */
  on(eventType, handler) {
    if (!this._eventHandlers[eventType]) {
      this._eventHandlers[eventType] = [];
    }
    this._eventHandlers[eventType].push(handler);
    return () => {
      if (this._eventHandlers[eventType]) {
        this._eventHandlers[eventType] = this._eventHandlers[eventType].filter(h => h !== handler);
      }
    };
  }

  off(eventType, handler) {
    if (this._eventHandlers[eventType]) {
      this._eventHandlers[eventType] = this._eventHandlers[eventType].filter(h => h !== handler);
    }
  }

  /**
   * Subscribe to connection state changes
   */
  subscribe(listener) {
    this._stateListeners.add(listener);
    return () => this._stateListeners.delete(listener);
  }
}

// Module-level singleton
const wsManager = new WebSocketManager();

// ====================================================================
// REACT HOOK (lightweight wrapper around singleton)
// ====================================================================
export function useWebSocket(options = {}) {
  const { token } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const [connectionError, setConnectionError] = useState(null);

  const optionsRef = useRef(options);
  const tokenRef = useRef(token);

  // Keep options ref up-to-date without triggering re-subscriptions
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  // Keep token ref up-to-date
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  // Subscribe to singleton state changes
  useEffect(() => {
    const unsubscribe = wsManager.subscribe(({ isConnected: connected, connectionError: error, lastMessage: msg }) => {
      setIsConnected(connected);
      setConnectionError(error);
      setLastMessage(msg);
    });

    // Initialize with current state
    setIsConnected(wsManager.isConnected);
    setConnectionError(wsManager.connectionError);
    setLastMessage(wsManager.lastMessage);

    return unsubscribe;
  }, []);

  // Subscribe to option callbacks (onProcessUpdate, etc.)
  useEffect(() => {
    const unsubs = [];
    const opts = optionsRef.current;

    if (opts.onProcessUpdate) {
      unsubs.push(wsManager.on(WSEventType.PROCESS_CREATED, (p) => opts.onProcessUpdate(WSEventType.PROCESS_CREATED, p)));
      unsubs.push(wsManager.on(WSEventType.PROCESS_UPDATED, (p) => opts.onProcessUpdate(WSEventType.PROCESS_UPDATED, p)));
      unsubs.push(wsManager.on(WSEventType.PROCESS_STATUS_CHANGED, (p) => opts.onProcessUpdate(WSEventType.PROCESS_STATUS_CHANGED, p)));
      unsubs.push(wsManager.on(WSEventType.PROCESS_ASSIGNED, (p) => opts.onProcessUpdate(WSEventType.PROCESS_ASSIGNED, p)));
    }

    if (opts.onNotification) {
      unsubs.push(wsManager.on(WSEventType.NEW_NOTIFICATION, opts.onNotification));
    }

    if (opts.onDeadlineReminder) {
      unsubs.push(wsManager.on(WSEventType.DEADLINE_REMINDER, opts.onDeadlineReminder));
    }

    if (opts.onUserOnline) {
      unsubs.push(wsManager.on(WSEventType.USER_ONLINE, opts.onUserOnline));
    }

    if (opts.onUserOffline) {
      unsubs.push(wsManager.on(WSEventType.USER_OFFLINE, opts.onUserOffline));
    }

    return () => unsubs.forEach(unsub => unsub?.());
  }, []);

  // Subscriber lifecycle: connect on mount, disconnect on last unmount
  useEffect(() => {
    if (optionsRef.current.autoConnect !== false && token) {
      wsManager.addSubscriber(token);
    }

    return () => {
      wsManager.removeSubscriber();
    };
  }, [token]);

  const sendMessage = useCallback((type, data = {}) => {
    return wsManager.sendMessage(type, data);
  }, []);

  const markNotificationRead = useCallback((notificationId) => {
    return wsManager.sendMessage('mark_notification_read', { notification_id: notificationId });
  }, []);

  const markAllNotificationsRead = useCallback(() => {
    return wsManager.sendMessage('mark_all_read');
  }, []);

  const on = useCallback((eventType, handler) => {
    return wsManager.on(eventType, handler);
  }, []);

  const off = useCallback((eventType, handler) => {
    return wsManager.off(eventType, handler);
  }, []);

  return {
    isConnected,
    isPolling: !!wsManager._pollingInterval,
    lastMessage,
    connectionError,
    connect: (t) => wsManager.connect(t || token),
    disconnect: () => wsManager.removeSubscriber(),
    sendMessage,
    markNotificationRead,
    markAllNotificationsRead,
    on,
    off,
  };
}

export default useWebSocket;
