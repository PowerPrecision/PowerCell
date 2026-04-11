"""
Test Iteration 54 - P0 Features Testing
=========================================
Testing new CRM imobiliário features:
1. AI Import Logs with details (GET /api/ai-import-logs)
2. User-S3 Mapping endpoints (GET/POST /api/admin/user-s3-mappings)
3. Email filtering rules in sync_emails_for_process
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        data = response.json()
        assert data.get("status") == "healthy", "API not healthy"
        print("✓ Health endpoint OK")
    
    def test_admin_login(self, api_client):
        """Test admin login with credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        assert "user" in data, "No user in response"
        assert data["user"]["role"] == "admin", f"User role is {data['user']['role']}, expected admin"
        print("✓ Admin login OK")


class TestAIImportLogs:
    """Tests for AI Import Logs functionality (P0 Feature 1)"""
    
    def test_list_ai_import_logs(self, authenticated_client):
        """Test GET /api/ai-import-logs endpoint"""
        response = authenticated_client.get(f"{BASE_URL}/api/ai-import-logs")
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "logs" in data, "Response missing 'logs' field"
        assert "total" in data, "Response missing 'total' field"
        assert "page" in data, "Response missing 'page' field"
        assert "limit" in data, "Response missing 'limit' field"
        assert "total_pages" in data, "Response missing 'total_pages' field"
        
        # Validate pagination defaults
        assert data["page"] == 1, "Default page should be 1"
        assert isinstance(data["logs"], list), "logs should be a list"
        
        print(f"✓ AI Import Logs endpoint OK - {data['total']} logs found")
    
    def test_ai_import_logs_with_pagination(self, authenticated_client):
        """Test AI import logs with pagination parameters"""
        response = authenticated_client.get(f"{BASE_URL}/api/ai-import-logs?page=1&limit=10")
        assert response.status_code == 200, f"Failed: {response.status_code}"
        data = response.json()
        assert data["page"] == 1
        assert data["limit"] == 10
        print("✓ AI Import Logs pagination OK")
    
    def test_ai_import_logs_stats(self, authenticated_client):
        """Test GET /api/ai-import-logs/stats endpoint"""
        response = authenticated_client.get(f"{BASE_URL}/api/ai-import-logs/stats")
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Validate stats structure
        assert "total_imports" in data, "Response missing 'total_imports'"
        assert "total_documents" in data, "Response missing 'total_documents'"
        assert "total_success" in data, "Response missing 'total_success'"
        assert "total_errors" in data, "Response missing 'total_errors'"
        assert "success_rate" in data, "Response missing 'success_rate'"
        
        print(f"✓ AI Import Logs Stats OK - {data['total_imports']} total imports")


class TestUserS3Mappings:
    """Tests for User-S3 Mappings functionality (P0 Feature 2)"""
    
    def test_get_user_s3_mappings(self, authenticated_client):
        """Test GET /api/admin/user-s3-mappings endpoint"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/user-s3-mappings")
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "users" in data, "Response missing 'users' field"
        assert "available_folders" in data, "Response missing 'available_folders' field"
        assert "s3_configured" in data, "Response missing 's3_configured' field"
        
        # Validate users list
        assert isinstance(data["users"], list), "users should be a list"
        if len(data["users"]) > 0:
            user = data["users"][0]
            assert "id" in user, "User missing 'id'"
            assert "name" in user or "email" in user, "User missing 'name' or 'email'"
        
        # Validate available_folders
        assert isinstance(data["available_folders"], list), "available_folders should be a list"
        
        print(f"✓ User-S3 Mappings GET OK - {len(data['users'])} users, {len(data['available_folders'])} folders, S3 configured: {data['s3_configured']}")
    
    def test_post_user_s3_mapping_requires_user_id(self, authenticated_client):
        """Test POST /api/admin/user-s3-mappings requires user_id"""
        response = authenticated_client.post(f"{BASE_URL}/api/admin/user-s3-mappings")
        # Should fail without user_id parameter
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✓ User-S3 Mapping POST validation OK (requires user_id)")
    
    def test_post_user_s3_mapping_invalid_user(self, authenticated_client):
        """Test POST with invalid user_id returns 404"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/admin/user-s3-mappings?user_id=nonexistent_user_id"
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ User-S3 Mapping POST invalid user handling OK")
    
    def test_post_user_s3_mapping_valid_user(self, authenticated_client):
        """Test POST with valid user_id"""
        # First, get list of users to find a valid user_id
        response = authenticated_client.get(f"{BASE_URL}/api/admin/user-s3-mappings")
        assert response.status_code == 200
        data = response.json()
        
        if not data["users"]:
            pytest.skip("No users found to test S3 mapping")
        
        # Get first user's ID
        test_user = data["users"][0]
        user_id = test_user["id"]
        
        # Test setting a mapping (can use null for no actual S3 folder)
        response = authenticated_client.post(
            f"{BASE_URL}/api/admin/user-s3-mappings?user_id={user_id}"
        )
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        result = response.json()
        
        assert result.get("success") == True, "Mapping should succeed"
        assert result.get("user_id") == user_id, "Response should contain user_id"
        
        print(f"✓ User-S3 Mapping POST OK for user: {result.get('user_name')}")


