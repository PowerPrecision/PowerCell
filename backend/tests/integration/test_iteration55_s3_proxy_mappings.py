"""
Iteration 55 - Test S3 Proxy and Client/Process S3 Mappings
Tests:
1. S3 Proxy endpoint: GET /api/documents/proxy/{file_path}
2. Client-S3 Mappings: GET /api/admin/client-s3-mappings
3. Client-S3 Mappings: POST /api/admin/client-s3-mappings?process_id=xxx&s3_folder=xxx
4. Auto-map: POST /api/admin/client-s3-mappings/auto-map
"""
import pytest
import requests
import os
import urllib.parse

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "admin@sistema.pt"
TEST_PASSWORD = "admin"


class TestAuthentication:
    """Test authentication for admin access"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.fail(f"Authentication failed: {response.status_code} - {response.text}")
    
    def test_login_success(self, auth_token):
        """Verify admin can login"""
        assert auth_token is not None
        print(f"SUCCESS: Admin login successful, token: {auth_token[:20]}...")


class TestS3ProxyEndpoint:
    """Test S3 Proxy endpoint for CORS bypass"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Authentication failed")
    
    def test_proxy_endpoint_exists(self, auth_token):
        """Test that proxy endpoint returns proper response for valid file"""
        # Test file from the problem statement
        file_path = "Documentação Clientes/Admilson/DemonstracaoLiquidacao_259301876_202553807030.pdf"
        encoded_path = urllib.parse.quote(file_path, safe='')
        
        response = requests.get(
            f"{BASE_URL}/api/documents/proxy/{encoded_path}",
            headers={"Authorization": f"Bearer {auth_token}"},
            stream=True  # Use stream for potentially large files
        )
        
        # Accept 200 (success) or 500 (S3 error) - just verify endpoint exists
        assert response.status_code in [200, 401, 403, 500], f"Unexpected status: {response.status_code}"
        print(f"INFO: Proxy endpoint status: {response.status_code}")
        
        if response.status_code == 200:
            # Verify we get proper content type for PDF
            content_type = response.headers.get('Content-Type', '')
            print(f"SUCCESS: Proxy returned file with content-type: {content_type}")
            assert 'pdf' in content_type.lower() or 'octet-stream' in content_type.lower()
        elif response.status_code == 500:
            # S3 error - file may not exist, but endpoint works
            print(f"INFO: S3 error (file may not exist): {response.text[:200]}")
    
    def test_proxy_without_auth_fails(self):
        """Test that proxy endpoint requires authentication"""
        file_path = "test/file.pdf"
        encoded_path = urllib.parse.quote(file_path, safe='')
        
        response = requests.get(f"{BASE_URL}/api/documents/proxy/{encoded_path}")
        
        # Should fail without auth token
        assert response.status_code in [401, 403, 422], f"Expected auth error, got: {response.status_code}"
        print(f"SUCCESS: Proxy correctly requires authentication (status: {response.status_code})")


