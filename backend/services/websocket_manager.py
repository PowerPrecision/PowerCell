"""
====================================================================
WEBSOCKET MANAGER - CREDITOIMO
====================================================================
Gestor de conexões WebSocket para notificações em tempo real.

Funcionalidades:
- Gestão de conexões por utilizador
- Broadcast de notificações
- Reconexão automática
- Heartbeat para manter conexões activas
====================================================================
"""

import json
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gestor de conexões WebSocket."""
    
    def __init__(self):
        # Mapeamento de user_id para conjunto de conexões WebSocket
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Mapeamento de WebSocket para user_id
        self.websocket_to_user: Dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Aceitar uma nova conexão WebSocket."""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        
        self.active_connections[user_id].add(websocket)
        self.websocket_to_user[websocket] = user_id
        
        logger.info(f"WebSocket conectado para utilizador {user_id}. Total conexões: {self.get_total_connections()}")
    
    def disconnect(self, websocket: WebSocket):
        """Remover uma conexão WebSocket."""
        user_id = self.websocket_to_user.get(websocket)
        
        if user_id and user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            
            # Remover o set se estiver vazio
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        if websocket in self.websocket_to_user:
            del self.websocket_to_user[websocket]
        
        logger.info(f"WebSocket desconectado para utilizador {user_id}. Total conexões: {self.get_total_connections()}")
    
    async def send_personal_message(self, message: dict, user_id: str):
        """Enviar mensagem para um utilizador específico."""
        if user_id in self.active_connections:
            disconnected = set()
            
            for websocket in self.active_connections[user_id]:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Erro ao enviar mensagem para {user_id}: {e}")
                    disconnected.add(websocket)
            
            # Remover conexões que falharam
            for ws in disconnected:
                self.disconnect(ws)
    
    async def broadcast(self, message: dict, exclude_user: Optional[str] = None):
        """Enviar mensagem para todos os utilizadores conectados."""
        disconnected = []
        
        for user_id, connections in self.active_connections.items():
            if exclude_user and user_id == exclude_user:
                continue
            
            for websocket in connections:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Erro no broadcast para {user_id}: {e}")
                    disconnected.append(websocket)
        
        # Remover conexões que falharam
        for ws in disconnected:
            self.disconnect(ws)
    
    async def broadcast_to_roles(self, message: dict, roles: list, users_data: dict):
        """Enviar mensagem para utilizadores com papéis específicos."""
        for user_id in self.active_connections.keys():
            user_role = users_data.get(user_id, {}).get("role")
            if user_role in roles:
                await self.send_personal_message(message, user_id)
    
    def get_total_connections(self) -> int:
        """Obter número total de conexões activas."""
        return sum(len(conns) for conns in self.active_connections.values())
    
    def get_connected_users(self) -> list:
        """Obter lista de utilizadores conectados."""
        return list(self.active_connections.keys())
    
    def is_user_connected(self, user_id: str) -> bool:
        """Verificar se um utilizador está conectado."""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0


# Instância global do gestor de conexões
manager = ConnectionManager()


# Tipos de eventos WebSocket
class WSEventType:
    # Notificações
    NEW_NOTIFICATION = "new_notification"
    NOTIFICATION_READ = "notification_read"
    ALL_NOTIFICATIONS_READ = "all_notifications_read"
    
    # Processos
    PROCESS_CREATED = "process_created"
    PROCESS_UPDATED = "process_updated"
    PROCESS_STATUS_CHANGED = "process_status_changed"
    PROCESS_ASSIGNED = "process_assigned"
    
    # Documentos
    DOCUMENT_EXPIRING = "document_expiring"
    DOCUMENT_UPLOADED = "document_uploaded"
    
    # Eventos/Prazos
    DEADLINE_CREATED = "deadline_created"
    DEADLINE_UPDATED = "deadline_updated"
    DEADLINE_REMINDER = "deadline_reminder"
    
    # Sistema
    HEARTBEAT = "heartbeat"
    CONNECTION_STATUS = "connection_status"
    USER_ONLINE = "user_online"
    USER_OFFLINE = "user_offline"


def create_ws_message(event_type: str, data: dict, timestamp: Optional[str] = None) -> dict:
    """Criar mensagem WebSocket padronizada."""
    return {
        "type": event_type,
        "data": data,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat()
    }
