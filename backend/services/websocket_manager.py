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
    """Gestor de ligações WebSocket com suporte a Rooms (processos)."""
    
    def __init__(self):
        # Mapeamento de user_id para conjunto de ligações WebSocket
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Mapeamento de WebSocket para user_id
        self.websocket_to_user: Dict[WebSocket, str] = {}
        # ── Room support ──
        # room_name (e.g. "process_abc123") → conjunto de user_ids na room
        self.rooms: Dict[str, Set[str]] = {}
        # user_id → conjunto de room_names em que o utilizador está
        self.user_rooms: Dict[str, Set[str]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Aceitar uma nova ligação WebSocket."""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        
        self.active_connections[user_id].add(websocket)
        self.websocket_to_user[websocket] = user_id
        
        logger.info(f"WebSocket conectado para utilizador {user_id}. Total conexões: {self.get_total_connections()}")
    
    def disconnect(self, websocket: WebSocket):
        """Remover uma ligação WebSocket e limpar rooms automaticamente."""
        user_id = self.websocket_to_user.get(websocket)
        
        if user_id and user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            
            # Remover o set se estiver vazio
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                
                # ── Auto-cleanup: sair de todas as rooms quando sem conexões ──
                if user_id in self.user_rooms:
                    for room_name in list(self.user_rooms[user_id]):
                        self._leave_room_internal(room_name, user_id)
                    del self.user_rooms[user_id]
        
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
            
            # Remover ligações que falharam
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
        
        # Remover ligações que falharam
        for ws in disconnected:
            self.disconnect(ws)
    
    async def broadcast_to_roles(self, message: dict, roles: list, users_data: dict):
        """Enviar mensagem para utilizadores com papéis específicos."""
        for user_id in self.active_connections.keys():
            user_role = users_data.get(user_id, {}).get("role")
            if user_role in roles:
                await self.send_personal_message(message, user_id)
    
    # ── Room-based messaging ─────────────────────────────────────────────
    
    def join_room(self, room_name: str, user_id: str):
        """Adicionar um utilizador a uma room (e.g. "process_abc123")."""
        if room_name not in self.rooms:
            self.rooms[room_name] = set()
        self.rooms[room_name].add(user_id)
        
        if user_id not in self.user_rooms:
            self.user_rooms[user_id] = set()
        self.user_rooms[user_id].add(room_name)
        
        logger.debug(f"[ROOM] Utilizador {user_id} entrou na room '{room_name}'. "
                      f"Membros: {len(self.rooms[room_name])}")
    
    def leave_room(self, room_name: str, user_id: str):
        """Remover um utilizador de uma room."""
        self._leave_room_internal(room_name, user_id)
        # Limpar user_rooms se ficou vazio
        if user_id in self.user_rooms and not self.user_rooms[user_id]:
            del self.user_rooms[user_id]
    
    def _leave_room_internal(self, room_name: str, user_id: str):
        """Remover utilizador da room (sem limpar user_rooms — usado internamente)."""
        if room_name in self.rooms:
            self.rooms[room_name].discard(user_id)
            # Remover room se ficou vazia
            if not self.rooms[room_name]:
                del self.rooms[room_name]
            else:
                logger.debug(f"[ROOM] Utilizador {user_id} saiu da room '{room_name}'. "
                              f"Membros restantes: {len(self.rooms[room_name])}")
        
        if user_id in self.user_rooms:
            self.user_rooms[user_id].discard(room_name)
    
    async def broadcast_to_room(self, room_name: str, message: dict, exclude_user: Optional[str] = None):
        """Enviar mensagem para todos os utilizadores numa room, opcionalmente excluindo um."""
        if room_name not in self.rooms:
            return
        
        for user_id in self.rooms[room_name]:
            if exclude_user and user_id == exclude_user:
                continue
            await self.send_personal_message(message, user_id)
    
    def get_room_members(self, room_name: str) -> list:
        """Obter lista de user_ids numa room."""
        return list(self.rooms.get(room_name, set()))
    
    def is_in_room(self, room_name: str, user_id: str) -> bool:
        """Verificar se um utilizador está numa room."""
        return user_id in self.rooms.get(room_name, set())
    
    def get_total_connections(self) -> int:
        """Obter número total de ligações activas."""
        return sum(len(conns) for conns in self.active_connections.values())
    
    def get_connected_users(self) -> list:
        """Obter lista de utilizadores conectados."""
        return list(self.active_connections.keys())
    
    def is_user_connected(self, user_id: str) -> bool:
        """Verificar se um utilizador está conectado."""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0


# Instância global do gestor de ligações
manager = ConnectionManager()


# Tipos de eventos WebSocket
class WSEventType:
    """Constantes para tipos de eventos WebSocket no CRM.

    Estas constantes são usadas como valores do campo ``type`` nas mensagens
    WebSocket enviadas pelo servidor. O frontend usa estas constantes para
    identificar que tipo de atualização recebeu e atualizar a UI em conformidade.

    Categorias:
        - Notificações (NEW_NOTIFICATION, NOTIFICATION_READ, ALL_NOTIFICATIONS_READ)
        - Processos (PROCESS_CREATED, PROCESS_UPDATED, PROCESS_STATUS_CHANGED, etc.)
        - Kanban Collaboration (PROCESS_MOVED, PROCESS_LOCKED, PROCESS_UNLOCKED)
        - Documentos (DOCUMENT_EXPIRING, DOCUMENT_UPLOADED)
        - Prazos (DEADLINE_CREATED, DEADLINE_UPDATED, DEADLINE_REMINDER)
        - Sistema (HEARTBEAT, CONNECTION_STATUS, USER_ONLINE, USER_OFFLINE)
    """
    # Notificações
    NEW_NOTIFICATION = "new_notification"
    NOTIFICATION_READ = "notification_read"
    ALL_NOTIFICATIONS_READ = "all_notifications_read"
    
    # Processos
    PROCESS_CREATED = "process_created"
    PROCESS_UPDATED = "process_updated"
    PROCESS_STATUS_CHANGED = "process_status_changed"
    PROCESS_ASSIGNED = "process_assigned"
    
    # Kanban Collaboration
    PROCESS_MOVED = "process_moved"
    PROCESS_LOCKED = "process_locked"
    PROCESS_UNLOCKED = "process_unlocked"
    
    # Documentos
    DOCUMENT_EXPIRING = "document_expiring"
    DOCUMENT_UPLOADED = "document_uploaded"
    
    # Chat / Portal Messages
    PORTAL_MESSAGE = "portal_message"
    NEW_CHAT_MESSAGE = "new_chat_message"
    CHAT_TYPING = "chat_typing"
    
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
    """Cria mensagem WebSocket padronizada para envio ao frontend.

    Todas as mensagens WebSocket enviadas pelo servidor seguem esta estrutura:
    ``{"type": "evento", "data": {...}, "timestamp": "ISO-8601"}``. O timestamp
    UTC permite ao frontend ordenar mensagens e calcular latência.

    Args:
        event_type: Tipo de evento (usar constantes de ``WSEventType``).
        data: Payload do evento (dicionário com dados relevantes).
        timestamp: Timestamp ISO-8601 (default: momento atual em UTC).

    Returns:
        dict: Mensagem formatada com chaves ``type``, ``data`` e ``timestamp``.
    """
    return {
        "type": event_type,
        "data": data,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat()
    }
