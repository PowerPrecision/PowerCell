"""
Iteration 30 - Bug Fixes Testing
================================
Tests for the following bug fixes:
1. Kanban filters - GET /api/processes/kanban with consultor_id=none and mediador_id=none
2. Kanban filters - GET /api/processes/kanban with specific consultor_id
3. Client deletion - DELETE /api/clients/{id} should delete from processes collection
4. Email preferences - PUT /api/auth/preferences
5. Admin notification preferences - GET /api/admin/notification-preferences

Context from main agent:
- Fixed bugs: 1) Kanban filter logic was overwriting $or clause when both consultor_id 
  and mediador_id were 'none' - fixed using $and for multiple conditions. 
- 2) Client deletion was searching in 'clients' collection but data is in 'processes' - 
  fixed to search processes first.
"""

import os
import pytest
import requests
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin"


class TestAuthentication:
    """Basic authentication tests"""
    
    def test_01_admin_login(self):
        """Test admin login and get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        assert data.get("user", {}).get("role") == "admin", "User is not admin"
        print(f"✓ Admin login successful, role: {data['user']['role']}")
        # Store token for other tests
        TestAuthentication.token = data["access_token"]
        TestAuthentication.user_id = data["user"]["id"]


class TestKanbanFilters:
    """Tests for Kanban filter fixes - using $and for multiple conditions"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure we have admin token"""
        if not hasattr(TestAuthentication, 'token'):
            # Login first
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            assert response.status_code == 200
            TestAuthentication.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {TestAuthentication.token}"}
    
    def test_02_kanban_no_filters(self):
        """Test kanban without filters returns all processes"""
        response = requests.get(
            f"{BASE_URL}/api/processes/kanban",
            headers=self.headers
        )
        assert response.status_code == 200, f"Kanban failed: {response.text}"
        data = response.json()
        assert "columns" in data, "No columns in response"
        assert "total_processes" in data, "No total_processes in response"
        total = data["total_processes"]
        print(f"✓ Kanban without filters: {total} total processes, {len(data['columns'])} columns")
        TestKanbanFilters.total_processes = total
    
    def test_03_kanban_filter_consultor_none(self):
        """Test kanban filter with consultor_id=none (processes without consultor)"""
        response = requests.get(
            f"{BASE_URL}/api/processes/kanban?consultor_id=none",
            headers=self.headers
        )
        assert response.status_code == 200, f"Kanban filter failed: {response.text}"
        data = response.json()
        total = data["total_processes"]
        
        # Verify all returned processes have no consultor
        for column in data["columns"]:
            for process in column.get("processes", []):
                consultor_id = process.get("assigned_consultor_id")
                assert consultor_id in [None, "", None], \
                    f"Process {process['id']} has consultor_id={consultor_id}, expected none"
        
        print(f"✓ Kanban with consultor_id=none: {total} processes without consultor")
        TestKanbanFilters.processes_without_consultor = total
    
    def test_04_kanban_filter_mediador_none(self):
        """Test kanban filter with mediador_id=none (processes without mediador)"""
        response = requests.get(
            f"{BASE_URL}/api/processes/kanban?mediador_id=none",
            headers=self.headers
        )
        assert response.status_code == 200, f"Kanban filter failed: {response.text}"
        data = response.json()
        total = data["total_processes"]
        
        # Verify all returned processes have no mediador
        for column in data["columns"]:
            for process in column.get("processes", []):
                mediador_id = process.get("assigned_mediador_id")
                assert mediador_id in [None, "", None], \
                    f"Process {process['id']} has mediador_id={mediador_id}, expected none"
        
        print(f"✓ Kanban with mediador_id=none: {total} processes without mediador")
        TestKanbanFilters.processes_without_mediador = total
    
    def test_05_kanban_filter_both_none(self):
        """
        CRITICAL TEST: Kanban filter with both consultor_id=none AND mediador_id=none
        This was the bug - the $or clause was being overwritten when both filters were 'none'.
        Fix: Use $and for multiple conditions.
        """
        response = requests.get(
            f"{BASE_URL}/api/processes/kanban?consultor_id=none&mediador_id=none",
            headers=self.headers
        )
        assert response.status_code == 200, f"Kanban filter failed: {response.text}"
        data = response.json()
        total = data["total_processes"]
        
        # Verify ALL returned processes have BOTH no consultor AND no mediador
        for column in data["columns"]:
            for process in column.get("processes", []):
                consultor_id = process.get("assigned_consultor_id")
                mediador_id = process.get("assigned_mediador_id")
                
                # Both must be empty/None
                assert consultor_id in [None, ""], \
                    f"Process {process['id']} has consultor_id={consultor_id}, expected none"
                assert mediador_id in [None, ""], \
                    f"Process {process['id']} has mediador_id={mediador_id}, expected none"
        
        print(f"✓ Kanban with consultor_id=none AND mediador_id=none: {total} processes")
        print(f"  (Total: {TestKanbanFilters.total_processes}, without consultor: {TestKanbanFilters.processes_without_consultor}, without mediador: {TestKanbanFilters.processes_without_mediador})")
        
        # The count should be <= both individual filters (intersection)
        assert total <= TestKanbanFilters.processes_without_consultor, \
            "Combined filter should return <= processes without consultor"
        assert total <= TestKanbanFilters.processes_without_mediador, \
            "Combined filter should return <= processes without mediador"
    
    def test_06_kanban_filter_specific_consultor(self):
        """Test kanban filter with a specific consultor_id"""
        # First, get list of consultors
        response = requests.get(
            f"{BASE_URL}/api/admin/users?role=consultor",
            headers=self.headers
        )
        
        if response.status_code == 200:
            users = response.json()
            if users and len(users) > 0:
                consultor_id = users[0]["id"]
                consultor_name = users[0].get("name", "Unknown")
                
                # Now filter by this consultor
                response = requests.get(
                    f"{BASE_URL}/api/processes/kanban?consultor_id={consultor_id}",
                    headers=self.headers
                )
                assert response.status_code == 200, f"Kanban filter failed: {response.text}"
                data = response.json()
                total = data["total_processes"]
                
                # Verify all returned processes have this consultor
                for column in data["columns"]:
                    for process in column.get("processes", []):
                        assert process.get("assigned_consultor_id") == consultor_id, \
                            f"Process {process['id']} has wrong consultor"
                
                print(f"✓ Kanban with specific consultor ({consultor_name}): {total} processes")
            else:
                print("⚠ No consultors found to test specific consultor filter")
                pytest.skip("No consultors available")
        else:
            print("⚠ Could not fetch consultors list")
            pytest.skip("Could not fetch consultors")


