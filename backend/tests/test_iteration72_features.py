"""
Iteration 72 Tests - P2 Backlog Items
=====================================
Tests for:
- O3: Rate limiting on document endpoints (upload 30/min, delete 20/min, AI analysis 10/min)
- O10: Cursor pagination on GET /api/clients/registered
- O24: UnifiedAuditTrail component verification
- O6: Skeleton loaders (animate-pulse) verification
- Bug fix: clients.py duplicate $or key fix
- Stale processes endpoint verification
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndBasics:
    """Basic health and connectivity tests"""
    
    def test_health_endpoint(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health endpoint working")

class TestCursorPagination:
    """O10 - Cursor pagination tests for /api/clients/registered"""
    
    def test_registered_clients_endpoint_exists(self):
        """Test that registered clients endpoint exists (may require auth)"""
        response = requests.get(f"{BASE_URL}/api/clients/registered")
        # Should return 401 (unauthorized) or 200 (if no auth required)
        assert response.status_code in [200, 401, 403]
        print(f"✓ Registered clients endpoint exists (status: {response.status_code})")
    
    def test_cursor_params_accepted(self):
        """Test that cursor and cursor_id params are accepted"""
        # Test with cursor params - should not return 422 (validation error)
        response = requests.get(
            f"{BASE_URL}/api/clients/registered",
            params={"cursor": "test", "cursor_id": "test123"}
        )
        # Should return 401 (auth) or 200, not 422 (param validation error)
        assert response.status_code != 422, "Cursor params should be accepted"
        print(f"✓ Cursor params accepted (status: {response.status_code})")
    
    def test_backwards_compatibility_skip_limit(self):
        """Test that skip/limit still works without cursor"""
        response = requests.get(
            f"{BASE_URL}/api/clients/registered",
            params={"skip": 0, "limit": 10}
        )
        # Should return 401 (auth) or 200, not 422
        assert response.status_code != 422, "Skip/limit should still work"
        print(f"✓ Skip/limit backwards compatible (status: {response.status_code})")

class TestStaleProcessesEndpoint:
    """Test stale processes admin endpoint"""
    
    def test_stale_processes_endpoint_exists(self):
        """Test that stale processes endpoint exists"""
        response = requests.get(f"{BASE_URL}/api/admin/stale-processes")
        # Should return 401 (unauthorized) or 200 (if accessible)
        assert response.status_code in [200, 401, 403]
        print(f"✓ Stale processes endpoint exists (status: {response.status_code})")
    
    def test_stale_processes_with_days_param(self):
        """Test stale processes with days parameter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/stale-processes",
            params={"days": 14}
        )
        # Should accept days param without 422 error
        assert response.status_code != 422, "Days param should be accepted"
        print(f"✓ Days param accepted (status: {response.status_code})")

class TestDocumentEndpoints:
    """O3 - Document endpoints with rate limiting"""
    
    def test_document_upload_endpoint_exists(self):
        """Test document upload endpoint exists"""
        # POST without file should return 422 (missing file) or 401 (auth)
        response = requests.post(f"{BASE_URL}/api/documents/client/test123/upload")
        assert response.status_code in [401, 403, 422]
        print(f"✓ Document upload endpoint exists (status: {response.status_code})")
    
    def test_document_delete_endpoint_exists(self):
        """Test document delete endpoint exists"""
        response = requests.delete(
            f"{BASE_URL}/api/documents/client/test123/file",
            params={"file_path": "test/path"}
        )
        assert response.status_code in [401, 403, 404]
        print(f"✓ Document delete endpoint exists (status: {response.status_code})")
    
    def test_ai_analyze_endpoint_exists(self):
        """Test AI analyze endpoint exists"""
        response = requests.post(f"{BASE_URL}/api/documents/ai-analyze/test123")
        assert response.status_code in [401, 403, 422]
        print(f"✓ AI analyze endpoint exists (status: {response.status_code})")

