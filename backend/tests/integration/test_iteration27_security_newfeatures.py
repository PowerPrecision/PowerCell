"""
=============================================================================
ITERATION 27 - TESTING NEW SECURITY & AI FEATURES
=============================================================================
Tests for:
1. Security Headers in all HTTP responses (X-Frame-Options, CSP, etc.)
2. /api/ai/bulk/background-jobs - Background job tracking
3. /api/ai/bulk/suggest-clients - Client suggestions with fuzzy matching
4. /api/admin/ai-import-logs - AI import logs endpoint
5. /api/admin/ai-training - AI training data CRUD
6. /api/properties/{id}/documents - Property documents endpoints
=============================================================================
"""
import os
import pytest
import requests
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Session to share token across tests (avoids rate limiting from multiple logins)
_session = None
_token = None

def get_auth_session():
    """Get or create authenticated session"""
    global _session, _token
    if _session is None or _token is None:
        _session = requests.Session()
        # Add delay to avoid rate limiting
        time.sleep(0.5)
        login_response = _session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        if login_response.status_code == 200:
            _token = login_response.json().get("access_token")
            _session.headers.update({"Authorization": f"Bearer {_token}"})
        elif login_response.status_code == 429:
            # Wait and retry
            time.sleep(2)
            login_response = _session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "admin@admin.com", "password": "admin"}
            )
            if login_response.status_code == 200:
                _token = login_response.json().get("access_token")
                _session.headers.update({"Authorization": f"Bearer {_token}"})
    return _session, _token


class TestSecurityHeaders:
    """Test security headers presence in HTTP responses"""
    
    def test_api_health_check_security_headers(self):
        """Test security headers are present in /api endpoints (not /health which goes to frontend)"""
        # The /health endpoint goes to frontend Express, not FastAPI
        # We need to test /api/ endpoints for security headers
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/properties/stats")
        assert response.status_code == 200
        
        # Verify X-Frame-Options header
        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"
        print("✅ X-Frame-Options: DENY")
        
        # Verify X-Content-Type-Options header
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        print("✅ X-Content-Type-Options: nosniff")
        
        # Verify X-XSS-Protection header
        assert "X-XSS-Protection" in response.headers
        assert "1; mode=block" in response.headers["X-XSS-Protection"]
        print("✅ X-XSS-Protection: 1; mode=block")
        
        # Verify Strict-Transport-Security header
        assert "Strict-Transport-Security" in response.headers
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
        print("✅ Strict-Transport-Security present")
        
        # Verify Referrer-Policy header
        assert "Referrer-Policy" in response.headers
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        print("✅ Referrer-Policy: strict-origin-when-cross-origin")
        
        # Verify Content-Security-Policy header
        assert "Content-Security-Policy" in response.headers
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        print("✅ Content-Security-Policy present with default-src 'self' and frame-ancestors 'none'")
        
        # Verify Permissions-Policy header
        assert "Permissions-Policy" in response.headers
        pp = response.headers["Permissions-Policy"]
        assert "camera=()" in pp
        assert "microphone=()" in pp
        print("✅ Permissions-Policy present with restricted features")
    
    def test_api_endpoint_security_headers(self):
        """Test security headers are present in API responses (authenticated)"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        # Test GET /api/properties
        response = session.get(f"{BASE_URL}/api/properties")
        assert response.status_code == 200
        
        # Verify security headers on authenticated endpoint
        assert "X-Frame-Options" in response.headers
        assert "X-Content-Type-Options" in response.headers
        assert "Content-Security-Policy" in response.headers
        print("✅ Security headers present on /api/properties endpoint")


class TestBackgroundJobs:
    """Test /api/ai/bulk/background-jobs endpoint"""
    
    def test_get_background_jobs_list(self):
        """Test GET /api/ai/bulk/background-jobs returns job list"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/ai/bulk/background-jobs")
        assert response.status_code == 200
        
        data = response.json()
        assert "jobs" in data
        assert "counts" in data
        assert isinstance(data["jobs"], list)
        
        # Verify counts structure
        counts = data["counts"]
        assert "running" in counts
        assert "success" in counts
        assert "failed" in counts
        assert "total" in counts
        print(f"✅ GET /api/ai/bulk/background-jobs: {counts['total']} jobs found")
    
    def test_get_background_jobs_with_status_filter(self):
        """Test GET /api/ai/bulk/background-jobs with status filter"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/ai/bulk/background-jobs?status=running")
        assert response.status_code == 200
        
        data = response.json()
        assert "jobs" in data
        # All returned jobs should have status "running" (or be empty)
        for job in data["jobs"]:
            assert job.get("status") == "running"
        print("✅ GET /api/ai/bulk/background-jobs?status=running: filter works")
    
    def test_get_background_jobs_with_limit(self):
        """Test GET /api/ai/bulk/background-jobs with limit parameter"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/ai/bulk/background-jobs?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["jobs"]) <= 5
        print("✅ GET /api/ai/bulk/background-jobs?limit=5: limit works")
    
    def test_clear_finished_jobs(self):
        """Test DELETE /api/ai/bulk/background-jobs clears finished jobs"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.delete(f"{BASE_URL}/api/ai/bulk/background-jobs?only_failed=false")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert "removed_count" in data
        print(f"✅ DELETE /api/ai/bulk/background-jobs: {data['removed_count']} jobs removed")


class TestSuggestClients:
    """Test /api/ai/bulk/suggest-clients endpoint"""
    
    def test_suggest_clients_basic(self):
        """Test GET /api/ai/bulk/suggest-clients?query=X returns suggestions"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/ai/bulk/suggest-clients?query=Test")
        assert response.status_code == 200
        
        data = response.json()
        assert "query" in data
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        print(f"✅ GET /api/ai/bulk/suggest-clients: {len(data['suggestions'])} suggestions for 'Test'")
    
    def test_suggest_clients_short_query(self):
        """Test suggest-clients with too short query"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/ai/bulk/suggest-clients?query=A")
        assert response.status_code == 200
        
        data = response.json()
        # Should return message about minimum characters
        assert data.get("suggestions") == []
        assert "pelo menos 2" in data.get("message", "").lower() or len(data.get("message", "")) > 0
        print("✅ GET /api/ai/bulk/suggest-clients: handles short query correctly")
    
    def test_suggest_clients_with_limit(self):
        """Test suggest-clients with limit parameter"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/ai/bulk/suggest-clients?query=Test&limit=3")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["suggestions"]) <= 3
        print("✅ GET /api/ai/bulk/suggest-clients?limit=3: limit works")


