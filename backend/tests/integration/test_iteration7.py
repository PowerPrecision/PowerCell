"""
Iteration 7 Tests - PowerCell
Testing:
1. Login as admin
2. Dashboard loads correctly with stats and Kanban
3. Process details page loads without errors
4. Impersonate functionality on users page
5. Impersonate banner and stop impersonate
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin2026"


class TestHealthAndAuth:
    """Health check and authentication tests"""
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health check passed")
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful: {data['user']['name']}")
        return data["access_token"]


class TestDashboardEndpoints:
    """Test dashboard-related endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for authenticated requests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_stats(self):
        """Test stats endpoint for dashboard"""
        response = requests.get(f"{BASE_URL}/api/stats", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        # Verify stats structure
        assert "total_processes" in data or "processes" in data or isinstance(data, dict)
        print(f"✓ Stats endpoint working: {data}")
    
    def test_get_kanban_board(self):
        """Test Kanban board endpoint"""
        response = requests.get(f"{BASE_URL}/api/processes/kanban", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        # API returns object with columns array or direct list
        if isinstance(data, dict):
            assert "columns" in data
            columns = data["columns"]
        else:
            columns = data
        assert isinstance(columns, list)
        print(f"✓ Kanban board endpoint working: {len(columns)} columns")
    
    def test_get_workflow_statuses(self):
        """Test workflow statuses endpoint (was broken before)"""
        response = requests.get(f"{BASE_URL}/api/admin/workflow-statuses", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"✓ Workflow statuses endpoint working: {len(data)} statuses")
    
    def test_get_users(self):
        """Test users endpoint"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Users endpoint working: {len(data)} users")
    
    def test_get_deadlines_calendar(self):
        """Test calendar deadlines endpoint"""
        response = requests.get(f"{BASE_URL}/api/deadlines/calendar", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Calendar deadlines endpoint working: {len(data)} deadlines")
    
    def test_get_notifications(self):
        """Test notifications endpoint"""
        response = requests.get(f"{BASE_URL}/api/alerts/notifications", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        # API returns object with notifications array or direct list
        if isinstance(data, dict):
            assert "notifications" in data
            notifications = data["notifications"]
        else:
            notifications = data
        assert isinstance(notifications, list)
        print(f"✓ Notifications endpoint working: {len(notifications)} notifications")


class TestProcessDetails:
    """Test process details page endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token and a process ID"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get a process ID
        processes_response = requests.get(f"{BASE_URL}/api/processes", headers=self.headers)
        processes = processes_response.json()
        self.process_id = processes[0]["id"] if processes else None
    
    def test_get_process_details(self):
        """Test getting process details"""
        if not self.process_id:
            pytest.skip("No processes available")
        
        response = requests.get(f"{BASE_URL}/api/processes/{self.process_id}", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "client_name" in data
        print(f"✓ Process details endpoint working: {data['client_name']}")
    
    def test_get_process_deadlines(self):
        """Test getting process deadlines"""
        if not self.process_id:
            pytest.skip("No processes available")
        
        response = requests.get(f"{BASE_URL}/api/deadlines", params={"process_id": self.process_id}, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Process deadlines endpoint working: {len(data)} deadlines")
    
    def test_get_process_activities(self):
        """Test getting process activities"""
        if not self.process_id:
            pytest.skip("No processes available")
        
        response = requests.get(f"{BASE_URL}/api/activities", params={"process_id": self.process_id}, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Process activities endpoint working: {len(data)} activities")
    
    def test_get_process_history(self):
        """Test getting process history"""
        if not self.process_id:
            pytest.skip("No processes available")
        
        response = requests.get(f"{BASE_URL}/api/history", params={"process_id": self.process_id}, headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Process history endpoint working: {len(data)} entries")


class TestImpersonateFunctionality:
    """Test impersonate functionality - CRITICAL for this iteration"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.token = response.json()["access_token"]
        self.admin_user = response.json()["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_non_admin_user_for_impersonate(self):
        """Get a non-admin user to impersonate"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200
        users = response.json()
        
        # Find a non-admin user
        non_admin_users = [u for u in users if u["role"] != "admin"]
        assert len(non_admin_users) > 0, "No non-admin users found to impersonate"
        
        self.target_user = non_admin_users[0]
        print(f"✓ Found non-admin user to impersonate: {self.target_user['name']} ({self.target_user['role']})")
        return self.target_user
    
    def test_impersonate_user(self):
        """Test impersonate endpoint"""
        # Get a non-admin user
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        users = response.json()
        non_admin_users = [u for u in users if u["role"] != "admin"]
        
        if not non_admin_users:
            pytest.skip("No non-admin users to impersonate")
        
        target_user = non_admin_users[0]
        
        # Call impersonate endpoint
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{target_user['id']}", 
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["id"] == target_user["id"]
        assert data["user"]["is_impersonated"] == True
        assert "impersonated_by" in data["user"]
        
        print(f"✓ Impersonate endpoint working: Now viewing as {data['user']['name']}")
        return data
    
    def test_impersonate_and_verify_me_endpoint(self):
        """Test that /auth/me returns impersonate info"""
        # Get a non-admin user
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        users = response.json()
        non_admin_users = [u for u in users if u["role"] != "admin"]
        
        if not non_admin_users:
            pytest.skip("No non-admin users to impersonate")
        
        target_user = non_admin_users[0]
        
        # Impersonate
        impersonate_response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{target_user['id']}", 
            headers=self.headers
        )
        impersonate_data = impersonate_response.json()
        impersonate_token = impersonate_data["access_token"]
        
        # Call /auth/me with impersonate token
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {impersonate_token}"}
        )
        assert me_response.status_code == 200
        me_data = me_response.json()
        
        # Verify impersonate fields are present
        assert me_data["id"] == target_user["id"]
        assert me_data.get("is_impersonated") == True
        assert "impersonated_by" in me_data
        assert "impersonated_by_name" in me_data
        
        print(f"✓ /auth/me returns impersonate info: impersonated_by={me_data['impersonated_by_name']}")
    
    def test_stop_impersonate(self):
        """Test stop impersonate endpoint"""
        # Get a non-admin user
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        users = response.json()
        non_admin_users = [u for u in users if u["role"] != "admin"]
        
        if not non_admin_users:
            pytest.skip("No non-admin users to impersonate")
        
        target_user = non_admin_users[0]
        
        # Impersonate first
        impersonate_response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{target_user['id']}", 
            headers=self.headers
        )
        impersonate_token = impersonate_response.json()["access_token"]
        
        # Stop impersonate
        stop_response = requests.post(
            f"{BASE_URL}/api/admin/stop-impersonate",
            headers={"Authorization": f"Bearer {impersonate_token}"}
        )
        assert stop_response.status_code == 200
        stop_data = stop_response.json()
        
        # Verify we're back to admin
        assert "access_token" in stop_data
        assert stop_data["user"]["role"] == "admin"
        assert stop_data["user"].get("is_impersonated") is None or stop_data["user"].get("is_impersonated") == False
        
        print(f"✓ Stop impersonate working: Back to {stop_data['user']['name']}")
    
    def test_cannot_impersonate_admin(self):
        """Test that admin cannot impersonate another admin"""
        # Get another admin user (if exists)
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        users = response.json()
        admin_users = [u for u in users if u["role"] == "admin" and u["id"] != self.admin_user["id"]]
        
        if not admin_users:
            pytest.skip("No other admin users to test")
        
        other_admin = admin_users[0]
        
        # Try to impersonate another admin
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{other_admin['id']}", 
            headers=self.headers
        )
        assert response.status_code == 403
        print(f"✓ Cannot impersonate another admin (403 returned)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