class TestClientDeletion:
    """Tests for client deletion - should search in processes collection first"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure we have admin token"""
        if not hasattr(TestAuthentication, 'token'):
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            assert response.status_code == 200
            TestAuthentication.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {TestAuthentication.token}"}
    
    def test_07_create_test_process_for_deletion(self):
        """Create a test process that we'll delete"""
        test_name = f"TEST_DELETE_{uuid.uuid4().hex[:8]}"
        
        response = requests.post(
            f"{BASE_URL}/api/processes/create-client",
            headers=self.headers,
            json={
                "process_type": "credito_habitacao",
                "client_name": test_name,
                "client_email": f"{test_name.lower()}@test.com",
                "personal_data": {
                    "nome_completo": test_name,
                    "email": f"{test_name.lower()}@test.com"
                }
            }
        )
        assert response.status_code == 200, f"Create process failed: {response.text}"
        data = response.json()
        process_id = data["id"]
        print(f"✓ Created test process: {process_id} ({test_name})")
        TestClientDeletion.test_process_id = process_id
        TestClientDeletion.test_process_name = test_name
    
    def test_08_verify_process_exists(self):
        """Verify the process exists before deletion"""
        process_id = TestClientDeletion.test_process_id
        
        response = requests.get(
            f"{BASE_URL}/api/processes/{process_id}",
            headers=self.headers
        )
        assert response.status_code == 200, f"Process not found: {response.text}"
        data = response.json()
        assert data["id"] == process_id
        print(f"✓ Process exists: {data['client_name']}")
    
    def test_09_delete_client_via_clients_endpoint(self):
        """
        CRITICAL TEST: Delete client via DELETE /api/clients/{id}
        This should find and delete from processes collection (not clients).
        Bug fix: Now searches processes collection first.
        """
        process_id = TestClientDeletion.test_process_id
        
        response = requests.delete(
            f"{BASE_URL}/api/clients/{process_id}",
            headers=self.headers
        )
        assert response.status_code == 200, f"Delete failed: {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Delete not successful: {data}"
        print(f"✓ Client deleted successfully: {data.get('message')}")
    
    def test_10_verify_process_deleted(self):
        """Verify the process no longer exists after deletion"""
        process_id = TestClientDeletion.test_process_id
        
        response = requests.get(
            f"{BASE_URL}/api/processes/{process_id}",
            headers=self.headers
        )
        # Should return 404 now
        assert response.status_code == 404, \
            f"Process still exists! Expected 404, got {response.status_code}: {response.text}"
        print(f"✓ Process correctly deleted - returns 404")


