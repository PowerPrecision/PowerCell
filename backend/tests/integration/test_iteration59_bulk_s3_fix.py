"""
Test Iteration 59: Bulk S3 Mappings Fix & Document Expiry Alerts

Testing:
1. POST /api/admin/client-s3-mappings/bulk - deve funcionar com array de mapeamentos
2. POST /api/admin/client-s3-mappings/bulk - deve funcionar com array vazio
3. POST /api/admin/client-s3-mappings/bulk - deve funcionar sem body
4. GET /api/documents/expiry/upcoming - alertas de documentos a expirar
5. GET /api/admin/jobs/health - continua funcionando
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestBulkS3MappingsFix:
    """Test cases for the 422 error fix on bulk S3 mappings endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@sistema.pt", "password": "admin"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_bulk_s3_mappings_with_empty_array(self, auth_headers):
        """Test bulk S3 mappings with empty array - should NOT return 422"""
        response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings/bulk",
            headers=auth_headers,
            json=[]
        )
        
        # Should NOT be 422 - should be 200
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("updated") == 0
        print(f"✓ Bulk S3 mappings with empty array: {data}")
    
    def test_bulk_s3_mappings_without_body(self, auth_headers):
        """Test bulk S3 mappings without any body - should NOT return 422"""
        # Send request without body but with Content-Type
        response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings/bulk",
            headers=auth_headers
        )
        
        # Should NOT be 422 - should be 200
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        print(f"✓ Bulk S3 mappings without body: {data}")
    
    def test_bulk_s3_mappings_with_valid_data(self, auth_headers):
        """Test bulk S3 mappings with valid data array"""
        # First get a valid process ID
        processes_response = requests.get(
            f"{BASE_URL}/api/processes?limit=1",
            headers=auth_headers
        )
        
        if processes_response.status_code == 200:
            data = processes_response.json()
            # Handle both list and dict response formats
            processes = data if isinstance(data, list) else data.get("processes", [])
            if processes:
                process_id = processes[0].get("id")
                
                # Now test bulk update
                response = requests.post(
                    f"{BASE_URL}/api/admin/client-s3-mappings/bulk",
                    headers=auth_headers,
                    json=[
                        {"process_id": process_id, "s3_folder": None}
                    ]
                )
                
                assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
                
                data = response.json()
                assert data.get("success") == True
                print(f"✓ Bulk S3 mappings with valid data: updated={data.get('updated')}")
            else:
                pytest.skip("No processes available for testing")
        else:
            pytest.skip("Could not fetch processes for testing")
    
    def test_bulk_s3_mappings_with_invalid_process_id(self, auth_headers):
        """Test bulk S3 mappings with invalid process_id"""
        response = requests.post(
            f"{BASE_URL}/api/admin/client-s3-mappings/bulk",
            headers=auth_headers,
            json=[
                {"process_id": "invalid-process-id-xyz", "s3_folder": "test-folder"}
            ]
        )
        
        # Should still be 200, but with error in results
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("total") == 1
        
        # Check that the invalid process is reported as error
        results = data.get("results", [])
        if results:
            assert results[0].get("success") == False
            print(f"✓ Bulk S3 mappings with invalid process: error correctly reported")


class TestDocumentExpiryAlerts:
    """Test cases for document expiry alerts endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@sistema.pt", "password": "admin"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_upcoming_expiries_endpoint(self, auth_headers):
        """Test GET /api/documents/expiry/upcoming endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/documents/expiry/upcoming",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should return a list (possibly empty if no expiring docs)
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✓ Document expiry upcoming: {len(data)} documents")
    
    def test_upcoming_expiries_with_custom_days(self, auth_headers):
        """Test upcoming expiries with custom days parameter"""
        response = requests.get(
            f"{BASE_URL}/api/documents/expiry/upcoming?days=90",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✓ Document expiry upcoming (90 days): {len(data)} documents")
    
    def test_expiry_calendar_endpoint(self, auth_headers):
        """Test GET /api/documents/expiry/calendar endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/documents/expiry/calendar",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should return calendar events
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✓ Document expiry calendar: {len(data)} events")


class TestJobsHealthEndpoint:
    """Test that jobs health endpoint still works"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Login and get admin token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@sistema.pt", "password": "admin"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_jobs_health_endpoint(self, auth_headers):
        """Test GET /api/admin/jobs/health endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/admin/jobs/health",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should have expected fields
        assert "healthy" in data or "timestamp" in data, f"Missing expected fields in response"
        print(f"✓ Jobs health endpoint: healthy={data.get('healthy', 'N/A')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