class TestAIImportLogs:
    """Test /api/admin/ai-import-logs endpoint"""
    
    def test_get_ai_import_logs(self):
        """Test GET /api/admin/ai-import-logs returns logs"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/admin/ai-import-logs")
        assert response.status_code == 200
        
        data = response.json()
        assert "logs" in data
        assert "pagination" in data
        assert "stats" in data
        
        # Verify pagination structure
        pagination = data["pagination"]
        assert "page" in pagination
        assert "limit" in pagination
        assert "total" in pagination
        assert "total_pages" in pagination
        
        # Verify stats structure
        stats = data["stats"]
        assert "total_errors" in stats
        assert "unresolved" in stats
        assert "resolved" in stats
        
        print(f"✅ GET /api/admin/ai-import-logs: {stats['total_errors']} total logs")
    
    def test_get_ai_import_logs_with_filters(self):
        """Test ai-import-logs with filters"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/admin/ai-import-logs?page=1&limit=10&days=30")
        assert response.status_code == 200
        
        data = response.json()
        assert data["pagination"]["limit"] == 10
        print("✅ GET /api/admin/ai-import-logs with filters works")


class TestAITraining:
    """Test /api/admin/ai-training CRUD endpoints"""
    
    def test_get_ai_training_data(self):
        """Test GET /api/admin/ai-training returns training data"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/admin/ai-training")
        assert response.status_code == 200
        
        data = response.json()
        assert "total" in data
        assert "categories" in data
        assert "data" in data
        print(f"✅ GET /api/admin/ai-training: {data['total']} training entries")
    
    def test_create_ai_training_entry(self):
        """Test POST /api/admin/ai-training creates new entry"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        test_entry = {
            "category": "custom_rules",
            "title": f"TEST_Entry_{uuid.uuid4().hex[:8]}",
            "content": "Test content for AI training",
            "examples": ["example1", "example2"],
            "is_active": True
        }
        
        time.sleep(0.3)
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{BASE_URL}/api/admin/ai-training", json=test_entry)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert "entry" in data
        assert data["entry"]["title"] == test_entry["title"]
        assert data["entry"]["category"] == "custom_rules"
        
        created_entry_id = data["entry"]["id"]
        print(f"✅ POST /api/admin/ai-training: created entry {created_entry_id}")
        
        # Cleanup - delete the test entry
        time.sleep(0.3)
        session.delete(f"{BASE_URL}/api/admin/ai-training/{created_entry_id}")
    
    def test_ai_training_invalid_category(self):
        """Test POST /api/admin/ai-training rejects invalid category"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        test_entry = {
            "category": "invalid_category",
            "title": "Test",
            "content": "Test content"
        }
        
        time.sleep(0.3)
        session.headers.update({"Content-Type": "application/json"})
        response = session.post(f"{BASE_URL}/api/admin/ai-training", json=test_entry)
        assert response.status_code == 400
        assert "inválida" in response.json().get("detail", "").lower() or "invalid" in response.json().get("detail", "").lower()
        print("✅ POST /api/admin/ai-training: rejects invalid category")
    
    def test_get_ai_training_prompt(self):
        """Test GET /api/admin/ai-training/prompt returns consolidated prompt"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/admin/ai-training/prompt")
        assert response.status_code == 200
        
        data = response.json()
        assert "prompt" in data
        assert "entries_count" in data
        assert "categories" in data
        print(f"✅ GET /api/admin/ai-training/prompt: {data['entries_count']} active entries in prompt")