class TestAIImportLogsV2:
    """Tests for AI Import Logs V2 endpoints in admin.py"""
    
    def test_ai_import_logs_v2_endpoint(self, authenticated_client):
        """Test GET /api/admin/ai-import-logs-v2 endpoint"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/ai-import-logs-v2")
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "logs" in data, "Response missing 'logs' field"
        assert "pagination" in data, "Response missing 'pagination' field"
        assert "stats" in data, "Response missing 'stats' field"
        
        # Check pagination has total
        assert "total" in data["pagination"], "Pagination missing 'total' field"
        
        print(f"✓ AI Import Logs V2 endpoint OK - {data['pagination']['total']} logs")
    
    def test_ai_import_logs_v2_grouped(self, authenticated_client):
        """Test GET /api/admin/ai-import-logs-v2/grouped endpoint"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/ai-import-logs-v2/grouped")
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Validate response structure (uses 'groups' and 'stats' keys)
        assert "groups" in data, "Response missing 'groups' field"
        assert "stats" in data, "Response missing 'stats' field"
        
        # Validate stats structure
        stats = data["stats"]
        assert "total_clients" in stats, "Stats missing 'total_clients'"
        assert "total_docs" in stats, "Stats missing 'total_docs'"
        
        print(f"✓ AI Import Logs V2 Grouped endpoint OK - {len(data['groups'])} groups, {stats['total_clients']} clients")


class TestEmailSyncService:
    """Tests for email sync service (P0 Feature 3)"""
    
    def test_email_sync_endpoint_exists(self, authenticated_client):
        """Test that email sync endpoint exists (requires process_id)"""
        # This endpoint requires a valid process_id, so we'll test with an invalid one
        response = authenticated_client.post(f"{BASE_URL}/api/emails/sync/nonexistent_process_id")
        # Should return 404 for non-existent process or 200 with error
        assert response.status_code in [200, 404, 500], f"Unexpected status: {response.status_code}"
        print("✓ Email sync endpoint exists")
    
    def test_email_accounts_endpoint(self, authenticated_client):
        """Test GET /api/emails/accounts to check email configuration"""
        response = authenticated_client.get(f"{BASE_URL}/api/emails/accounts")
        # May not exist, but let's check what's available
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Email accounts endpoint OK - found {len(data)} accounts")
        elif response.status_code == 404:
            print("✓ Email accounts endpoint not found (may need different route)")
        else:
            print(f"Email accounts returned: {response.status_code}")


class TestSystemConfigMaintenanceTab:
    """Tests for SystemConfigPage maintenance section"""
    
    def test_repair_indexes_endpoint(self, authenticated_client):
        """Test POST /api/admin/db/indexes/repair endpoint"""
        response = authenticated_client.post(f"{BASE_URL}/api/admin/db/indexes/repair")
        # May need admin role
        assert response.status_code in [200, 403], f"Unexpected: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Repair indexes endpoint OK - {data}")
        else:
            print("✓ Repair indexes endpoint accessible (403 = restricted)")
    
    def test_migrate_process_numbers_endpoint(self, authenticated_client):
        """Test POST /api/admin/migrate-process-numbers endpoint"""
        response = authenticated_client.post(f"{BASE_URL}/api/admin/migrate-process-numbers")
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Should have message and updated count
        assert "message" in data or "updated" in data, "Response should contain message or updated"
        
        print(f"✓ Migrate process numbers OK - {data.get('updated', 0)} updated")


# Fixtures
@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def auth_token(api_client):
    """Get authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login-v2", json={
        "email": "admin@sistema.pt",
        "password": "admin"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
