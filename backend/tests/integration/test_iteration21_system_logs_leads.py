"""
Iteration 21: Test System Logs and Leads from URL features
==========================================================
Tests:
- Bug fix: client_email and client_phone should accept strings without validation errors
- POST /api/leads/from-url - create lead from URL
- GET /api/admin/system-logs - list error logs  
- GET /api/admin/system-logs/stats - logs statistics
- POST /api/admin/system-logs/mark-read - mark as read
- POST /api/admin/system-logs/{error_id}/resolve - resolve error
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAdminLogin:
    """Test admin authentication"""
    
    def test_admin_login_success(self):
        """Test login with admin credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "access_token not in response"
        print(f"PASS: Admin login successful")
        return data["access_token"]


class TestProcessUpdateStringFields:
    """Test that client_email and client_phone accept string values"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        if response.status_code != 200:
            pytest.skip("Could not login as admin")
        return response.json()["access_token"]
    
    def test_process_update_with_string_email(self, admin_token):
        """Test updating process with string email value (bug fix verification)"""
        # First get a process
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/processes", headers=headers)
        assert response.status_code == 200, f"Failed to get processes: {response.text}"
        
        processes = response.json()
        if not processes:
            pytest.skip("No processes available for testing")
        
        process_id = processes[0]["id"]
        
        # Try to update with string email
        update_data = {
            "client_email": "test_string@email.com",
            "client_phone": "912345678"
        }
        
        response = requests.put(
            f"{BASE_URL}/api/processes/{process_id}",
            json=update_data,
            headers=headers
        )
        
        assert response.status_code == 200, f"Process update failed: {response.text}"
        print(f"PASS: Process update with string email/phone succeeded")
    
    def test_process_update_with_numeric_string_phone(self, admin_token):
        """Test updating process with numeric string phone (e.g., '912345678')"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/processes", headers=headers)
        assert response.status_code == 200
        
        processes = response.json()
        if not processes:
            pytest.skip("No processes available for testing")
        
        process_id = processes[0]["id"]
        
        # Try with numeric-looking string that could be parsed as number
        update_data = {
            "client_phone": "912345678",  # Numeric string
            "client_email": "test@test.pt"  # Valid email string
        }
        
        response = requests.put(
            f"{BASE_URL}/api/processes/{process_id}",
            json=update_data,
            headers=headers
        )
        
        # Should NOT get validation error about 'Input should be a valid number'
        assert response.status_code == 200, f"Update failed with: {response.text}"
        print(f"PASS: Process update with numeric string phone succeeded")


class TestLeadsFromURL:
    """Test POST /api/leads/from-url endpoint"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        if response.status_code != 200:
            pytest.skip("Could not login as admin")
        return response.json()["access_token"]
    
    def test_leads_from_url_endpoint_exists(self, admin_token):
        """Test that POST /api/leads/from-url endpoint exists"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Try with invalid URL to just verify endpoint exists
        response = requests.post(
            f"{BASE_URL}/api/leads/from-url",
            json={"url": "https://example.com/test-property"},
            headers=headers
        )
        
        # Should get 200 with success=False or success=True, not 404
        assert response.status_code == 200, f"Endpoint returned {response.status_code}: {response.text}"
        data = response.json()
        assert "success" in data, "Response should have 'success' field"
        print(f"PASS: POST /api/leads/from-url endpoint exists, success={data.get('success')}")
    
    def test_leads_from_url_requires_url(self, admin_token):
        """Test that URL is required"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/leads/from-url",
            json={},
            headers=headers
        )
        
        # Should get 400 Bad Request
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print(f"PASS: Endpoint correctly requires URL parameter")
    
    def test_leads_from_url_duplicate_check(self, admin_token):
        """Test that duplicate URL check works"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First, create a lead
        test_url = f"https://example.com/test-property-{uuid.uuid4()}"
        response = requests.post(
            f"{BASE_URL}/api/leads/from-url",
            json={"url": test_url},
            headers=headers
        )
        
        # Try again with same URL (should detect duplicate)
        response2 = requests.post(
            f"{BASE_URL}/api/leads/from-url",
            json={"url": test_url},
            headers=headers
        )
        
        assert response2.status_code == 200, f"Expected 200, got {response2.status_code}"
        data = response2.json()
        # Should indicate duplicate
        assert data.get("success") == False or "existe" in data.get("message", "").lower(), \
            f"Should detect duplicate: {data}"
        print(f"PASS: Duplicate URL detection works")