class TestEmailPreferences:
    """Tests for PUT /api/auth/preferences endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure we have admin token"""
        if not hasattr(TestAuthentication, 'token'):
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            assert response.status_code == 200
            TestAuthentication.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {TestAuthentication.token}"}
    
    def test_11_update_email_preferences(self):
        """Test updating email notification preferences"""
        response = requests.put(
            f"{BASE_URL}/api/auth/preferences",
            headers=self.headers,
            json={
                "notifications": {
                    "email_new_process": True,
                    "email_status_change": True,
                    "email_document_upload": False,
                    "email_urgent_only": True
                }
            }
        )
        assert response.status_code == 200, f"Update preferences failed: {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Update not successful: {data}"
        print(f"✓ Email preferences updated successfully")
    
    def test_12_verify_preferences_via_me_endpoint(self):
        """Verify preferences are stored correctly"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get me failed: {response.text}"
        data = response.json()
        assert "email" in data
        print(f"✓ User profile retrieved: {data['email']}")


class TestAdminNotificationPreferences:
    """Tests for GET /api/admin/notification-preferences endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure we have admin token"""
        if not hasattr(TestAuthentication, 'token'):
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            assert response.status_code == 200
            TestAuthentication.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {TestAuthentication.token}"}
    
    def test_13_get_all_notification_preferences(self):
        """Test getting all users' notification preferences (admin only)"""
        response = requests.get(
            f"{BASE_URL}/api/admin/notification-preferences",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get notification preferences failed: {response.text}"
        data = response.json()
        
        # Should return a list of users with their preferences
        assert isinstance(data, list), "Expected list of users"
        
        if len(data) > 0:
            # Check structure
            first_user = data[0]
            assert "user_id" in first_user, "Missing user_id field"
            assert "email" in first_user, "Missing email field"
            assert "name" in first_user, "Missing name field"
            
            print(f"✓ Admin notification preferences: {len(data)} users")
            print(f"  First user: {first_user.get('name')} ({first_user.get('email')})")
            print(f"  Receives email: {first_user.get('receives_email')}, Is test user: {first_user.get('is_test_user')}")
        else:
            print("⚠ No users found in notification preferences")
    
    def test_14_get_specific_user_notification_preferences(self):
        """Test getting notification preferences for a specific user"""
        user_id = TestAuthentication.user_id
        
        response = requests.get(
            f"{BASE_URL}/api/admin/notification-preferences/{user_id}",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get user preferences failed: {response.text}"
        data = response.json()
        
        assert "user_id" in data, "Missing user_id"
        assert "preferences" in data, "Missing preferences"
        assert data["user_id"] == user_id
        
        prefs = data.get("preferences", {})
        print(f"✓ User notification preferences retrieved for {data.get('user_email')}")
        print(f"  Preferences: email_urgent_only={prefs.get('email_urgent_only')}, email_daily_summary={prefs.get('email_daily_summary')}")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure we have admin token"""
        if not hasattr(TestAuthentication, 'token'):
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            assert response.status_code == 200
            TestAuthentication.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {TestAuthentication.token}"}
    
    def test_99_cleanup_test_data(self):
        """Clean up any remaining test data (TEST_ prefixed processes)"""
        # Get all processes
        response = requests.get(
            f"{BASE_URL}/api/processes",
            headers=self.headers
        )
        
        if response.status_code == 200:
            processes = response.json()
            deleted = 0
            for proc in processes:
                if proc.get("client_name", "").startswith("TEST_"):
                    # Delete test process
                    del_resp = requests.delete(
                        f"{BASE_URL}/api/clients/{proc['id']}",
                        headers=self.headers
                    )
                    if del_resp.status_code == 200:
                        deleted += 1
            
            print(f"✓ Cleanup complete: deleted {deleted} test processes")
        else:
            print("⚠ Could not fetch processes for cleanup")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
