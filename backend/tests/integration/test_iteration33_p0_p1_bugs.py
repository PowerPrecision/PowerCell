"""
Iteration 33 - Test P0 and P1 Bugs:
- P0: Verify emergentintegrations module is installed and API doesn't return ModuleNotFoundError
- P1: Verify Background Jobs page shows import jobs from DB

API Endpoints tested:
- POST /api/ai/bulk/import-session/start - Create import session
- POST /api/ai/bulk/import-session/{id}/update - Update progress  
- POST /api/ai/bulk/import-session/{id}/finish - Finish session
- GET /api/ai/bulk/background-jobs - List jobs with counts
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://file-refresh-ui.preview.emergentagent.com')


class TestP0EmergentIntegrations:
    """P0: Verify emergentintegrations module is installed and working"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_01_health_endpoint(self):
        """Test backend is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"SUCCESS: Health check passed - {data}")
    
    def test_02_emergentintegrations_module_import(self):
        """P0: Verify emergentintegrations is importable (no ModuleNotFoundError)"""
        # Test that the module is importable by calling an endpoint that uses it
        # The ai_document.py service imports from emergentintegrations
        # If the module is missing, any AI endpoint would fail
        
        # We test the background-jobs endpoint which should work without AI
        # but the services that use AI are loaded at startup
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers=self.headers
        )
        # If emergentintegrations was not installed, the server would fail to start
        # or return 500 with ModuleNotFoundError
        assert response.status_code == 200, f"Background jobs endpoint failed: {response.text}"
        print(f"SUCCESS: emergentintegrations module is working - server started correctly")
    
    def test_03_import_session_start_no_module_error(self):
        """P0: Verify POST /api/ai/bulk/import-session/start doesn't return ModuleNotFoundError"""
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/import-session/start",
            headers=self.headers,
            json={
                "total_files": 5,
                "folder_name": "TEST_P0_ImportSession",
                "client_id": None
            }
        )
        
        # Should NOT return 500 with ModuleNotFoundError
        assert response.status_code != 500 or "ModuleNotFoundError" not in response.text, \
            f"P0 BUG: ModuleNotFoundError returned: {response.text}"
        
        assert response.status_code == 200, f"Import session start failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert "session_id" in data, f"Response missing session_id: {data}"
        assert data["session_id"], f"session_id is empty: {data}"
        
        # Save session_id for cleanup
        self.test_session_id = data["session_id"]
        print(f"SUCCESS: P0 Bug Fixed - Import session created: {data['session_id']}")
        
        return data["session_id"]


