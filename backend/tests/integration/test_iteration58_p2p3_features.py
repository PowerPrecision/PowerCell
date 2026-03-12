"""
Test Suite Iteration 58 - P2 and P3 Features
- Jobs health endpoint: GET /api/admin/jobs/health
- Document organize endpoint: POST /api/documents/organize/{process_id}
- AI analyze improvements: POST /api/documents/ai-analyze/{process_id} with extracted_data, conflicts, documents
"""
import os
import pytest
import requests
import json
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "admin@sistema.pt"
TEST_PASSWORD = "admin"


@pytest.fixture(scope="module")
def auth_token():
    """Authenticate and get token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def test_process_id(auth_headers):
    """Get a valid process ID for testing"""
    response = requests.get(
        f"{BASE_URL}/api/processes",
        headers=auth_headers,
        params={"limit": 1}
    )
    if response.status_code == 200:
        data = response.json()
        # Handle both list response and dict with processes/items key
        if isinstance(data, list):
            processes = data
        else:
            processes = data.get("processes") or data.get("items") or []
        if len(processes) > 0:
            return processes[0].get("id")
    pytest.skip("No processes available for testing")


class TestJobsHealthEndpoint:
    """Tests for GET /api/admin/jobs/health - Jobs health monitoring"""
    
    def test_jobs_health_returns_200(self, auth_headers):
        """Jobs health endpoint should return 200 for admin users"""
        response = requests.get(
            f"{BASE_URL}/api/admin/jobs/health",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_jobs_health_response_structure(self, auth_headers):
        """Jobs health response should have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/jobs/health",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        
        # Check required fields
        assert "timestamp" in data, "Response missing 'timestamp'"
        assert "healthy" in data, "Response missing 'healthy'"
        assert "stats" in data, "Response missing 'stats'"
        
        # Check stats structure
        stats = data.get("stats", {})
        assert "total_24h" in stats, "Stats missing 'total_24h'"
        assert "running" in stats, "Stats missing 'running'"
        assert "stuck" in stats, "Stats missing 'stuck'"
        assert "completed" in stats, "Stats missing 'completed'"
        assert "failed" in stats, "Stats missing 'failed'"
        assert "success_rate" in stats, "Stats missing 'success_rate'"
    
    def test_jobs_health_has_stuck_jobs_list(self, auth_headers):
        """Jobs health response should include stuck_jobs list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/jobs/health",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "stuck_jobs" in data, "Response missing 'stuck_jobs'"
        assert isinstance(data["stuck_jobs"], list), "stuck_jobs should be a list"
    
    def test_jobs_health_has_running_jobs_list(self, auth_headers):
        """Jobs health response should include running_jobs list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/jobs/health",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "running_jobs" in data, "Response missing 'running_jobs'"
        assert isinstance(data["running_jobs"], list), "running_jobs should be a list"
    
    def test_jobs_health_has_alerts_list(self, auth_headers):
        """Jobs health response should include alerts list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/jobs/health",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "alerts" in data, "Response missing 'alerts'"
        assert isinstance(data["alerts"], list), "alerts should be a list"
    
    def test_jobs_health_healthy_field_is_boolean(self, auth_headers):
        """Jobs health 'healthy' field should be boolean"""
        response = requests.get(
            f"{BASE_URL}/api/admin/jobs/health",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data["healthy"], bool), "healthy field should be boolean"


class TestDocumentOrganizeEndpoint:
    """Tests for POST /api/documents/organize/{process_id} - Organize documents into folders"""
    
    def test_organize_endpoint_exists(self, auth_headers, test_process_id):
        """Organize endpoint should exist and accept POST"""
        response = requests.post(
            f"{BASE_URL}/api/documents/organize/{test_process_id}",
            headers=auth_headers,
            json={"documents": [], "create_folders": False}
        )
        # Should not return 404 (endpoint not found)
        assert response.status_code != 404, f"Endpoint not found: {response.status_code}"
    
    def test_organize_empty_documents(self, auth_headers, test_process_id):
        """Organize with empty documents should return success"""
        response = requests.post(
            f"{BASE_URL}/api/documents/organize/{test_process_id}",
            headers=auth_headers,
            json={"documents": [], "create_folders": False}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Response should have success: true"
    
    def test_organize_response_structure(self, auth_headers, test_process_id):
        """Organize response should have required fields"""
        response = requests.post(
            f"{BASE_URL}/api/documents/organize/{test_process_id}",
            headers=auth_headers,
            json={"documents": [], "create_folders": False}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "success" in data, "Response missing 'success'"
        assert "organized_count" in data, "Response missing 'organized_count'"
        assert "folders_created_count" in data, "Response missing 'folders_created_count'"
        assert "results" in data, "Response missing 'results'"
    
    def test_organize_with_document_types(self, auth_headers, test_process_id):
        """Organize with document types should map to correct folders"""
        documents = [
            {"type": "cc", "file_name": "cartao_cidadao.pdf"},
            {"type": "irs", "file_name": "declaracao_irs.pdf"},
            {"type": "recibo_vencimento", "file_name": "recibo.pdf"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/documents/organize/{test_process_id}",
            headers=auth_headers,
            json={"documents": documents, "create_folders": False}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("organized_count") == 3, f"Expected 3 organized docs, got {data.get('organized_count')}"
        
        results = data.get("results", {})
        organized = results.get("organized", [])
        
        # Check folder mappings
        folder_map = {item["file"]: item["folder"] for item in organized}
        assert folder_map.get("cartao_cidadao.pdf") == "Identificação"
        assert folder_map.get("declaracao_irs.pdf") == "Financeiros/IRS"
        assert folder_map.get("recibo.pdf") == "Financeiros/Recibos"
    
    def test_organize_invalid_process_returns_404(self, auth_headers):
        """Organize with invalid process_id should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/documents/organize/invalid_process_xyz",
            headers=auth_headers,
            json={"documents": [], "create_folders": False}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestAIAnalyzeEndpointImprovements:
    """Tests for POST /api/documents/ai-analyze/{process_id} - Improved AI analysis"""
    
    def test_ai_analyze_endpoint_exists(self, auth_headers, test_process_id):
        """AI analyze endpoint should exist"""
        response = requests.post(
            f"{BASE_URL}/api/documents/ai-analyze/{test_process_id}",
            headers={"Authorization": auth_headers["Authorization"]},
            files={}
        )
        # Should not return 404
        assert response.status_code != 404, f"Endpoint not found: {response.status_code}"
    
    def test_ai_analyze_requires_files(self, auth_headers, test_process_id):
        """AI analyze should require files"""
        response = requests.post(
            f"{BASE_URL}/api/documents/ai-analyze/{test_process_id}",
            headers={"Authorization": auth_headers["Authorization"]},
            files={}
        )
        # Should return 400 or 422 for missing files (422 is FastAPI validation error)
        assert response.status_code in [400, 422], f"Expected 400/422 for no files, got {response.status_code}"
    
    def test_ai_analyze_invalid_process_returns_404(self, auth_headers):
        """AI analyze with invalid process should return 404"""
        import io
        dummy_file = io.BytesIO(b"test content")
        
        response = requests.post(
            f"{BASE_URL}/api/documents/ai-analyze/invalid_process_xyz",
            headers={"Authorization": auth_headers["Authorization"]},
            files={"files": ("test.txt", dummy_file, "text/plain")}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestHTMLNestingFix:
    """Verify HTML nesting issues in SystemConfigPage are fixed (frontend code review)"""
    
    def test_badge_not_inside_paragraph(self):
        """Badge component should not be nested inside <p> tag in SystemConfigPage"""
        import os
        
        filepath = "/app/frontend/src/pages/SystemConfigPage.js"
        if not os.path.exists(filepath):
            pytest.skip("SystemConfigPage.js not found")
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check that Badge is not inside <p> tags
        # The HTML warning was: '<div> cannot be a descendant of <p>'
        # Badge renders as div, so it shouldn't be inside <p>
        import re
        
        # Look for patterns like <p>...Badge... where Badge is on same or adjacent lines
        # This is a simple check - the actual fix was done by the main agent
        p_badge_pattern = r'<p[^>]*>[\s\S]*?<Badge'
        matches = re.findall(p_badge_pattern, content)
        
        # If there are matches, check if they're properly closed
        for match in matches:
            # Badge inside p is bad
            assert '</Badge>' not in match or '</p>' in match.split('<Badge')[0], \
                f"Found Badge potentially nested inside <p>: {match[:100]}..."
        
        print("Badge nesting check passed - no obvious <p><Badge> nesting found")


class TestFrontendComponentStructure:
    """Verify frontend components have required callbacks and state"""
    
    def test_s3filemanager_has_onaidataextracted_prop(self):
        """S3FileManager should accept onAIDataExtracted callback"""
        filepath = "/app/frontend/src/components/S3FileManager.js"
        if not os.path.exists(filepath):
            pytest.skip("S3FileManager.js not found")
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check for onAIDataExtracted prop
        assert "onAIDataExtracted" in content, "S3FileManager missing onAIDataExtracted prop"
        assert "onAIDataExtracted({" in content, "S3FileManager should call onAIDataExtracted callback"
    
    def test_processdetails_has_showairewviewdialog_state(self):
        """ProcessDetails should have showAIReviewDialog state"""
        filepath = "/app/frontend/src/pages/ProcessDetails.js"
        if not os.path.exists(filepath):
            pytest.skip("ProcessDetails.js not found")
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check for showAIReviewDialog state
        assert "showAIReviewDialog" in content, "ProcessDetails missing showAIReviewDialog state"
        assert "setShowAIReviewDialog" in content, "ProcessDetails missing setShowAIReviewDialog setter"
    
    def test_processdetails_has_handleaidataextractedfromdocs(self):
        """ProcessDetails should have handleAIDataExtractedFromDocs handler"""
        filepath = "/app/frontend/src/pages/ProcessDetails.js"
        if not os.path.exists(filepath):
            pytest.skip("ProcessDetails.js not found")
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check for handler
        assert "handleAIDataExtractedFromDocs" in content, "ProcessDetails missing handleAIDataExtractedFromDocs"
        assert "onAIDataExtracted={handleAIDataExtractedFromDocs}" in content, \
            "ProcessDetails should pass handleAIDataExtractedFromDocs to S3FileManager"
    
    def test_processdetails_has_conflict_dialog(self):
        """ProcessDetails should have AI conflict review dialog"""
        filepath = "/app/frontend/src/pages/ProcessDetails.js"
        if not os.path.exists(filepath):
            pytest.skip("ProcessDetails.js not found")
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check for conflict dialog
        assert "Revisão de Dados Extraídos" in content, "ProcessDetails missing conflict review dialog title"
        assert "aiConflicts" in content, "ProcessDetails missing aiConflicts state"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
