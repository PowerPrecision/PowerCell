"""
====================================================================
TESTES DE WEBSOCKET - CREDITOIMO
====================================================================
Testes para conexões WebSocket e notificações em tempo real.
====================================================================
"""

import pytest
import asyncio
from httpx import AsyncClient
from fastapi.testclient import TestClient
import os

# Import app
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001')

# Credenciais de teste - usar variáveis de ambiente
TEST_ADMIN_EMAIL = os.environ.get('TEST_ADMIN_EMAIL', 'admin@sistema.pt')
TEST_ADMIN_PASSWORD = os.environ.get('TEST_ADMIN_PASSWORD', 'admin2026')


class TestWebSocketStatus:
    """Testes para o endpoint de status WebSocket."""
    
    @pytest.fixture
    def auth_token(self):
        """Get admin auth token."""
        import requests
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Authentication failed")
    
    def test_websocket_status_endpoint(self, auth_token):
        """Test WebSocket status endpoint."""
        import requests
        response = requests.get(
            f"{BASE_URL}/api/ws/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # O endpoint deve estar acessível
        assert response.status_code == 200
        data = response.json()
        
        # Verificar estrutura da resposta
        assert "total_connections" in data
        assert "connected_users" in data
        assert "user_ids" in data
        
        # Verificar tipos
        assert isinstance(data["total_connections"], int)
        assert isinstance(data["connected_users"], int)
        assert isinstance(data["user_ids"], list)
        
        print(f"WebSocket Status: {data['total_connections']} conexões, {data['connected_users']} utilizadores")


class TestWebSocketManager:
    """Testes para o gestor de conexões WebSocket."""
    
    def test_manager_initialization(self):
        """Test WebSocket manager initialization."""
        from services.websocket_manager import ConnectionManager
        
        manager = ConnectionManager()
        
        assert manager.active_connections == {}
        assert manager.websocket_to_user == {}
        assert manager.get_total_connections() == 0
        assert manager.get_connected_users() == []
    
    def test_is_user_connected_false(self):
        """Test is_user_connected returns False for non-connected user."""
        from services.websocket_manager import ConnectionManager
        
        manager = ConnectionManager()
        
        assert manager.is_user_connected("non_existent_user") == False


class TestWSEventTypes:
    """Testes para tipos de eventos WebSocket."""
    
    def test_event_types_defined(self):
        """Test all event types are defined."""
        from services.websocket_manager import WSEventType
        
        # Notificações
        assert WSEventType.NEW_NOTIFICATION == "new_notification"
        assert WSEventType.NOTIFICATION_READ == "notification_read"
        assert WSEventType.ALL_NOTIFICATIONS_READ == "all_notifications_read"
        
        # Processos
        assert WSEventType.PROCESS_CREATED == "process_created"
        assert WSEventType.PROCESS_UPDATED == "process_updated"
        assert WSEventType.PROCESS_STATUS_CHANGED == "process_status_changed"
        assert WSEventType.PROCESS_ASSIGNED == "process_assigned"
        
        # Sistema
        assert WSEventType.HEARTBEAT == "heartbeat"
        assert WSEventType.CONNECTION_STATUS == "connection_status"
    
    def test_create_ws_message(self):
        """Test WebSocket message creation."""
        from services.websocket_manager import create_ws_message
        
        message = create_ws_message("test_event", {"key": "value"})
        
        assert message["type"] == "test_event"
        assert message["data"] == {"key": "value"}
        assert "timestamp" in message
        
        # Verificar formato ISO do timestamp
        from datetime import datetime
        timestamp = message["timestamp"]
        assert "T" in timestamp  # ISO format


class TestRealtimeNotifications:
    """Testes para serviço de notificações em tempo real."""
    
    @pytest.mark.asyncio
    async def test_notification_structure(self):
        """Test notification data structure."""
        # Verificar que o serviço pode ser importado
        from services.realtime_notifications import send_realtime_notification
        
        # A função deve existir e ser callable
        assert callable(send_realtime_notification)
    
    @pytest.mark.asyncio
    async def test_broadcast_function_exists(self):
        """Test broadcast function exists."""
        from services.realtime_notifications import broadcast_notification
        
        assert callable(broadcast_notification)
    
    @pytest.mark.asyncio
    async def test_notify_process_update_exists(self):
        """Test notify_process_update function exists."""
        from services.realtime_notifications import notify_process_update
        
        assert callable(notify_process_update)


# Testes de integração (requerem servidor a correr)
class TestWebSocketIntegration:
    """Testes de integração WebSocket."""
    
    @pytest.fixture
    def auth_token(self):
        """Get admin auth token."""
        import requests
        try:
            response = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD
            }, timeout=5)
            if response.status_code == 200:
                return response.json()["access_token"]
        except:
            pass
        pytest.skip("Server not available or authentication failed")
    
    def test_websocket_url_format(self, auth_token):
        """Test WebSocket URL is properly formatted."""
        ws_url = f"{BASE_URL.replace('http', 'ws')}/api/ws/notifications?token={auth_token}"
        
        # URL deve começar com ws:// ou wss://
        assert ws_url.startswith("ws://") or ws_url.startswith("wss://")
        
        # URL deve conter o endpoint correcto
        assert "/api/ws/notifications" in ws_url
        
        # URL deve conter o token
        assert "token=" in ws_url
        
        print(f"WebSocket URL: {ws_url[:50]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