class TestP1BackgroundJobs:
    """P1: Verify Background Jobs page shows import jobs from DB"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_01_get_background_jobs(self):
        """P1: Verify GET /api/ai/bulk/background-jobs returns jobs from DB"""
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Background jobs failed: {response.text}"
        
        data = response.json()
        assert "jobs" in data, f"Response missing 'jobs': {data}"
        assert "counts" in data, f"Response missing 'counts': {data}"
        
        counts = data["counts"]
        assert "running" in counts, f"Counts missing 'running': {counts}"
        assert "success" in counts, f"Counts missing 'success': {counts}"
        assert "failed" in counts, f"Counts missing 'failed': {counts}"
        assert "total" in counts, f"Counts missing 'total': {counts}"
        
        print(f"SUCCESS: Background jobs endpoint working - {counts}")
        return data
    
    def test_02_create_import_session_and_verify_in_jobs(self):
        """P1: Create import session and verify it appears in background jobs list"""
        
        # Create a unique session
        unique_name = f"TEST_P1_Job_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Create session
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/import-session/start",
            headers=self.headers,
            json={
                "total_files": 10,
                "folder_name": unique_name,
                "client_id": None
            }
        )
        
        assert response.status_code == 200, f"Create session failed: {response.text}"
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"Created session: {session_id}")
        
        # Step 2: Verify session appears in background jobs
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers=self.headers
        )
        
        assert response.status_code == 200
        jobs_data = response.json()
        
        # Find our session in the jobs list
        found_job = None
        for job in jobs_data["jobs"]:
            if job.get("id") == session_id:
                found_job = job
                break
        
        assert found_job is not None, f"P1 BUG: Session {session_id} not found in background jobs list"
        assert found_job["type"] == "bulk_import", f"Job type mismatch: {found_job}"
        assert found_job["status"] == "running", f"Job status should be 'running': {found_job}"
        assert found_job["total"] == 10, f"Job total should be 10: {found_job}"
        
        print(f"SUCCESS: P1 Bug Fixed - Job found in background jobs: {found_job['id']}")
        
        return session_id
    
    def test_03_update_import_session(self):
        """Test POST /api/ai/bulk/import-session/{id}/update updates progress"""
        
        # Create session first
        create_response = requests.post(
            f"{BASE_URL}/api/ai/bulk/import-session/start",
            headers=self.headers,
            json={
                "total_files": 20,
                "folder_name": f"TEST_Update_{uuid.uuid4().hex[:8]}",
                "client_id": None
            }
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["session_id"]
        
        # Update progress
        update_response = requests.post(
            f"{BASE_URL}/api/ai/bulk/import-session/{session_id}/update",
            headers=self.headers,
            json={
                "processed": 5,
                "errors": 1,
                "error_message": "Test error message"
            }
        )
        
        assert update_response.status_code == 200, f"Update session failed: {update_response.text}"
        
        update_data = update_response.json()
        assert update_data.get("processed") == 5, f"Processed not updated: {update_data}"
        assert update_data.get("errors") == 1, f"Errors not updated: {update_data}"
        assert update_data.get("progress") == 25, f"Progress should be 25%: {update_data}"
        
        print(f"SUCCESS: Session update working - progress: {update_data.get('progress')}%")
        
        return session_id
    
    def test_04_finish_import_session(self):
        """Test POST /api/ai/bulk/import-session/{id}/finish marks job as complete"""
        
        # Create session
        create_response = requests.post(
            f"{BASE_URL}/api/ai/bulk/import-session/start",
            headers=self.headers,
            json={
                "total_files": 5,
                "folder_name": f"TEST_Finish_{uuid.uuid4().hex[:8]}",
                "client_id": None
            }
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["session_id"]
        
        # Finish session with success
        finish_response = requests.post(
            f"{BASE_URL}/api/ai/bulk/import-session/{session_id}/finish?success=true&message=Completed",
            headers=self.headers
        )
        
        assert finish_response.status_code == 200, f"Finish session failed: {finish_response.text}"
        
        finish_data = finish_response.json()
        assert finish_data.get("status") == "success", f"Status not 'success': {finish_data}"
        assert finish_data.get("finished_at") is not None, f"finished_at not set: {finish_data}"
        
        print(f"SUCCESS: Session finish working - status: {finish_data.get('status')}")
        
        return session_id
    
    def test_05_get_single_job(self):
        """Test GET /api/ai/bulk/background-jobs/{job_id} returns single job"""
        
        # Create session
        create_response = requests.post(
            f"{BASE_URL}/api/ai/bulk/import-session/start",
            headers=self.headers,
            json={
                "total_files": 3,
                "folder_name": f"TEST_Single_{uuid.uuid4().hex[:8]}",
                "client_id": None
            }
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["session_id"]
        
        # Get single job
        get_response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{session_id}",
            headers=self.headers
        )
        
        assert get_response.status_code == 200, f"Get single job failed: {get_response.text}"
        
        job_data = get_response.json()
        assert job_data.get("id") == session_id, f"Job ID mismatch: {job_data}"
        assert job_data.get("type") == "bulk_import", f"Job type wrong: {job_data}"
        
        print(f"SUCCESS: Get single job working - {job_data['id']}")
        
        return session_id
    
    def test_06_delete_job(self):
        """Test DELETE /api/ai/bulk/background-jobs/{job_id} removes job"""
        
        # Create session
        create_response = requests.post(
            f"{BASE_URL}/api/ai/bulk/import-session/start",
            headers=self.headers,
            json={
                "total_files": 2,
                "folder_name": f"TEST_Delete_{uuid.uuid4().hex[:8]}",
                "client_id": None
            }
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["session_id"]
        
        # Delete job
        delete_response = requests.delete(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{session_id}",
            headers=self.headers
        )
        
        assert delete_response.status_code == 200, f"Delete job failed: {delete_response.text}"
        
        # Verify job is gone
        get_response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs/{session_id}",
            headers=self.headers
        )
        
        assert get_response.status_code == 404, f"Job should be deleted but found: {get_response.text}"
        
        print(f"SUCCESS: Delete job working - job removed")


class TestCleanup:
    """Cleanup test data created during tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin to get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_cleanup_test_jobs(self):
        """Clean up TEST_ prefixed jobs"""
        # Get all jobs
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs?limit=100",
            headers=self.headers
        )
        
        if response.status_code == 200:
            jobs = response.json().get("jobs", [])
            deleted = 0
            for job in jobs:
                folder_name = job.get("details", {}).get("folder_name", "")
                if folder_name.startswith("TEST_"):
                    delete_resp = requests.delete(
                        f"{BASE_URL}/api/ai/bulk/background-jobs/{job['id']}",
                        headers=self.headers
                    )
                    if delete_resp.status_code == 200:
                        deleted += 1
            
            print(f"Cleanup: Deleted {deleted} test jobs")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
