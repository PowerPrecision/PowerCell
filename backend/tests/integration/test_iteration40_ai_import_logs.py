"""
Test Suite for AI Import Logs features - Iteration 40
Tests:
1. System Logs (Erros do Sistema) - GET /api/admin/system-logs
2. AI Import Logs - GET /api/admin/ai-import-logs-v2
3. AI Import Logs Grouped - GET /api/admin/ai-import-logs-v2/grouped
4. Bulk Resolve AI Import Logs - POST /api/admin/ai-import-logs/bulk-resolve
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

class TestAdminAuth:
    """Authentication tests for admin endpoints"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        return data["access_token"]
    
    def test_admin_login_success(self):
        """Test admin login works"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "admin"


class TestSystemLogs:
    """Test System Error Logs (Erros do Sistema) tab"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        return response.json().get("access_token")
    
    def test_get_system_logs_endpoint_exists(self, admin_token):
        """Test GET /api/admin/system-logs endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs?days=30",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # Should be 200 or return data structure (not 404)
        assert response.status_code in [200, 204], f"System logs endpoint failed: {response.status_code}"
    
    def test_get_system_logs_with_filters(self, admin_token):
        """Test GET /api/admin/system-logs with various filters"""
        # Test with days filter
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs?days=30&page=1&limit=25",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Should have expected structure
        assert "errors" in data or "total" in data, f"Unexpected response structure: {data.keys()}"
    
    def test_get_system_logs_stats(self, admin_token):
        """Test GET /api/admin/system-logs/stats endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs/stats?days=30",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Should have stats fields
        assert "total" in data, f"Missing 'total' in stats: {data.keys()}"
    
    def test_bulk_resolve_system_logs(self, admin_token):
        """Test POST /api/admin/system-logs/bulk-resolve endpoint exists"""
        # Test with empty array (valid request, should not fail with 404)
        response = requests.post(
            f"{BASE_URL}/api/admin/system-logs/bulk-resolve",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={"error_ids": []}
        )
        # Should return 400 for empty array, not 404
        assert response.status_code in [200, 400], f"Bulk resolve endpoint issue: {response.status_code}"