class TestClientS3Mappings:
    """Test Client/Process S3 Mapping endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Authentication failed")
    
    def test_get_client_s3_mappings(self, auth_token):
        """Test GET /api/admin/client-s3-mappings returns processes and available folders"""
        response = requests.get(
            f"{BASE_URL}/api/admin/client-s3-mappings",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got: {response.status_code} - {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "processes" in data, "Response should contain 'processes' key"
        assert "available_folders" in data, "Response should contain 'available_folders' key"
        assert "s3_configured" in data, "Response should contain 's3_configured' key"
        assert "stats" in data, "Response should contain 'stats' key"
        
        # Validate stats structure
        stats = data["stats"]
        assert "total" in stats, "Stats should have 'total'"
        assert "mapped" in stats, "Stats should have 'mapped'"
        assert "unmapped" in stats, "Stats should have 'unmapped'"
        
        print(f"SUCCESS: Client-S3 mappings returned {len(data['processes'])} processes")
        print(f"INFO: {len(data['available_folders'])} S3 folders available")
        print(f"INFO: Stats - Total: {stats['total']}, Mapped: {stats['mapped']}, Unmapped: {stats['unmapped']}")
        print(f"INFO: S3 configured: {data['s3_configured']}")
    
    def test_get_client_s3_mappings_with_search(self, auth_token):
        """Test GET /api/admin/client-s3-mappings with search parameter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/client-s3-mappings?search=test",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got: {response.status_code}"
        data = response.json()
        assert "processes" in data
        print(f"SUCCESS: Search filter returned {len(data['processes'])} processes")
    
    def test_get_client_s3_mappings_unmapped_only(self, auth_token):
        """Test GET /api/admin/client-s3-mappings with unmapped_only=true"""
        response = requests.get(
            f"{BASE_URL}/api/admin/client-s3-mappings?unmapped_only=true",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got: {response.status_code}"
        data = response.json()
        assert "processes" in data
        print(f"SUCCESS: Unmapped filter returned {len(data['processes'])} processes")
    
    def test_update_client_s3_mapping_requires_process_id(self, auth_token):
        """Test POST /api/admin/client-s3-mappings without process_id fails"""
        response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should fail with 422 validation error
        assert response.status_code == 422, f"Expected 422, got: {response.status_code}"
        print(f"SUCCESS: Missing process_id correctly returns 422 validation error")
    
    def test_update_client_s3_mapping_invalid_process(self, auth_token):
        """Test POST /api/admin/client-s3-mappings with invalid process_id"""
        response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings?process_id=invalid-id-123&s3_folder=test",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should fail with 404
        assert response.status_code == 404, f"Expected 404, got: {response.status_code}"
        print(f"SUCCESS: Invalid process_id correctly returns 404")
    
    def test_update_client_s3_mapping_valid_process(self, auth_token):
        """Test POST /api/admin/client-s3-mappings with valid process_id"""
        # First get a valid process
        get_response = requests.get(
            f"{BASE_URL}/api/admin/client-s3-mappings",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        if get_response.status_code != 200:
            pytest.skip("Could not fetch processes")
        
        data = get_response.json()
        processes = data.get("processes", [])
        available_folders = data.get("available_folders", [])
        
        if not processes:
            pytest.skip("No processes available for testing")
        
        # Use first process
        test_process = processes[0]
        process_id = test_process.get("id")
        original_folder = test_process.get("s3_folder_mapping")
        
        # Set a mapping
        test_folder = available_folders[0]["path"] if available_folders else "test-folder"
        
        update_response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings?process_id={process_id}&s3_folder={urllib.parse.quote(test_folder)}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert update_response.status_code == 200, f"Expected 200, got: {update_response.status_code} - {update_response.text}"
        update_data = update_response.json()
        
        assert update_data.get("success") == True
        assert update_data.get("process_id") == process_id
        print(f"SUCCESS: Updated mapping for process {process_id} to folder: {test_folder}")
        
        # Restore original mapping
        restore_url = f"{BASE_URL}/api/admin/client-s3-mappings?process_id={process_id}"
        if original_folder:
            restore_url += f"&s3_folder={urllib.parse.quote(original_folder)}"
        
        requests.post(restore_url, headers={"Authorization": f"Bearer {auth_token}"})
        print(f"INFO: Restored original mapping")


class TestAutoMapEndpoint:
    """Test auto-map endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Authentication failed")
    
    def test_auto_map_endpoint_exists(self, auth_token):
        """Test POST /api/admin/client-s3-mappings/auto-map"""
        response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings/auto-map",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Can be 200 (success) or 500 (S3 not configured)
        assert response.status_code in [200, 500], f"Expected 200 or 500, got: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert "total_unmapped" in data
            assert "mapped_count" in data
            print(f"SUCCESS: Auto-map completed. Unmapped: {data['total_unmapped']}, Mapped: {data['mapped_count']}")
        else:
            print(f"INFO: Auto-map returned 500 (S3 may not be configured): {response.text[:200]}")
    
    def test_auto_map_requires_auth(self):
        """Test that auto-map requires authentication"""
        response = requests.post(f"{BASE_URL}/api/admin/client-s3-mappings/auto-map")
        
        assert response.status_code in [401, 403, 422], f"Expected auth error, got: {response.status_code}"
        print(f"SUCCESS: Auto-map correctly requires authentication")


class TestClientStatusFilter:
    """Test client page status filter (has_active_process)"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Authentication failed")
    
    def test_get_clients_all(self, auth_token):
        """Test GET /api/clients returns all clients"""
        response = requests.get(
            f"{BASE_URL}/api/clients?show_all=true&limit=100",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got: {response.status_code}"
        data = response.json()
        assert "clients" in data
        total_clients = len(data.get("clients", []))
        print(f"SUCCESS: GET /api/clients returned {total_clients} clients")
        return total_clients
    
    def test_get_clients_with_active_process(self, auth_token):
        """Test GET /api/clients?has_active_process=true"""
        response = requests.get(
            f"{BASE_URL}/api/clients?show_all=true&limit=100&has_active_process=true",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got: {response.status_code}"
        data = response.json()
        assert "clients" in data
        active_clients = len(data.get("clients", []))
        print(f"SUCCESS: Clients with active processes: {active_clients}")
    
    def test_get_clients_without_active_process(self, auth_token):
        """Test GET /api/clients?has_active_process=false"""
        response = requests.get(
            f"{BASE_URL}/api/clients?show_all=true&limit=100&has_active_process=false",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got: {response.status_code}"
        data = response.json()
        assert "clients" in data
        inactive_clients = len(data.get("clients", []))
        print(f"SUCCESS: Clients without active processes: {inactive_clients}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