class TestSystemErrorLogs:
    """Test /api/admin/system-logs endpoints"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        if response.status_code != 200:
            pytest.skip("Could not login as admin")
        return response.json()["access_token"]
    
    def test_get_system_logs(self, admin_token):
        """Test GET /api/admin/system-logs returns logs"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs",
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check response structure
        assert "errors" in data, "Response should have 'errors' field"
        assert "total" in data, "Response should have 'total' field"
        assert "page" in data, "Response should have 'page' field"
        assert "pages" in data, "Response should have 'pages' field"
        
        print(f"PASS: GET /api/admin/system-logs returns {data['total']} logs")
    
    def test_get_system_logs_with_filters(self, admin_token):
        """Test GET /api/admin/system-logs with query parameters"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Test with severity filter
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs",
            params={"severity": "warning", "days": 30, "limit": 10},
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"PASS: GET /api/admin/system-logs with filters works")
    
    def test_get_system_logs_stats(self, admin_token):
        """Test GET /api/admin/system-logs/stats returns statistics"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs/stats",
            headers=headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check stats structure
        assert "total" in data, "Stats should have 'total'"
        assert "unread" in data, "Stats should have 'unread'"
        assert "unresolved" in data, "Stats should have 'unresolved'"
        assert "critical" in data, "Stats should have 'critical'"
        
        print(f"PASS: GET /api/admin/system-logs/stats - total={data['total']}, unread={data['unread']}, critical={data['critical']}")
    
    def test_mark_logs_as_read(self, admin_token):
        """Test POST /api/admin/system-logs/mark-read"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get some logs
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs",
            params={"limit": 5},
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            errors = data.get("errors", [])
            
            if errors:
                error_ids = [e["id"] for e in errors[:2]]  # Mark first 2 as read
                
                response = requests.post(
                    f"{BASE_URL}/api/admin/system-logs/mark-read",
                    json={"error_ids": error_ids},
                    headers=headers
                )
                
                assert response.status_code == 200, f"Failed: {response.text}"
                result = response.json()
                assert "marked_count" in result, "Response should have marked_count"
                print(f"PASS: POST /api/admin/system-logs/mark-read - marked {result.get('marked_count')} logs")
            else:
                print("SKIP: No logs available to mark as read")
        else:
            pytest.skip("Could not get logs")
    
    def test_mark_read_requires_error_ids(self, admin_token):
        """Test that mark-read endpoint requires error_ids"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/system-logs/mark-read",
            json={},
            headers=headers
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print(f"PASS: mark-read correctly requires error_ids")
    
    def test_resolve_error(self, admin_token):
        """Test POST /api/admin/system-logs/{error_id}/resolve"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # First get an unresolved log
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs",
            params={"resolved": "false", "limit": 1},
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            errors = data.get("errors", [])
            
            if errors:
                error_id = errors[0]["id"]
                
                response = requests.post(
                    f"{BASE_URL}/api/admin/system-logs/{error_id}/resolve",
                    json={"notes": "Resolved during iteration 21 testing"},
                    headers=headers
                )
                
                assert response.status_code == 200, f"Failed: {response.text}"
                result = response.json()
                assert result.get("success") == True, "Should return success=True"
                print(f"PASS: POST /api/admin/system-logs/{error_id}/resolve - error resolved")
            else:
                print("SKIP: No unresolved logs available")
        else:
            pytest.skip("Could not get logs")
    
    def test_resolve_nonexistent_error(self, admin_token):
        """Test resolve endpoint returns 404 for non-existent error"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        fake_id = "nonexistent-error-id-12345"
        response = requests.post(
            f"{BASE_URL}/api/admin/system-logs/{fake_id}/resolve",
            json={"notes": "Test"},
            headers=headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"PASS: resolve endpoint returns 404 for non-existent error")


class TestSystemLogsAccess:
    """Test that system logs require admin access"""
    
    def test_system_logs_requires_auth(self):
        """Test that unauthenticated requests are rejected"""
        response = requests.get(f"{BASE_URL}/api/admin/system-logs")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: System logs requires authentication")
    
    def test_system_logs_requires_admin_role(self):
        """Test that non-admin users cannot access system logs"""
        # Login as consultor
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "consultor@sistema.pt",
            "password": "consultor123"
        })
        
        if login_response.status_code != 200:
            pytest.skip("Could not login as consultor")
        
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/system-logs", headers=headers)
        
        # Should be forbidden for non-admin
        assert response.status_code == 403, f"Expected 403 Forbidden, got {response.status_code}"
        print(f"PASS: System logs requires admin role")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