class TestCodeVerification:
    """Code verification tests for rate limiting and cursor pagination"""
    
    def test_rate_limit_decorator_on_upload(self):
        """Verify rate limit decorator on upload endpoint"""
        with open("/app/backend/routes/documents.py", "r") as f:
            content = f.read()
        
        # Find upload endpoint and check for rate limit
        upload_pattern = r'@limiter\.limit\("30/minute"\)\s*\nasync def upload_file_s3'
        assert re.search(upload_pattern, content), "Upload should have 30/minute rate limit"
        print("✓ Upload endpoint has 30/minute rate limit")
    
    def test_rate_limit_decorator_on_delete(self):
        """Verify rate limit decorator on delete endpoint"""
        with open("/app/backend/routes/documents.py", "r") as f:
            content = f.read()
        
        # Find delete endpoint and check for rate limit
        delete_pattern = r'@limiter\.limit\("20/minute"\)\s*\nasync def delete_file_s3'
        assert re.search(delete_pattern, content), "Delete should have 20/minute rate limit"
        print("✓ Delete endpoint has 20/minute rate limit")
    
    def test_rate_limit_decorator_on_ai_analyze(self):
        """Verify rate limit decorator on AI analyze endpoint"""
        with open("/app/backend/routes/documents.py", "r") as f:
            content = f.read()
        
        # Find AI analyze endpoint and check for rate limit
        ai_pattern = r'@limiter\.limit\("10/minute"\)\s*\nasync def ai_analyze_documents'
        assert re.search(ai_pattern, content), "AI analyze should have 10/minute rate limit"
        print("✓ AI analyze endpoint has 10/minute rate limit")
    
    def test_cursor_pagination_params_in_clients(self):
        """Verify cursor and cursor_id params in clients.py"""
        with open("/app/backend/routes/clients.py", "r") as f:
            content = f.read()
        
        assert 'cursor: Optional[str]' in content, "cursor param should exist"
        assert 'cursor_id: Optional[str]' in content, "cursor_id param should exist"
        print("✓ Cursor pagination params exist in clients.py")
    
    def test_cursor_response_fields_in_clients(self):
        """Verify next_cursor, next_cursor_id, has_more in response"""
        with open("/app/backend/routes/clients.py", "r") as f:
            content = f.read()
        
        assert '"next_cursor":' in content or "'next_cursor':" in content, "next_cursor should be in response"
        assert '"next_cursor_id":' in content or "'next_cursor_id':" in content, "next_cursor_id should be in response"
        assert '"has_more":' in content or "'has_more':" in content, "has_more should be in response"
        print("✓ Cursor response fields exist in clients.py")
    
    def test_duplicate_or_fix_in_clients(self):
        """Verify duplicate $or fix using $and wrapper"""
        with open("/app/backend/routes/clients.py", "r") as f:
            content = f.read()
        
        # Check for $and wrapper pattern around line 485-495
        assert '"$and"' in content or "'$and'" in content, "$and wrapper should exist"
        print("✓ $and wrapper exists in clients.py (duplicate $or fix)")

class TestFrontendComponents:
    """Frontend component verification tests"""
    
    def test_unified_audit_trail_component_exists(self):
        """Verify UnifiedAuditTrail component exists"""
        import os
        path = "/app/frontend/src/components/UnifiedAuditTrail.js"
        assert os.path.exists(path), "UnifiedAuditTrail.js should exist"
        
        with open(path, "r") as f:
            content = f.read()
        
        assert 'data-testid="unified-audit-trail"' in content, "Should have data-testid"
        assert 'EVENT_TYPES' in content, "Should have EVENT_TYPES"
        assert 'status_change' in content, "Should have status_change type"
        assert 'comment' in content, "Should have comment type"
        assert 'document' in content, "Should have document type"
        assert 'email' in content, "Should have email type"
        assert 'assignment' in content, "Should have assignment type"
        print("✓ UnifiedAuditTrail component exists with all event types")
    
    def test_unified_audit_trail_imported_in_process_details(self):
        """Verify UnifiedAuditTrail is imported in ProcessDetails"""
        with open("/app/frontend/src/pages/ProcessDetails.js", "r") as f:
            content = f.read()
        
        assert 'import UnifiedAuditTrail' in content, "Should import UnifiedAuditTrail"
        assert 'Filme da Lead' in content, "Should have 'Filme da Lead' label"
        assert '<UnifiedAuditTrail' in content, "Should use UnifiedAuditTrail component"
        print("✓ UnifiedAuditTrail imported and used in ProcessDetails")
    
    def test_skeleton_loaders_use_animate_pulse(self):
        """Verify skeleton loaders use animate-pulse (not animate-spin)"""
        pages_to_check = [
            "/app/frontend/src/pages/ExpiringDocumentsDashboard.jsx",
            "/app/frontend/src/pages/SystemConfigPage.js",
            "/app/frontend/src/pages/BackupsPage.js",
            "/app/frontend/src/pages/DiagnosticsPage.js",
            "/app/frontend/src/pages/PendingItemsList.js",
            "/app/frontend/src/pages/RGPDPage.jsx",
        ]
        
        for page_path in pages_to_check:
            with open(page_path, "r") as f:
                content = f.read()
            
            # Check for animate-pulse in loading state
            assert 'animate-pulse' in content, f"{page_path} should have animate-pulse skeleton"
            print(f"✓ {page_path.split('/')[-1]} has animate-pulse skeleton")
    
    def test_stale_processes_alert_in_admin_dashboard(self):
        """Verify stale processes alert banner in AdminDashboard"""
        with open("/app/frontend/src/pages/AdminDashboard.js", "r") as f:
            content = f.read()
        
        assert 'stale-processes-alert' in content, "Should have stale-processes-alert data-testid"
        print("✓ AdminDashboard has stale-processes-alert banner")

class TestLimiterImport:
    """Verify limiter is properly imported"""
    
    def test_limiter_imported_in_documents(self):
        """Verify limiter is imported from middleware"""
        with open("/app/backend/routes/documents.py", "r") as f:
            content = f.read()
        
        assert 'from middleware.rate_limit import limiter' in content, "Limiter should be imported"
        print("✓ Limiter imported in documents.py")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
