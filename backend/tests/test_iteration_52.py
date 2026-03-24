"""
====================================================================
TESTS FOR ITERATION 52 - Session Features
====================================================================
Testing:
1. Email test-connection endpoint
2. Templates available endpoint  
3. Template validation endpoint
4. Worker lazy loading verification (code review)
====================================================================
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://undo-toast-ui.preview.emergentagent.com')


class TestAuthentication:
    """Test authentication endpoints"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geral@powerealestate.pt", "password": "admin"}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def consultant_token(self):
        """Get consultant authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "flaviosilva@powerealestate.pt", "password": "flavio123"}
        )
        assert response.status_code == 200, f"Consultant login failed: {response.text}"
        return response.json()["access_token"]


class TestEmailEndpoints(TestAuthentication):
    """Test email endpoints - Feature 3"""
    
    def test_email_test_connection_endpoint_exists(self, admin_token):
        """Test /api/emails/test-connection endpoint returns valid response"""
        response = requests.get(
            f"{BASE_URL}/api/emails/test-connection",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Endpoint should exist and return 200
        assert response.status_code == 200, f"Email test-connection failed: {response.text}"
        
        data = response.json()
        # Should contain account results (power and/or precision)
        # Since we have env vars set, we should get results
        assert isinstance(data, dict), "Response should be a dict with account results"
        
        # Check if we have any account results
        print(f"Email accounts configured: {list(data.keys())}")
        
        # If accounts are configured, check structure
        for account_name, result in data.items():
            if account_name != "error":
                assert "imap" in result or "smtp" in result, f"Account {account_name} should have imap/smtp status"
    
    def test_email_accounts_endpoint(self, admin_token):
        """Test /api/emails/accounts endpoint returns configured accounts"""
        response = requests.get(
            f"{BASE_URL}/api/emails/accounts",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200, f"Email accounts failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list of accounts"
        
        # Check account structure
        for account in data:
            assert "name" in account, "Account should have name"
            assert "email" in account, "Account should have email"
        
        print(f"Configured email accounts: {[a['name'] for a in data]}")


class TestTemplatesEndpoints(TestAuthentication):
    """Test templates endpoints - Features 4, 5"""
    
    def test_templates_available_endpoint(self, admin_token):
        """Test GET /api/templates/available - Feature 4"""
        response = requests.get(
            f"{BASE_URL}/api/templates/available",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200, f"Templates available failed: {response.text}"
        
        data = response.json()
        assert "templates" in data, "Response should contain 'templates' key"
        
        templates = data["templates"]
        assert isinstance(templates, list), "Templates should be a list"
        
        # Should have some templates
        assert len(templates) > 0, "Should have at least one template"
        
        print(f"Available templates: {[t.get('id') or t.get('type') or t for t in templates]}")
        
        # Check template structure
        for template in templates:
            assert "id" in template or "type" in template, "Template should have id or type"
    
    def test_templates_validate_endpoint_with_invalid_process(self, admin_token):
        """Test GET /api/templates/process/{id}/validate/{tipo} with invalid process - Feature 5"""
        # Use non-existent process ID
        fake_process_id = "non-existent-process-12345"
        template_type = "cpcv"
        
        response = requests.get(
            f"{BASE_URL}/api/templates/process/{fake_process_id}/validate/{template_type}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Should return 404 for non-existent process
        assert response.status_code == 404, f"Should return 404 for invalid process: {response.text}"


class TestBackgroundJobsPage(TestAuthentication):
    """Test Background Jobs Page - Feature 1 (Bug Fix)"""
    
    def test_background_jobs_endpoint(self, admin_token):
        """Test /api/ai/bulk/background-jobs endpoint returns valid response"""
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200, f"Background jobs endpoint failed: {response.text}"
        
        data = response.json()
        assert "jobs" in data, "Response should contain 'jobs' key"
        assert "counts" in data, "Response should contain 'counts' key"
        
        # Verify counts structure
        counts = data["counts"]
        assert "total" in counts, "Counts should have 'total'"


class TestProcessData(TestAuthentication):
    """Test with real process data if available"""
    
    def test_get_processes_for_templates(self, admin_token):
        """Get process IDs for template testing"""
        response = requests.get(
            f"{BASE_URL}/api/processes?limit=1",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if response.status_code == 200:
            data = response.json()
            # Handle both list and dict responses
            processes = data if isinstance(data, list) else data.get("processes", data.get("items", []))
            if processes:
                process_id = processes[0].get("id")
                print(f"Found process for testing: {process_id}")
                return process_id
        
        print("No processes found for template testing")
        return None
    
    def test_template_validate_with_real_process(self, admin_token):
        """Test template validation with real process"""
        # First get a real process
        response = requests.get(
            f"{BASE_URL}/api/processes?limit=1",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if response.status_code == 200:
            data = response.json()
            # Handle both list and dict responses
            processes = data if isinstance(data, list) else data.get("processes", data.get("items", []))
            if processes:
                process_id = processes[0].get("id")
                
                # Test validation endpoint
                val_response = requests.get(
                    f"{BASE_URL}/api/templates/process/{process_id}/validate/cpcv",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                assert val_response.status_code == 200, f"Template validation failed: {val_response.text}"
                
                val_data = val_response.json()
                assert "is_valid" in val_data, "Response should have 'is_valid'"
                assert "can_generate" in val_data, "Response should have 'can_generate'"
                
                print(f"Template validation result: is_valid={val_data['is_valid']}, missing_fields={val_data.get('missing_required_fields', [])}")
            else:
                pytest.skip("No processes available for testing")
        else:
            pytest.skip("No processes available for testing")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
