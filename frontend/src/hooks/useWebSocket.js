/**
 * ====================================================================
 * HOOK USEWEBSOCKET - CREDITOIMO
 * ====================================================================
 * Hook React para gestão de conexões WebSocket em tempo real.
 * 
 * Funcionalidades:
 * - Conexão automática com autenticação
 * - Reconexão automática em caso de falha
 * - Heartbeat para manter conexão activa
 * - Gestão de eventos de notificação
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

const RECONNECT_INTERVAL = 5000; // 5 segundos
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
  
  const {
    onNotification,
    onProcessUpdate,
    onDeadlineReminder,
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
        
        default:
          console.log('WebSocket: Evento não tratado:', type, payload);
      }
    } catch (error) {
      console.error('WebSocket: Erro ao processar mensagem:', error);
    }
  }, [onNotification, onProcessUpdate, onDeadlineReminder]);

  // Conectar ao WebSocket
  const connect = useCallback(() => {
    if (!token) {
      console.log('WebSocket: Sem token, não conectando');
      return;
    }
    
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('WebSocket: Já conectado');
      return;
    }
    
    try {
      const url = getWebSocketUrl();
      
      // Se não há URL, não conectar
      if (!url) {
        console.log('WebSocket: URL não disponível');
        return;
      }
      
      console.log('WebSocket: Conectando a', url.replace(/token=.*/, 'token=***'));
      
      wsRef.current = new WebSocket(url);
      
      wsRef.current.onopen = () => {
        console.log('WebSocket: Conexão estabelecida');
        setIsConnected(true);
        setConnectionError(null);
        startHeartbeat();
        onConnect?.();
      };
      
      wsRef.current.onmessage = handleMessage;
      
      wsRef.current.onclose = (event) => {
        console.log('WebSocket: Conexão fechada', event.code, event.reason);
        setIsConnected(false);
        clearHeartbeat();
        onDisconnect?.();
        
        // Reconectar automaticamente se não foi fechamento intencional
        if (event.code !== 1000 && event.code !== 4001) {
          console.log(`WebSocket: Reconectando em ${RECONNECT_INTERVAL/1000}s...`);
          reconnectTimeoutRef.current = setTimeout(connect, RECONNECT_INTERVAL);
        }
      };
      
      wsRef.current.onerror = (error) => {
        console.error('WebSocket: Erro:', error);
        setConnectionError('Erro na conexão WebSocket');
      };
      
    } catch (error) {
      console.error('WebSocket: Erro ao criar conexão:', error);
      setConnectionError(error.message);
    }
  }, [token, getWebSocketUrl, handleMessage, startHeartbeat, clearHeartbeat, onConnect, onDisconnect]);

  // Desconectar
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    clearHeartbeat();
    
    if (wsRef.current) {
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
    };
  }, [autoConnect, token, connect, disconnect]);

  return {
    isConnected,
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
