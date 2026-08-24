/**
 * useWebSocket — Hook WebSocket singleton com exponential backoff, heartbeat e polling fallback.
 *
 * PORQUÊ: O PowerCell precisa de actualizações em tempo real (novos processos, mudanças
 * de estado, notificações, presença de utilizadores). O WebSocket é a forma mais
 * eficiente de obter isso, mas tem fragilidades (desconexões de rede, tokens expirados).
 * Este módulo resolve esses problemas com uma arquitectura singleton + polling fallback.
 *
 * DECISÕES ARQUITECTURAIS:
 * - WebSocketManager (singleton module-level): garante uma única ligação por sessão
 *   independentemente de quantos componentes chamem useWebSocket(). Usa reference
 *   counting para ligar no 1º subscriber e desligar no último.
 * - Exponential backoff na reconexão: começa a 1s, duplica até 30s máximo.
 *   O backoff NÃO é resetado no `onopen` — só após a ligação ficar estável
 *   (evita churn quando o servidor aceita e fecha de imediato com JWT expirado).
 * - Limite de tentativas consecutivas: após MAX_RECONNECT_ATTEMPTS falhas, para
 *   o loop WS e fica em polling até o token mudar.
 * - Heartbeat a cada 30s para manter a ligação activa e detectar desconexões silenciosas.
 * - Polling fallback: quando o WebSocket falha 3 vezes consecutivas, comuta para
 *   polling via REST (/api/alerts/notifications) até a ligação ser restabelecida.
 * - Token expirado (Pacote FP): close 4001/4001, reason, ou JWT `exp` local.
 *   Aborta reconexão com o mesmo token, tenta um refresh silencioso, e espera
 *   que o AuthContext entregue um token novo. Código 4002/4002 / HTTP 403
 *   (token inválido) força logout (sem polling).
 * - Proteção contra React StrictMode double-mount via verificação de estado.
 * - Tipos de eventos tipados (WSEventType) para processos, documentos, notificações,
 *   prazos e presença de utilizadores.
 *
 * @context {AuthContext} — Consome token para autenticar a ligação WebSocket
 *
 * @param {Object} [options={}] — Opções de configuração
 * @param {Function} [options.onProcessUpdate] — Callback para mudanças em processos (todos os tipos)
 * @param {Function} [options.onNotification] — Callback para novas notificações
 * @param {Function} [options.onDeadlineReminder] — Callback para lembretes de prazos
 * @param {Function} [options.onUserOnline] — Callback quando utilizador fica online
 * @param {Function} [options.onUserOffline] — Callback quando utilizador fica offline
 * @param {boolean} [options.autoConnect=true] — Conectar automaticamente ao montar
 *
 * @returns {Object} Estado e funções do WebSocket:
 *   - isConnected, isPolling, connectionError,
 *   - connect, disconnect, sendMessage,
 *   - markNotificationRead, markAllNotificationsRead,
 *   - on, off
 *
 * @example
 * const { isConnected, sendMessage, on } = useWebSocket({
 *   onProcessUpdate: (type, data) => {
 *     console.log('Processo actualizado:', data);
 *   },
 *   onNotification: (notification) => {
 *     toast.info(notification.message);
 *   },
 * });
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  forceSessionExpired,
  isAuthWebSocketClose,
  isExpiredTokenWebSocketClose,
  isJwtExpired,
  isSessionInvalid,
  registerSessionCleanup,
  WS_CLOSE_TOKEN_INVALID,
  WS_CLOSE_TOKEN_INVALID_LEGACY,
} from '../services/sessionExpiry';

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

  // Email / Webmail
  NEW_EMAIL: 'new_email',

  // Chat
  NEW_CHAT_MESSAGE: 'new_chat_message',

  // Portal Messages (client ↔ staff)
  PORTAL_MESSAGE: 'portal_message',

  // Room events
  ROOM_JOINED: 'room_joined',
  ROOM_LEFT: 'room_left',
};

const INITIAL_RECONNECT_INTERVAL = 1000;
const MAX_RECONNECT_INTERVAL = 30000;
const MAX_RECONNECT_ATTEMPTS = 8;
const STABLE_CONNECTION_MS = 3000;
const HEARTBEAT_INTERVAL = 30000;
const POLLING_INTERVAL = 30000;
const MAX_WS_FAILS = 3;
const API_URL = process.env.REACT_APP_BACKEND_URL + '/api';
const ALERTS_NOTIFICATIONS_URL = `${API_URL}/alerts/notifications`;

// ====================================================================
// WEBSOCKET MANAGER (Singleton — module level)
// ====================================================================
class WebSocketManager {
  constructor() {
    this.ws = null;
    this.token = null;
    this.isConnected = false;
    this.connectionError = null;

    // State listeners (React setState wrappers) — connection only, never per-message
    this._stateListeners = new Set();

    // Event handlers registry
    this._eventHandlers = {};

    // Reconnection state
    this._reconnectTimeout = null;
    this._reconnectAttempts = 0;
    this._reconnectInterval = INITIAL_RECONNECT_INTERVAL;
    this._waitingForFreshToken = false;
    this._rejectedToken = null;
    this._stableTimer = null;

    // Heartbeat
    this._heartbeatInterval = null;

    // Polling fallback
    this._pollingInterval = null;
    this._wsFailCount = 0;

    // Reference counting
    this._subscriberCount = 0;
    this._isConnecting = false;

    // Token refresh lock (prevents concurrent refresh attempts)
    this._isRefreshing = false;

    // Auth failure: stop reconnect/polling and force logout
    this._authFailed = false;

    // Active process rooms (for auto-rejoin on reconnect)
    this._joinedRooms = new Set();
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
    } catch {
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
    if (this._pollingInterval || this._authFailed || isSessionInvalid()) return;
    this._pollingInterval = setInterval(async () => {
      if (!this.token || this._authFailed || isSessionInvalid()) return;
      try {
        const response = await fetch(
          `${ALERTS_NOTIFICATIONS_URL}?unread_only=true`,
          { headers: { Authorization: `Bearer ${this.token}` } },
        );
        if (response.status === 401 || response.status === 403) {
          this._handleAuthFailure();
          return;
        }
        if (response.ok) {
          const data = await response.json();
          const notifications = data.notifications || data;
          if (Array.isArray(notifications)) {
            notifications.forEach(n => {
              this._dispatchEvent(WSEventType.NEW_NOTIFICATION, n);
            });
          }
        }
      } catch {
        // Silent fail (network); auth failures are handled above / by fetch guard
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

  _clearReconnectTimer() {
    if (this._reconnectTimeout) {
      clearTimeout(this._reconnectTimeout);
      this._reconnectTimeout = null;
    }
  }

  _clearStableTimer() {
    if (this._stableTimer) {
      clearTimeout(this._stableTimer);
      this._stableTimer = null;
    }
  }

  _markConnectionStable() {
    this._reconnectAttempts = 0;
    this._reconnectInterval = INITIAL_RECONNECT_INTERVAL;
    this._waitingForFreshToken = false;
    this._rejectedToken = null;
  }

  /**
   * Access token expired: do NOT reconnect with the same JWT (that is the
   * production churn loop). Try one silent refresh; otherwise wait for
   * AuthContext to deliver a new token via updateToken().
   */
  _handleExpiredToken() {
    if (this._authFailed || isSessionInvalid()) return;
    this._waitingForFreshToken = true;
    this._rejectedToken = this.token;
    this._clearReconnectTimer();
    console.warn('WebSocket: Token expirado — a abortar reconexão automática com o mesmo JWT');
    this._refreshAndReconnect();
  }

  _scheduleReconnect() {
    if (this._waitingForFreshToken || this._authFailed || isSessionInvalid()) return;
    if (this._subscriberCount <= 0) return;
    if (isJwtExpired(this.token)) {
      this._handleExpiredToken();
      return;
    }
    if (this._reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.warn(`WebSocket: Limite de ${MAX_RECONNECT_ATTEMPTS} reconexões atingido; a usar polling`);
      this.connectionError = 'Reconexão WebSocket suspensa após demasiadas falhas';
      this._startPolling();
      this._notifyStateListeners();
      return;
    }

    this._clearReconnectTimer();
    const delay = this._reconnectInterval;
    this._reconnectAttempts += 1;
    this._reconnectInterval = Math.min(this._reconnectInterval * 2, MAX_RECONNECT_INTERVAL);
    this._reconnectTimeout = setTimeout(() => {
      this._reconnectTimeout = null;
      this.connect(this.token);
    }, delay);
  }

  /**
   * Attempt to refresh the JWT token and reconnect.
   * Returns true if refresh succeeded, false otherwise.
   */
  async _refreshAndReconnect() {
    if (this._isRefreshing) return false;
    this._isRefreshing = true;

    try {
      const currentRefreshToken = localStorage.getItem('refreshToken');
      if (!currentRefreshToken) {
        console.warn('WebSocket: Sem refresh token disponível');
        this._handleAuthFailure();
        return false;
      }

      const response = await fetch(`${API_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: currentRefreshToken })
      });

      if (!response.ok) {
        console.warn('WebSocket: Refresh falhou, sessão pode ter expirado');
        if (response.status === 401 || response.status === 403) {
          this._handleAuthFailure();
        }
        // Keep _waitingForFreshToken: do not reconnect with the expired JWT.
        return false;
      }

      const data = await response.json();

      // Update stored tokens
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('refreshToken', data.refresh_token);
      this.token = data.access_token;

      if (isJwtExpired(this.token)) {
        this._handleAuthFailure();
        return false;
      }

      this._waitingForFreshToken = false;
      this._rejectedToken = null;
      this._reconnectAttempts = 0;
      this._reconnectInterval = INITIAL_RECONNECT_INTERVAL;
      this.connect(this.token);

      return true;
    } catch (error) {
      console.error('WebSocket: Erro ao fazer refresh do token:', error);
      return false;
    } finally {
      this._isRefreshing = false;
    }
  }

  /**
   * Update the stored token (called when AuthContext refreshes).
   * Reconnects even when the socket is down — that is how we resume after
   * aborting reconnect on an expired JWT.
   */
  updateToken(newToken) {
    if (!newToken || newToken === this.token) return;
    if (isJwtExpired(newToken) && this.token && !isJwtExpired(this.token)) return;

    this.token = newToken;
    this._waitingForFreshToken = false;
    this._rejectedToken = null;
    this._reconnectAttempts = 0;
    this._reconnectInterval = INITIAL_RECONNECT_INTERVAL;

    if (this._subscriberCount <= 0 || this._authFailed || isSessionInvalid()) return;

    this._clearReconnectTimer();

    if (this.ws) {
      this.ws.onclose = null;
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close(1000, 'Token atualizado');
      }
      this.ws = null;
      this.isConnected = false;
      this._stopHeartbeat();
    }
    this.connect(newToken);
  }

  /**
   * Processar mensagem recebida
   */
  _handleMessage(event) {
    try {
      const data = JSON.parse(event.data);
      const type = data.type || data.event;
      const payload = data.data !== undefined ? data.data : data;

      // Event subscribers only — do not push frames into React state
      // (heartbeats every 30s would re-render every useWebSocket() consumer).
      this._dispatchEvent(type, payload, data);
    } catch (error) {
      console.error('WebSocket: Erro ao processar mensagem:', error);
    }
  }

  // ====================================================================
  // CONNECT / DISCONNECT
  // ====================================================================
  /**
   * Auth failure (403 / 4001-4002 / 401): stop reconnect + polling and logout.
   */
  _handleAuthFailure() {
    if (this._authFailed) return;
    this._authFailed = true;
    this._stopPolling();
    this.disconnect();
    this._subscriberCount = 0;
    forceSessionExpired();
  }

  disconnectForAuthFailure() {
    this._authFailed = true;
    this._stopPolling();
    this.disconnect();
    this._subscriberCount = 0;
  }

  connect(token) {
    if (!token || this._authFailed || isSessionInvalid()) return;

    if (this._waitingForFreshToken && token === this._rejectedToken) return;

    if (isJwtExpired(token)) {
      this.token = token;
      if (!this._isRefreshing) this._handleExpiredToken();
      return;
    }

    this.token = token;
    this._waitingForFreshToken = false;
    this._rejectedToken = null;
    this._clearReconnectTimer();

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

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this._isConnecting = false;
        this.isConnected = true;
        this.connectionError = null;
        this._wsFailCount = 0;
        this._stopPolling();
        this._startHeartbeat();
        this._rejoinRooms(); // Rejuntar-se a rooms após reconexão
        this._notifyStateListeners();
        this._dispatchEvent(WSEventType.CONNECTION_STATUS, {
          status: 'connected',
          user_id: null,
        });
        // Do NOT reset backoff here: the server may accept() and immediately
        // close an expired JWT. Only reset after the socket stays open.
        this._clearStableTimer();
        this._stableTimer = setTimeout(() => {
          this._stableTimer = null;
          if (this.isConnected) this._markConnectionStable();
        }, STABLE_CONNECTION_MS);
      };

      this.ws.onmessage = (event) => this._handleMessage(event);

      this.ws.onclose = (event) => {
        this._isConnecting = false;
        this.isConnected = false;
        this._stopHeartbeat();
        this._clearStableTimer();
        this._notifyStateListeners();

        const tokenExpired = isExpiredTokenWebSocketClose(event) || isJwtExpired(this.token);
        if (tokenExpired && this._subscriberCount > 0) {
          this._handleExpiredToken();
          return;
        }

        // Invalid token / HTTP 403 handshake: stop reconnect and force logout
        if (
          event.code === WS_CLOSE_TOKEN_INVALID
          || event.code === WS_CLOSE_TOKEN_INVALID_LEGACY
          || isAuthWebSocketClose(event)
        ) {
          console.warn(`WebSocket: Falha de autenticação (code=${event.code}), sem reconexão`);
          this._handleAuthFailure();
          return;
        }

        // Auto-reconnect unless intentional close or session already invalid
        if (event.code !== 1000 && this._subscriberCount > 0 && !this._authFailed && !isSessionInvalid()) {
          this._scheduleReconnect();
        }
      };

      this.ws.onerror = () => {
        this._isConnecting = false;
        this.connectionError = 'Erro na conexão WebSocket';
        this._wsFailCount++;
        if (this._wsFailCount >= MAX_WS_FAILS && !this._authFailed && !isSessionInvalid()) {
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
    this._clearReconnectTimer();
    this._clearStableTimer();
    this._waitingForFreshToken = false;
    this._rejectedToken = null;

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
    if (this._authFailed || isSessionInvalid()) return this._subscriberCount;
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

  // ── Room-based messaging (process chat rooms) ──────────────────────

  /**
   * Juntar-se à room de um processo para receber mensagens do portal em tempo real.
   * Regista a room para auto-rejoin em caso de reconexão.
   */
  joinProcessRoom(processId) {
    if (!processId) return;
    this._joinedRooms.add(processId);
    return this.sendMessage('join_process_room', { process_id: processId });
  }

  /**
   * Sair da room de um processo.
   */
  leaveProcessRoom(processId) {
    if (!processId) return;
    this._joinedRooms.delete(processId);
    return this.sendMessage('leave_process_room', { process_id: processId });
  }

  /**
   * Rejuntar-se a todas as rooms após reconexão.
   */
  _rejoinRooms() {
    if (this._joinedRooms.size === 0) return;
    this._joinedRooms.forEach(processId => {
      this.sendMessage('join_process_room', { process_id: processId });
    });
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
registerSessionCleanup(() => wsManager.disconnectForAuthFailure());

// ====================================================================
// REACT HOOK (lightweight wrapper around singleton)
// ====================================================================
export function useWebSocket(options = {}) {
  const { token } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState(null);

  const optionsRef = useRef(options);
  const tokenRef = useRef(token);

  // ── FIX: update optionsRef synchronously on every render ──
  // Callers pass inline option objects ({ autoConnect: true, onChatMessage: fn })
  // which are new references every render. Putting `options` in a useEffect dep
  // array would fire that effect on every render. Instead, we update the ref
  // synchronously during render (before any event handlers fire) and only use
  // useEffect for the token ref (which changes infrequently).
  optionsRef.current = options;

  // Keep token ref up-to-date
  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  // When token changes (from AuthContext refresh), update the WebSocket manager
  useEffect(() => {
    if (token && token !== wsManager.token) {
      wsManager.updateToken(token);
    }
  }, [token]);

  // Subscribe to singleton connection-state changes only (not per-message)
  useEffect(() => {
    const unsubscribe = wsManager.subscribe(({ isConnected: connected, connectionError: error }) => {
      setIsConnected(connected);
      setConnectionError(error);
    });

    // Initialize with current state
    setIsConnected(wsManager.isConnected);
    setConnectionError(wsManager.connectionError);

    return unsubscribe;
  }, []);

  // Subscribe to option callbacks (onProcessUpdate, etc.)
  // IMPORTANT: We intentionally use [] deps and read from optionsRef.current
  // inside the handler wrappers. This prevents re-subscription on every render
  // (callers pass inline option objects). The handler wrappers always
  // read the latest callback from optionsRef, avoiding stale closures.
  useEffect(() => {
    const unsubs = [];

    // Wrapper that always calls the latest callback from optionsRef
    const makeHandler = (eventType) => (payload) => {
      const handler = optionsRef.current[eventType];
      if (handler) handler(payload);
    };

    unsubs.push(wsManager.on(WSEventType.PROCESS_CREATED, makeHandler('onProcessUpdate')));
    unsubs.push(wsManager.on(WSEventType.PROCESS_UPDATED, makeHandler('onProcessUpdate')));
    unsubs.push(wsManager.on(WSEventType.PROCESS_STATUS_CHANGED, makeHandler('onProcessUpdate')));
    unsubs.push(wsManager.on(WSEventType.PROCESS_ASSIGNED, makeHandler('onProcessUpdate')));
    unsubs.push(wsManager.on(WSEventType.NEW_NOTIFICATION, makeHandler('onNotification')));
    unsubs.push(wsManager.on(WSEventType.DEADLINE_REMINDER, makeHandler('onDeadlineReminder')));
    unsubs.push(wsManager.on(WSEventType.USER_ONLINE, makeHandler('onUserOnline')));
    unsubs.push(wsManager.on(WSEventType.USER_OFFLINE, makeHandler('onUserOffline')));
    unsubs.push(wsManager.on(WSEventType.NEW_CHAT_MESSAGE, makeHandler('onChatMessage')));
    unsubs.push(wsManager.on(WSEventType.PORTAL_MESSAGE, makeHandler('onPortalMessage')));
    unsubs.push(wsManager.on(WSEventType.NEW_EMAIL, makeHandler('onNewEmail')));
    unsubs.push(wsManager.on(WSEventType.ROOM_JOINED, makeHandler('onRoomJoined')));
    unsubs.push(wsManager.on(WSEventType.ROOM_LEFT, makeHandler('onRoomLeft')));

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

  const joinProcessRoom = useCallback((processId) => {
    return wsManager.joinProcessRoom(processId);
  }, []);

  const leaveProcessRoom = useCallback((processId) => {
    return wsManager.leaveProcessRoom(processId);
  }, []);

  return {
    isConnected,
    isPolling: !!wsManager._pollingInterval,
    connectionError,
    connect: (t) => wsManager.connect(t || token),
    disconnect: () => wsManager.removeSubscriber(),
    sendMessage,
    joinProcessRoom,
    leaveProcessRoom,
    markNotificationRead,
    markAllNotificationsRead,
    on,
    off,
  };
}

export default useWebSocket;
