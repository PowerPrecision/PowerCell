/**
 * ====================================================================
 * HOOK USEWEBSOCKET - CREDITOIMO
 * ====================================================================
 * Hook React para gestão de conexões WebSocket em tempo real.
 * 
 * Funcionalidades:
 * - Conexão automática com autenticação
 * - Reconexão automática com exponential backoff
 * - Heartbeat para manter conexão activa
 * - Gestão de eventos de notificação
 * - Proteção contra conexões paralelas (React StrictMode, re-renders)
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

const INITIAL_RECONNECT_INTERVAL = 1000; // 1 segundo (início)
const MAX_RECONNECT_INTERVAL = 30000; // 30 segundos (teto)
const HEARTBEAT_INTERVAL = 30000; // 30 segundos

export function useWebSocket(options = {}) {
  const { token } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const [connectionError, setConnectionError] = useState(null);
  
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const heartbeatIntervalRef = useRef(null);
  const eventHandlersRef = useRef({});
  const reconnectAttemptsRef = useRef(0);
  const reconnectIntervalRef = useRef(INITIAL_RECONNECT_INTERVAL);
  const isConnectingRef = useRef(false); // Previne conexões paralelas
  
  const {
    onNotification,
    onProcessUpdate,
    onDeadlineReminder,
    onUserOnline,
    onUserOffline,
    onConnect,
    onDisconnect,
    autoConnect = true,
  } = options;

  // Obter URL do WebSocket
  const getWebSocketUrl = useCallback(() => {
    const backendUrl = process.env.REACT_APP_BACKEND_URL;
    
    // Se não há URL configurada, não conectar
    if (!backendUrl) {
      console.warn('WebSocket: REACT_APP_BACKEND_URL não configurada');
      return null;
    }
    
    // Construir URL WebSocket corretamente
    // REACT_APP_BACKEND_URL pode ser:
    // - https://domain.com (produção/preview)
    // - http://localhost:8001 (desenvolvimento local)
    
    try {
      const url = new URL(backendUrl);
      
      // Determinar protocolo WebSocket baseado no protocolo HTTP
      const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      
      // Construir URL WebSocket mantendo host e porta originais
      const wsUrl = `${wsProtocol}//${url.host}/api/ws/notifications?token=${token}`;
      
      return wsUrl;
    } catch (e) {
      // Fallback para o método antigo se URL() falhar
      console.warn('WebSocket: Erro ao parsear URL, usando fallback');
      const wsProtocol = backendUrl.startsWith('https') ? 'wss' : 'ws';
      const wsUrl = backendUrl.replace(/^https?:\/\//, `${wsProtocol}://`);
      return `${wsUrl}/api/ws/notifications?token=${token}`;
    }
  }, [token]);

  // Limpar heartbeat
  const clearHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
  }, []);

  // Iniciar heartbeat
  const startHeartbeat = useCallback(() => {
    clearHeartbeat();
    heartbeatIntervalRef.current = setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, HEARTBEAT_INTERVAL);
  }, [clearHeartbeat]);

  // Processar mensagem recebida
  const handleMessage = useCallback((event) => {
    try {
      const data = JSON.parse(event.data);
      setLastMessage(data);
      
      const { type, data: payload } = data;
      
      // Chamar handler registado para este tipo de evento
      if (eventHandlersRef.current[type]) {
        eventHandlersRef.current[type].forEach(handler => handler(payload, data));
      }
      
      // Handlers específicos passados nas options
      switch (type) {
        case WSEventType.NEW_NOTIFICATION:
          onNotification?.(payload);
          break;
        
        case WSEventType.PROCESS_CREATED:
        case WSEventType.PROCESS_UPDATED:
        case WSEventType.PROCESS_STATUS_CHANGED:
        case WSEventType.PROCESS_ASSIGNED:
          onProcessUpdate?.(type, payload);
          break;
        
        case WSEventType.DEADLINE_REMINDER:
          onDeadlineReminder?.(payload);
          break;
        
        case WSEventType.CONNECTION_STATUS:
          if (payload.status === 'connected') {
            console.log('WebSocket: Conectado com sucesso', payload);
          }
          break;
        
        case WSEventType.HEARTBEAT:
          // Pong recebido, conexão está activa
          break;
        
        case WSEventType.USER_ONLINE:
          onUserOnline?.(payload);
          break;
        
        case WSEventType.USER_OFFLINE:
          onUserOffline?.(payload);
          break;
        
        default:
          // Eventos não esperados são silenciados para reduzir ruído no console
          break;
      }
    } catch (error) {
      console.error('WebSocket: Erro ao processar mensagem:', error);
    }
  }, [onNotification, onProcessUpdate, onDeadlineReminder, onUserOnline, onUserOffline]);

  // O11 - Polling fallback quando WebSocket falha
  const pollingIntervalRef = useRef(null);
  const wsFailCountRef = useRef(0);
  const MAX_WS_FAILS = 3;
  const POLLING_INTERVAL = 30000; // 30 seconds
  
  const startPollingFallback = useCallback(() => {
    if (pollingIntervalRef.current) return; // Already polling
    
    console.log('WebSocket: Iniciando polling fallback (30s)');
    pollingIntervalRef.current = setInterval(async () => {
      if (!token) return;
      try {
        const apiUrl = process.env.REACT_APP_BACKEND_URL;
        const response = await fetch(`${apiUrl}/api/notifications?unread=true&limit=10`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          const notifications = data.notifications || data;
          if (Array.isArray(notifications)) {
            notifications.forEach(n => {
              onNotification?.(n);
            });
          }
        }
      } catch (e) {
        // Silent fail - polling is best-effort
      }
    }, POLLING_INTERVAL);
  }, [token, onNotification]);
  
  const stopPollingFallback = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
      wsFailCountRef.current = 0;
      console.log('WebSocket: Polling fallback parado');
    }
  }, []);

  // Conectar ao WebSocket
  const connect = useCallback(() => {
    if (!token) {
      console.log('WebSocket: Sem token, não conectando');
      return;
    }
    
    // Prevenir conexões paralelas (React StrictMode, re-renders, etc.)
    if (isConnectingRef.current) {
      console.log('WebSocket: Conexão já em curso, ignorando');
      return;
    }
    
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('WebSocket: Já conectado');
      return;
    }
    
    // Fechar conexão anterior se existir (CLOSED/CLOSING/CONNECTING)
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      if (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close(1000, 'Nova conexão');
      }
      wsRef.current = null;
    }
    
    try {
      const url = getWebSocketUrl();
      
      // Se não há URL, não conectar
      if (!url) {
        isConnectingRef.current = false;
        console.log('WebSocket: URL não disponível');
        return;
      }
      
      console.log('WebSocket: Conectando a', url.replace(/token=.*/, 'token=***'));
      
      isConnectingRef.current = true;
      wsRef.current = new WebSocket(url);
      
      wsRef.current.onopen = () => {
        console.log('WebSocket: Conexão estabelecida');
        isConnectingRef.current = false;
        reconnectAttemptsRef.current = 0; // Reset tentativas
        reconnectIntervalRef.current = INITIAL_RECONNECT_INTERVAL; // Reset backoff
        setIsConnected(true);
        setConnectionError(null);
        wsFailCountRef.current = 0;
        stopPollingFallback(); // O11 - Parar polling quando WS conecta
        startHeartbeat();
        onConnect?.();
      };
      
      wsRef.current.onmessage = handleMessage;
      
      wsRef.current.onclose = (event) => {
        console.log('WebSocket: Conexão fechada', event.code, event.reason);
        isConnectingRef.current = false;
        setIsConnected(false);
        clearHeartbeat();
        onDisconnect?.();
        
        // Reconectar automaticamente se não foi fechamento intencional
        if (event.code !== 1000 && event.code !== 4001) {
          // Exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s (teto)
          const delay = reconnectIntervalRef.current;
          reconnectAttemptsRef.current++;
          reconnectIntervalRef.current = Math.min(
            reconnectIntervalRef.current * 2,
            MAX_RECONNECT_INTERVAL
          );
          console.log(`WebSocket: Reconectando em ${delay/1000}s... (tentativa ${reconnectAttemptsRef.current})`);
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        }
      };
      
      wsRef.current.onerror = (error) => {
        console.error('WebSocket: Erro:', error);
        isConnectingRef.current = false;
        setConnectionError('Erro na conexão WebSocket');
        // O11 - Contar falhas e ativar polling fallback
        wsFailCountRef.current++;
        if (wsFailCountRef.current >= MAX_WS_FAILS) {
          startPollingFallback();
        }
      };
      
    } catch (error) {
      isConnectingRef.current = false;
      console.error('WebSocket: Erro ao criar conexão:', error);
      setConnectionError(error.message);
    }
  }, [token, getWebSocketUrl, handleMessage, startHeartbeat, clearHeartbeat, stopPollingFallback, startPollingFallback, onConnect, onDisconnect]);

  // Desconectar
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    isConnectingRef.current = false;
    reconnectAttemptsRef.current = 0;
    reconnectIntervalRef.current = INITIAL_RECONNECT_INTERVAL;
    clearHeartbeat();
    
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close(1000, 'Desconexão intencional');
      wsRef.current = null;
    }
    
    setIsConnected(false);
  }, [clearHeartbeat]);

  // Enviar mensagem
  const sendMessage = useCallback((type, data = {}) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...data }));
      return true;
    }
    console.warn('WebSocket: Não conectado, mensagem não enviada');
    return false;
  }, []);

  // Marcar notificação como lida via WebSocket
  const markNotificationRead = useCallback((notificationId) => {
    return sendMessage('mark_notification_read', { notification_id: notificationId });
  }, [sendMessage]);

  // Marcar todas as notificações como lidas
  const markAllNotificationsRead = useCallback(() => {
    return sendMessage('mark_all_read');
  }, [sendMessage]);

  // Registar handler de evento
  const on = useCallback((eventType, handler) => {
    if (!eventHandlersRef.current[eventType]) {
      eventHandlersRef.current[eventType] = [];
    }
    eventHandlersRef.current[eventType].push(handler);
    
    // Retornar função para remover handler
    return () => {
      eventHandlersRef.current[eventType] = eventHandlersRef.current[eventType].filter(
        h => h !== handler
      );
    };
  }, []);

  // Remover handler de evento
  const off = useCallback((eventType, handler) => {
    if (eventHandlersRef.current[eventType]) {
      eventHandlersRef.current[eventType] = eventHandlersRef.current[eventType].filter(
        h => h !== handler
      );
    }
  }, []);

  // Conectar automaticamente quando há token
  useEffect(() => {
    if (autoConnect && token) {
      connect();
    }
    
    return () => {
      disconnect();
      stopPollingFallback(); // O11 - Limpar polling ao desmontar
    };
  }, [autoConnect, token, connect, disconnect, stopPollingFallback]);

  return {
    isConnected,
    isPolling: !!pollingIntervalRef.current,
    lastMessage,
    connectionError,
    connect,
    disconnect,
    sendMessage,
    markNotificationRead,
    markAllNotificationsRead,
    on,
    off,
  };
}

export default useWebSocket;
