"""
Iteration 37 - P1 Features Testing:
1. Advanced Bookmarklet (Idealista Import Page) - Two bookmarklets (Um Clique and Copiar)
2. Pause/Resume Background Jobs functionality
3. Background Jobs stats with 'Pausados' count
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials
ADMIN_CREDENTIALS = {
    "email": "admin@admin.com",
    "password": "admin"
}


class TestAuth:
    """Authentication tests"""
    
    def test_admin_login(self):
        """Test admin login to get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=ADMIN_CREDENTIALS
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data or "token" in data, "No token in response"


@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=ADMIN_CREDENTIALS
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("Authentication failed")


@pytest.fixture
def authenticated_headers(auth_token):
    """Headers with authentication token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestBackgroundJobsEndpoints:
    """Test Background Jobs endpoints including pause/resume"""
    
    def test_list_background_jobs_returns_paused_count(self, authenticated_headers):
        """
        GET /api/ai/bulk/background-jobs should return counts including 'paused' field
        """
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers=authenticated_headers
        )
        assert response.status_code == 200, f"Failed to get jobs: {response.text}"
        
        data = response.json()
        assert "jobs" in data, "Response should contain 'jobs' list"
        assert "counts" in data, "Response should contain 'counts' object"
        
        counts = data["counts"]
        # Verify 'paused' field exists in counts
        assert "paused" in counts, "counts should include 'paused' field"
        assert "running" in counts, "counts should include 'running' field"
        assert "success" in counts, "counts should include 'success' field"
        assert "failed" in counts, "counts should include 'failed' field"
        assert "total" in counts, "counts should include 'total' field"
        
        # paused should be an integer
        assert isinstance(counts["paused"], int), "'paused' should be an integer"
    
    def test_pause_endpoint_exists_returns_404_for_nonexistent_job(self, authenticated_headers):
        """
        POST /api/ai/bulk/background-jobs/{job_id}/pause exists and returns 404 for non-existent job
        """
        fake_job_id = "nonexistent-job-12345"
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{fake_job_id}/pause",
            headers=authenticated_headers
        )
        # Should return 404 for non-existent job (not 405 method not allowed)
        assert response.status_code == 404, f"Expected 404 for non-existent job, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have 'detail' field"
    
    def test_resume_endpoint_exists_returns_404_for_nonexistent_job(self, authenticated_headers):
        """
        POST /api/ai/bulk/background-jobs/{job_id}/resume exists and returns 404 for non-existent job
        """
        fake_job_id = "nonexistent-job-67890"
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{fake_job_id}/resume",
            headers=authenticated_headers
        )
        # Should return 404 for non-existent job (not 405 method not allowed)
        assert response.status_code == 404, f"Expected 404 for non-existent job, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have 'detail' field"
    
    def test_pause_requires_authentication(self):
        """
        POST /api/ai/bulk/background-jobs/{job_id}/pause requires authentication
        """
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/test-job/pause"
        )
        # Should return 401 or 403 for unauthenticated request
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {response.status_code}"
    
    def test_resume_requires_authentication(self):
        """
        POST /api/ai/bulk/background-jobs/{job_id}/resume requires authentication
        """
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/test-job/resume"
        )
        # Should return 401 or 403 for unauthenticated request
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {response.status_code}"
    
    def test_cancel_endpoint_still_works(self, authenticated_headers):
        """
        POST /api/ai/bulk/background-jobs/{job_id}/cancel still works (returns 404 for non-existent)
        """
        fake_job_id = "nonexistent-job-cancel-test"
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{fake_job_id}/cancel",
            headers=authenticated_headers
        )
        assert response.status_code == 404, f"Expected 404 for non-existent job, got {response.status_code}"


class TestIdealistaImportEndpoints:
    """Test endpoints used by Idealista Import page"""
    
    def test_extract_html_endpoint_exists(self, authenticated_headers):
        """
        POST /api/scraper/extract-html endpoint exists and validates input
        """
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html",
            headers=authenticated_headers,
            json={"html": "test"}
        )
        # Should return 400 for short HTML, not 404
        assert response.status_code in [400, 422], f"Endpoint should exist, got {response.status_code}"
    
    def test_extract_html_requires_auth(self):
        """
        POST /api/scraper/extract-html requires authentication
        """
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html",
            json={"html": "test content"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestHealthCheck:
    """Basic health check"""
    
    def test_health_endpoint(self):
        """Backend is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