class TestAIImportLogs:
    """Test AI Import Logs (Importações IA) tab - List view"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        return response.json().get("access_token")
    
    def test_get_ai_import_logs_v2(self, admin_token):
        """Test GET /api/admin/ai-import-logs-v2 endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/ai-import-logs-v2?days=30&page=1&limit=25",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"AI import logs failed: {response.text}"
        data = response.json()
        
        # Should have expected structure
        assert "logs" in data, f"Missing 'logs' in response: {data.keys()}"
        assert "pagination" in data, f"Missing 'pagination' in response: {data.keys()}"
        assert "stats" in data, f"Missing 'stats' in response: {data.keys()}"
        
        # Validate pagination structure
        pagination = data["pagination"]
        assert "page" in pagination
        assert "limit" in pagination
        assert "total" in pagination
        assert "total_pages" in pagination
        
        # Validate stats structure
        stats = data["stats"]
        assert "total" in stats
        assert "success" in stats
        assert "error" in stats
        
        print(f"AI Import Logs stats: total={stats.get('total')}, success={stats.get('success')}, error={stats.get('error')}")
    
    def test_ai_import_logs_with_status_filter(self, admin_token):
        """Test filtering AI import logs by status"""
        # Test error filter
        response = requests.get(
            f"{BASE_URL}/api/admin/ai-import-logs-v2?days=30&status=error",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        
        # Test success filter
        response = requests.get(
            f"{BASE_URL}/api/admin/ai-import-logs-v2?days=30&status=success",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
    
    def test_ai_import_logs_log_structure(self, admin_token):
        """Test that individual log entries have expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/ai-import-logs-v2?days=30&limit=5",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["logs"]:
            log = data["logs"][0]
            # Check expected fields
            expected_fields = ["id", "status", "client_name", "timestamp"]
            for field in expected_fields:
                assert field in log, f"Missing field '{field}' in log: {log.keys()}"
            print(f"Log fields present: {list(log.keys())}")


class TestAIImportLogsGrouped:
    """Test AI Import Logs grouped by client (Vista Clientes)"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        return response.json().get("access_token")
    
    def test_get_ai_import_logs_grouped(self, admin_token):
        """Test GET /api/admin/ai-import-logs-v2/grouped endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/admin/ai-import-logs-v2/grouped?days=30",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Grouped logs failed: {response.text}"
        data = response.json()
        
        # Should have expected structure
        assert "groups" in data, f"Missing 'groups' in response: {data.keys()}"
        assert "stats" in data, f"Missing 'stats' in response: {data.keys()}"
        
        # Validate stats structure for grouped view
        stats = data["stats"]
        assert "total_clients" in stats, f"Missing 'total_clients' in stats: {stats.keys()}"
        assert "total_docs" in stats, f"Missing 'total_docs' in stats: {stats.keys()}"
        assert "total_success" in stats, f"Missing 'total_success' in stats: {stats.keys()}"
        assert "total_errors" in stats, f"Missing 'total_errors' in stats: {stats.keys()}"
        
        print(f"Grouped stats: clients={stats.get('total_clients')}, docs={stats.get('total_docs')}, success={stats.get('total_success')}, errors={stats.get('total_errors')}")
    
    def test_grouped_logs_with_status_filter(self, admin_token):
        """Test filtering grouped logs by status"""
        response = requests.get(
            f"{BASE_URL}/api/admin/ai-import-logs-v2/grouped?days=30&status=error",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "groups" in data
    
    def test_grouped_logs_group_structure(self, admin_token):
        """Test that client groups have expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/ai-import-logs-v2/grouped?days=30",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["groups"]:
            group = data["groups"][0]
            # Check expected fields for a client group
            expected_fields = ["client_name", "total_docs", "success_count", "error_count", "logs"]
            for field in expected_fields:
                assert field in group, f"Missing field '{field}' in group: {group.keys()}"
            print(f"Group fields present: {list(group.keys())}")
            print(f"First group: client={group['client_name']}, docs={group['total_docs']}, success={group['success_count']}, errors={group['error_count']}")


class TestBulkResolveAIImportLogs:
    """Test bulk resolve functionality for AI import logs"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        return response.json().get("access_token")
    
    def test_bulk_resolve_endpoint_exists(self, admin_token):
        """Test POST /api/admin/ai-import-logs/bulk-resolve endpoint"""
        # Test with empty array (should return 400, not 404)
        response = requests.post(
            f"{BASE_URL}/api/admin/ai-import-logs/bulk-resolve",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={"log_ids": []}
        )
        # Should return 400 for empty array, not 404
        assert response.status_code in [200, 400], f"Bulk resolve endpoint issue: {response.status_code}, {response.text}"
    
    def test_bulk_resolve_with_fake_ids(self, admin_token):
        """Test bulk resolve with non-existent IDs (should succeed with 0 resolved)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/ai-import-logs/bulk-resolve",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={"log_ids": ["fake-id-12345", "fake-id-67890"]}
        )
        assert response.status_code == 200, f"Bulk resolve failed: {response.text}"
        data = response.json()
        # Should indicate success with resolved_count
        assert "success" in data or "resolved_count" in data


class TestSingleLogResolve:
    """Test single log resolve functionality"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        return response.json().get("access_token")
    
    def test_resolve_single_ai_import_log_endpoint(self, admin_token):
        """Test POST /api/admin/ai-import-logs/{log_id}/resolve endpoint"""
        # First get a log ID if any exists
        response = requests.get(
            f"{BASE_URL}/api/admin/ai-import-logs-v2?days=30&status=error&limit=1",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("logs"):
                log_id = data["logs"][0]["id"]
                # Test resolve endpoint
                resolve_response = requests.post(
                    f"{BASE_URL}/api/admin/ai-import-logs/{log_id}/resolve",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                assert resolve_response.status_code in [200, 404], f"Resolve endpoint failed: {resolve_response.status_code}"
            else:
                print("No error logs to test resolve endpoint")
        else:
            pytest.skip("Could not get logs to test resolve endpoint")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
