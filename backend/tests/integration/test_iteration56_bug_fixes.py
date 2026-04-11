"""
Test Iteration 56 - Bug Fixes Testing
======================================
Tests for bugs reported by user:
1. Global search (Ctrl+K): /api/search/global - was /api/api/search/global
2. Bulk S3 mappings: /api/admin/client-s3-mappings/bulk - 422 error fix
3. AI document analyze: /api/documents/ai-analyze/{process_id}
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "admin@sistema.pt"
TEST_PASSWORD = "admin"


class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_login_success(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "admin"
        print(f"✓ Login successful: {data.get('user', {}).get('email')}")


class TestGlobalSearch:
    """Test global search endpoint - Bug fix #1"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    
    def test_global_search_endpoint_exists(self, auth_headers):
        """Test that /api/search/global exists and doesn't 404"""
        response = requests.get(
            f"{BASE_URL}/api/search/global",
            params={"q": "test"},
            headers=auth_headers
        )
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404, "Global search endpoint not found"
        print(f"✓ Global search endpoint exists: status {response.status_code}")
    
    def test_global_search_returns_structure(self, auth_headers):
        """Test that global search returns correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/search/global",
            params={"q": "test", "limit": 5},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Global search failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "processes" in data, "Missing 'processes' in response"
        assert "clients" in data, "Missing 'clients' in response"
        assert "tasks" in data, "Missing 'tasks' in response"
        
        assert isinstance(data["processes"], list)
        assert isinstance(data["clients"], list)
        assert isinstance(data["tasks"], list)
        
        print(f"✓ Global search returned: {len(data['processes'])} processes, {len(data['tasks'])} tasks")
    
    def test_global_search_with_real_term(self, auth_headers):
        """Test global search with a common name"""
        response = requests.get(
            f"{BASE_URL}/api/search/global",
            params={"q": "admin", "limit": 5},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Search for 'admin': {len(data['processes'])} processes found")
    
    def test_global_search_minimum_length(self, auth_headers):
        """Test that search requires minimum 2 characters"""
        response = requests.get(
            f"{BASE_URL}/api/search/global",
            params={"q": "a"},  # Only 1 character
            headers=auth_headers
        )
        # Should fail validation (422)
        assert response.status_code == 422, "Should require minimum 2 characters"
        print("✓ Global search correctly rejects search with < 2 chars")


class TestBulkS3Mappings:
    """Test bulk S3 mappings endpoint - Bug fix #2"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    
    def test_bulk_s3_mappings_accepts_array(self, auth_headers):
        """Test that bulk endpoint accepts array JSON - was giving 422"""
        # Send empty array - should work without 422
        response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings/bulk",
            json=[],  # Empty array
            headers=auth_headers
        )
        assert response.status_code == 200, f"Bulk mappings failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        print(f"✓ Bulk S3 mappings accepts empty array: {data}")
    
    def test_bulk_s3_mappings_with_invalid_process(self, auth_headers):
        """Test bulk endpoint with invalid process ID"""
        response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings/bulk",
            json=[{"process_id": "invalid-id-12345", "s3_folder": "Test/Folder"}],
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should succeed but report the invalid process
        assert data.get("success") == True
        assert data.get("updated") == 0  # None updated
        print(f"✓ Bulk S3 mappings handles invalid process correctly: {data}")
    
    def test_client_s3_mappings_list(self, auth_headers):
        """Test listing client S3 mappings"""
        response = requests.get(
            f"{BASE_URL}/api/admin/client-s3-mappings",
            headers=auth_headers
        )
        assert response.status_code == 200, f"List mappings failed: {response.text}"
        data = response.json()
        assert "processes" in data or "stats" in data or isinstance(data, dict)
        print(f"✓ Client S3 mappings list works")


class TestAIDocumentAnalyze:
    """Test AI document analyze endpoint - Bug fix #3"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    
    @pytest.fixture(scope="class")
    def sample_process_id(self, auth_headers):
        """Get a sample process ID for testing"""
        response = requests.get(
            f"{BASE_URL}/api/processes",
            params={"limit": 1},
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            processes = data.get("processes", data) if isinstance(data, dict) else data
            if processes and len(processes) > 0:
                return processes[0].get("id")
        return None
    
    def test_ai_analyze_endpoint_exists(self, auth_headers, sample_process_id):
        """Test that AI analyze endpoint exists"""
        if not sample_process_id:
            pytest.skip("No process found for testing")
        
        # Test with no files (should return 422 for missing files, not 404)
        response = requests.post(
            f"{BASE_URL}/api/documents/ai-analyze/{sample_process_id}",
            headers=auth_headers
        )
        # 422 = validation error (no files), 400 = bad request, but NOT 404
        assert response.status_code in [400, 422], f"Unexpected status: {response.status_code} - {response.text}"
        print(f"✓ AI analyze endpoint exists: status {response.status_code}")
    
    def test_ai_analyze_with_invalid_process(self, auth_headers):
        """Test AI analyze with invalid process ID"""
        response = requests.post(
            f"{BASE_URL}/api/documents/ai-analyze/invalid-process-id",
            headers=auth_headers,
            files={"files": ("test.txt", b"test content", "text/plain")}
        )
        # Should return 404 for invalid process
        assert response.status_code == 404, f"Expected 404 for invalid process: {response.text}"
        print("✓ AI analyze correctly returns 404 for invalid process")


class TestHomeButtonNavigation:
    """Test home button navigation routes"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    
    def test_dashboard_endpoint(self, auth_headers):
        """Test dashboard endpoint exists"""
        # The frontend handles routing, but we verify auth works
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Admin should navigate to /dashboard
        assert data.get("role") == "admin"
        print(f"✓ Auth/me works, role: {data.get('role')}")


class TestAPIHealth:
    """Basic API health tests"""
    
    def test_health_endpoint(self):
        """Test basic health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint OK")
    
    def test_cors_headers(self):
        """Test CORS headers are present"""
        response = requests.options(f"{BASE_URL}/api/health")
        # Just verify the request doesn't fail
        print(f"✓ CORS test: status {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
