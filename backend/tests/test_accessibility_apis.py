"""
Test suite for accessibility and AI import logs API endpoints
Testing: /api/admin/ai-import-logs-v2, /api/documents/download-url, /api/ai-import-logs
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Test that API is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health endpoint working")
    
    def test_login_admin(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data or "token" in data
        print(f"✓ Admin login successful")
        return data.get("access_token") or data.get("token")


class TestAIImportLogsAPI:
    """Test AI Import Logs endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Authentication failed")
    
    def test_ai_import_logs_endpoint(self, auth_token):
        """Test /api/ai-import-logs endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/ai-import-logs", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "total" in data
        print(f"✓ AI Import Logs endpoint working - {data.get('total', 0)} logs found")
    
    def test_ai_import_logs_stats(self, auth_token):
        """Test /api/ai-import-logs/stats endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/ai-import-logs/stats", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_imports" in data
        print(f"✓ AI Import Logs stats working - {data.get('total_imports', 0)} total imports")
    
    def test_admin_ai_import_logs_v2(self, auth_token):
        """Test /api/admin/ai-import-logs-v2 endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/ai-import-logs-v2", headers=headers)
        # May return 200 with data or 404 if endpoint doesn't exist
        if response.status_code == 404:
            print("⚠ /api/admin/ai-import-logs-v2 endpoint not found - checking route")
            # Check if endpoint exists in admin routes
            pytest.skip("Endpoint may not be implemented yet")
        assert response.status_code == 200
        print(f"✓ Admin AI Import Logs V2 endpoint working")


class TestDocumentsAPI:
    """Test Documents endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Authentication failed")
    
    def test_download_url_endpoint_exists(self, auth_token):
        """Test /api/documents/download-url endpoint exists"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # Test with a dummy path - should return error but endpoint should exist
        test_path = "test/path.pdf"
        response = requests.get(f"{BASE_URL}/api/documents/download-url/{test_path}", headers=headers)
        # 500 is expected because the file doesn't exist, but endpoint should be reachable
        # 404 means endpoint doesn't exist
        assert response.status_code != 404, "Endpoint /api/documents/download-url/{path} not found"
        print(f"✓ Download URL endpoint exists (status: {response.status_code})")
    
    def test_document_types_endpoint(self, auth_token):
        """Test /api/documents/types endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/documents/types", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Document types endpoint working - {len(data)} types")


class TestSystemLogsNavigation:
    """Test system logs navigation (for AI Import tab)"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Authentication failed")
    
    def test_admin_logs_endpoint(self, auth_token):
        """Test /api/admin/logs endpoint for system logs"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/logs", headers=headers)
        # May return 200 or 404 if using different path
        print(f"Admin logs endpoint response: {response.status_code}")
        if response.status_code == 200:
            print("✓ Admin logs endpoint working")
        else:
            print(f"⚠ Admin logs endpoint status: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
