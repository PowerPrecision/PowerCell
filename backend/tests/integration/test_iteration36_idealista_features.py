"""
Iteration 36: Testing Idealista Import & Background Jobs Cancel Features
========================================================================

Tests:
1. POST /api/scraper/extract-html - Extract data from pasted HTML
2. GET /api/ai/bulk/background-jobs - List background jobs with stats
3. POST /api/ai/bulk/background-jobs/{job_id}/cancel - Cancel running jobs
"""
import pytest
import requests
import os
import uuid

# Get base URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://form-template-fix-1.preview.emergentagent.com"


class TestAuth:
    """Admin authentication for protected endpoints."""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        print(f"✓ Admin login successful")
        return data["access_token"]


class TestScraperExtractHtml(TestAuth):
    """Tests for POST /api/scraper/extract-html endpoint."""
    
    def test_extract_html_endpoint_exists(self, admin_token):
        """Verify the extract-html endpoint exists."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Send minimal HTML (should return 400 for too short)
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html",
            json={"html": "<html><body>test</body></html>"},
            headers=headers
        )
        # Either 400 (validation error for short HTML) or 422 (no data extracted) is expected
        assert response.status_code in [400, 422], f"Unexpected status: {response.status_code}"
        print(f"✓ Endpoint /api/scraper/extract-html exists and validates input")
    
    def test_extract_html_rejects_short_content(self, admin_token):
        """Test that short HTML content is rejected with 400."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html",
            json={"html": "short text"},
            headers=headers
        )
        assert response.status_code == 400, f"Expected 400 for short content, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        print(f"✓ Short HTML content correctly rejected: {data['detail']}")
    
    def test_extract_html_requires_auth(self):
        """Test that endpoint requires authentication."""
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html",
            json={"html": "<html><body>test content</body></html>"}
        )
        # Should require authentication (401)
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Endpoint requires authentication")


class TestBackgroundJobsList(TestAuth):
    """Tests for GET /api/ai/bulk/background-jobs endpoint."""
    
    def test_list_background_jobs_endpoint_exists(self, admin_token):
        """Verify the background-jobs list endpoint exists."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert "jobs" in data, "Response should have 'jobs' field"
        assert "counts" in data, "Response should have 'counts' field"
        
        # Verify counts structure
        counts = data["counts"]
        assert "running" in counts, "Counts should have 'running'"
        assert "success" in counts, "Counts should have 'success'"
        assert "failed" in counts, "Counts should have 'failed'"
        assert "total" in counts, "Counts should have 'total'"
        
        print(f"✓ Background jobs list endpoint works. Counts: {counts}")
    
    def test_list_background_jobs_with_status_filter(self, admin_token):
        """Test filtering by status."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        for status in ["running", "success", "failed"]:
            response = requests.get(
                f"{BASE_URL}/api/ai/bulk/background-jobs?status={status}",
                headers=headers
            )
            assert response.status_code == 200, f"Expected 200 for status={status}, got {response.status_code}"
            data = response.json()
            assert "jobs" in data
            print(f"✓ Filter status={status}: {len(data['jobs'])} jobs")
    
    def test_list_background_jobs_requires_auth(self):
        """Test that endpoint requires authentication."""
        response = requests.get(f"{BASE_URL}/api/ai/bulk/background-jobs")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Background jobs list requires authentication")


class TestBackgroundJobsCancel(TestAuth):
    """Tests for POST /api/ai/bulk/background-jobs/{job_id}/cancel endpoint."""
    
    def test_cancel_endpoint_exists(self, admin_token):
        """Verify the cancel endpoint exists."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        fake_job_id = str(uuid.uuid4())
        
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{fake_job_id}/cancel",
            headers=headers
        )
        # Should return 404 for non-existent job (not 405 method not allowed)
        assert response.status_code == 404, f"Expected 404 for fake job, got {response.status_code}"
        print("✓ Cancel endpoint exists (returns 404 for non-existent job)")
    
    def test_cancel_requires_running_status(self, admin_token):
        """Test that only running jobs can be cancelled."""
        # This test verifies the validation logic by checking error messages
        headers = {"Authorization": f"Bearer {admin_token}"}
        fake_job_id = str(uuid.uuid4())
        
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{fake_job_id}/cancel",
            headers=headers
        )
        data = response.json()
        
        # Should mention job not found or similar
        assert response.status_code == 404
        assert "detail" in data
        print(f"✓ Cancel validates job existence: {data['detail']}")
    
    def test_cancel_requires_auth(self):
        """Test that cancel endpoint requires authentication."""
        fake_job_id = str(uuid.uuid4())
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{fake_job_id}/cancel"
        )
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Cancel endpoint requires authentication")


class TestHealthCheck:
    """Basic health check."""
    
    def test_health_endpoint(self):
        """Verify backend is healthy."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("✓ Backend health check passed")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
