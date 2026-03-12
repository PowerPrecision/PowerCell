"""
====================================================================
TEST ITERATION 8 - PUSH NOTIFICATIONS & WEBSOCKET
====================================================================
Tests for:
1. Push Notification endpoints (subscribe, unsubscribe, status)
2. WebSocket status endpoint
3. Login and authentication
====================================================================
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin2026"


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_check(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health check passed")
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"
        print("✓ Admin login passed")


@pytest.fixture
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed")


@pytest.fixture
def auth_headers(auth_token):
    """Get headers with authentication"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestPushNotificationEndpoints:
    """Tests for Push Notification API endpoints"""
    
    def test_get_push_status_initial(self, auth_headers):
        """Test GET /api/notifications/push/status - initial status"""
        response = requests.get(
            f"{BASE_URL}/api/notifications/push/status",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "is_subscribed" in data
        assert "subscription_count" in data
        assert "subscriptions" in data
        assert isinstance(data["is_subscribed"], bool)
        assert isinstance(data["subscription_count"], int)
        assert isinstance(data["subscriptions"], list)
        print(f"✓ Push status: is_subscribed={data['is_subscribed']}, count={data['subscription_count']}")
    
    def test_push_subscribe(self, auth_headers):
        """Test POST /api/notifications/push/subscribe"""
        test_subscription = {
            "endpoint": "https://test-push-endpoint.example.com/test-iteration8",
            "keys": {
                "p256dh": "test-p256dh-key-iteration8",
                "auth": "test-auth-key-iteration8"
            },
            "expirationTime": None
        }
        
        response = requests.post(
            f"{BASE_URL}/api/notifications/push/subscribe",
            headers=auth_headers,
            json=test_subscription
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "message" in data
        print(f"✓ Push subscribe: {data['message']}")
    
    def test_push_status_after_subscribe(self, auth_headers):
        """Test GET /api/notifications/push/status - after subscription"""
        # First subscribe
        test_subscription = {
            "endpoint": "https://test-push-endpoint.example.com/test-iteration8-verify",
            "keys": {
                "p256dh": "test-p256dh-key-verify",
                "auth": "test-auth-key-verify"
            },
            "expirationTime": None
        }
        
        requests.post(
            f"{BASE_URL}/api/notifications/push/subscribe",
            headers=auth_headers,
            json=test_subscription
        )
        
        # Check status
        response = requests.get(
            f"{BASE_URL}/api/notifications/push/status",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["is_subscribed"] == True
        assert data["subscription_count"] >= 1
        print(f"✓ Push status after subscribe: count={data['subscription_count']}")
    
    def test_push_unsubscribe(self, auth_headers):
        """Test POST /api/notifications/push/unsubscribe"""
        test_subscription = {
            "endpoint": "https://test-push-endpoint.example.com/test-iteration8-verify",
            "keys": {
                "p256dh": "test-p256dh-key-verify",
                "auth": "test-auth-key-verify"
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/notifications/push/unsubscribe",
            headers=auth_headers,
            json=test_subscription
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "message" in data
        print(f"✓ Push unsubscribe: {data['message']}")
    
    def test_push_subscribe_update_existing(self, auth_headers):
        """Test updating existing subscription"""
        test_subscription = {
            "endpoint": "https://test-push-endpoint.example.com/test-iteration8",
            "keys": {
                "p256dh": "updated-p256dh-key",
                "auth": "updated-auth-key"
            },
            "expirationTime": None
        }
        
        response = requests.post(
            f"{BASE_URL}/api/notifications/push/subscribe",
            headers=auth_headers,
            json=test_subscription
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        # Should update existing subscription
        assert "atualizada" in data["message"].lower() or "criada" in data["message"].lower()
        print(f"✓ Push subscribe update: {data['message']}")
    
    def test_push_status_requires_auth(self):
        """Test that push status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/notifications/push/status")
        assert response.status_code in [401, 403]
        print("✓ Push status requires authentication")
    
    def test_push_subscribe_requires_auth(self):
        """Test that push subscribe requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/notifications/push/subscribe",
            json={"endpoint": "test", "keys": {}}
        )
        assert response.status_code in [401, 403]
        print("✓ Push subscribe requires authentication")


class TestWebSocketStatus:
    """Tests for WebSocket status endpoint"""
    
    def test_ws_status_endpoint(self):
        """Test GET /api/ws/status - public endpoint"""
        response = requests.get(f"{BASE_URL}/api/ws/status")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "total_connections" in data
        assert "connected_users" in data
        assert "user_ids" in data
        assert isinstance(data["total_connections"], int)
        assert isinstance(data["connected_users"], int)
        assert isinstance(data["user_ids"], list)
        print(f"✓ WebSocket status: connections={data['total_connections']}, users={data['connected_users']}")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_subscriptions(self, auth_headers):
        """Clean up test subscriptions"""
        # Unsubscribe test endpoints
        test_endpoints = [
            "https://test-push-endpoint.example.com/test-iteration8",
            "https://test-push-endpoint.example.com/test-iteration8-verify"
        ]
        
        for endpoint in test_endpoints:
            requests.post(
                f"{BASE_URL}/api/notifications/push/unsubscribe",
                headers=auth_headers,
                json={
                    "endpoint": endpoint,
                    "keys": {"p256dh": "test", "auth": "test"}
                }
            )
        
        print("✓ Test subscriptions cleaned up")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