class TestPropertyDocuments:
    """Test /api/properties/{id}/documents endpoints"""
    
    def test_get_property_documents(self):
        """Test GET /api/properties/{id}/documents returns documents list"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        # First get a property ID
        time.sleep(0.3)
        props_response = session.get(f"{BASE_URL}/api/properties")
        assert props_response.status_code == 200
        
        props = props_response.json()
        if not props:
            pytest.skip("No properties found in database")
        
        property_id = props[0]["id"]
        
        # Get documents for this property
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/properties/{property_id}/documents")
        assert response.status_code == 200
        
        data = response.json()
        assert "property_id" in data
        assert "total" in data
        assert "documents" in data
        assert isinstance(data["documents"], list)
        print(f"✅ GET /api/properties/{property_id}/documents: {data['total']} documents")
    
    def test_get_property_documents_filtered(self):
        """Test GET /api/properties/{id}/documents with document_type filter"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        # First get a property ID
        time.sleep(0.3)
        props_response = session.get(f"{BASE_URL}/api/properties")
        assert props_response.status_code == 200
        
        props = props_response.json()
        if not props:
            pytest.skip("No properties found in database")
        
        property_id = props[0]["id"]
        
        # Get documents with filter
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/properties/{property_id}/documents?document_type=caderneta_predial")
        assert response.status_code == 200
        
        data = response.json()
        # All returned documents should have the filtered type
        for doc in data.get("documents", []):
            assert doc.get("document_type") == "caderneta_predial"
        print("✅ GET /api/properties/{id}/documents with filter works")
    
    def test_property_documents_not_found(self):
        """Test GET /api/properties/{id}/documents returns 404 for invalid property"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        fake_id = "non-existent-property-id"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/properties/{fake_id}/documents")
        assert response.status_code == 404
        print("✅ GET /api/properties/{invalid_id}/documents returns 404")


class TestInputSanitization:
    """Test input sanitization doesn't break normal flows"""
    
    def test_normal_client_search(self):
        """Test that normal text search works with sanitization enabled"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/ai/bulk/suggest-clients?query=João Silva")
        assert response.status_code == 200
        print("✅ Normal search with accented characters works")
    
    def test_xss_attempt_blocked(self):
        """Test that XSS attempts are handled (either blocked or sanitized)"""
        session, token = get_auth_session()
        assert token is not None, "Failed to authenticate"
        
        # This should not cause a server error - it should be sanitized or handled
        time.sleep(0.3)
        response = session.get(f"{BASE_URL}/api/ai/bulk/suggest-clients?query=<script>alert('xss')</script>")
        # Should return 200 with empty/safe results, not 500
        assert response.status_code in [200, 400]
        print("✅ XSS attempt in query handled safely")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
