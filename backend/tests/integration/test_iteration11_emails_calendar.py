"""
====================================================================
TEST ITERATION 11 - EMAILS & CALENDAR USER FILTER
====================================================================
Tests for:
1. Email CRUD endpoints (POST, GET, DELETE)
2. Email stats endpoint
3. Calendar user filter (CEO/Admin visibility)
====================================================================
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin2026"


class TestEmailCRUD:
    """Tests for Email CRUD operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token and process ID"""
        # Login
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get a process ID
        processes_response = requests.get(f"{BASE_URL}/api/processes", headers=self.headers)
        assert processes_response.status_code == 200
        processes = processes_response.json()
        assert len(processes) > 0, "No processes found"
        self.process_id = processes[0]["id"]
        self.client_email = processes[0].get("client_email", "test@example.com")
    
    def test_create_email_sent(self):
        """Test creating a sent email record"""
        email_data = {
            "process_id": self.process_id,
            "direction": "sent",
            "from_email": "admin@sistema.pt",
            "to_emails": [self.client_email],
            "subject": "TEST_Email enviado de teste",
            "body": "Este é um email de teste enviado.",
            "status": "sent"
        }
        
        response = requests.post(f"{BASE_URL}/api/emails", json=email_data, headers=self.headers)
        assert response.status_code == 200, f"Create email failed: {response.text}"
        
        data = response.json()
        assert data["id"] is not None
        assert data["direction"] == "sent"
        assert data["subject"] == "TEST_Email enviado de teste"
        assert data["process_id"] == self.process_id
        assert "created_at" in data
        
        # Store for cleanup
        self.created_email_id = data["id"]
        print(f"PASS: Created sent email with ID: {self.created_email_id}")
    
    def test_create_email_received(self):
        """Test creating a received email record"""
        email_data = {
            "process_id": self.process_id,
            "direction": "received",
            "from_email": self.client_email,
            "to_emails": ["admin@sistema.pt"],
            "subject": "TEST_Email recebido de teste",
            "body": "Este é um email de teste recebido.",
            "status": "sent"
        }
        
        response = requests.post(f"{BASE_URL}/api/emails", json=email_data, headers=self.headers)
        assert response.status_code == 200, f"Create email failed: {response.text}"
        
        data = response.json()
        assert data["direction"] == "received"
        assert data["subject"] == "TEST_Email recebido de teste"
        print(f"PASS: Created received email with ID: {data['id']}")
    
    def test_get_process_emails(self):
        """Test getting emails for a process"""
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{self.process_id}",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get emails failed: {response.text}"
        
        emails = response.json()
        assert isinstance(emails, list)
        print(f"PASS: Retrieved {len(emails)} emails for process")
    
    def test_get_process_emails_filtered_by_direction(self):
        """Test getting emails filtered by direction"""
        # Test sent filter
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{self.process_id}",
            params={"direction": "sent"},
            headers=self.headers
        )
        assert response.status_code == 200
        
        emails = response.json()
        for email in emails:
            assert email["direction"] == "sent", "Filter by direction not working"
        print(f"PASS: Filtered emails by direction (sent): {len(emails)} emails")
    
    def test_get_email_stats(self):
        """Test getting email statistics for a process"""
        response = requests.get(
            f"{BASE_URL}/api/emails/stats/{self.process_id}",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get stats failed: {response.text}"
        
        stats = response.json()
        assert "total" in stats
        assert "sent" in stats
        assert "received" in stats
        assert stats["total"] == stats["sent"] + stats["received"]
        print(f"PASS: Email stats - Total: {stats['total']}, Sent: {stats['sent']}, Received: {stats['received']}")
    
    def test_delete_email(self):
        """Test deleting an email record"""
        # First create an email to delete
        email_data = {
            "process_id": self.process_id,
            "direction": "sent",
            "from_email": "admin@sistema.pt",
            "to_emails": ["test@delete.pt"],
            "subject": "TEST_Email para eliminar",
            "body": "Este email será eliminado.",
            "status": "sent"
        }
        
        create_response = requests.post(f"{BASE_URL}/api/emails", json=email_data, headers=self.headers)
        assert create_response.status_code == 200
        email_id = create_response.json()["id"]
        
        # Delete the email
        delete_response = requests.delete(f"{BASE_URL}/api/emails/{email_id}", headers=self.headers)
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        
        data = delete_response.json()
        assert data["success"] == True
        print(f"PASS: Deleted email {email_id}")
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/emails/{email_id}", headers=self.headers)
        assert get_response.status_code == 404, "Email should not exist after deletion"
        print("PASS: Verified email no longer exists")


class TestCalendarUserFilter:
    """Tests for Calendar user filter functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.user = response.json()["user"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_admin_can_see_all_users(self):
        """Test that admin can see all users for calendar filter"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200, f"Get users failed: {response.text}"
        
        users = response.json()
        assert len(users) > 0, "No users found"
        
        # Check that we have different roles
        roles = set(u["role"] for u in users)
        print(f"PASS: Admin can see users with roles: {roles}")
        assert "admin" in roles or "consultor" in roles or "mediador" in roles
    
    def test_calendar_deadlines_endpoint(self):
        """Test calendar deadlines endpoint"""
        response = requests.get(f"{BASE_URL}/api/deadlines/calendar", headers=self.headers)
        assert response.status_code == 200, f"Get calendar deadlines failed: {response.text}"
        
        deadlines = response.json()
        assert isinstance(deadlines, list)
        print(f"PASS: Retrieved {len(deadlines)} calendar deadlines")
    
    def test_calendar_deadlines_with_user_filter(self):
        """Test calendar deadlines with user filter"""
        # Get a user ID to filter by
        users_response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        users = users_response.json()
        
        # Find a consultor
        consultor = next((u for u in users if u["role"] == "consultor"), None)
        if consultor:
            response = requests.get(
                f"{BASE_URL}/api/deadlines/calendar",
                params={"consultor_id": consultor["id"]},
                headers=self.headers
            )
            assert response.status_code == 200
            print(f"PASS: Calendar filter by consultor works")


class TestTasksRegression:
    """Regression tests for Tasks system"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_tasks(self):
        """Test getting tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=self.headers)
        assert response.status_code == 200, f"Get tasks failed: {response.text}"
        
        tasks = response.json()
        assert isinstance(tasks, list)
        print(f"PASS: Retrieved {len(tasks)} tasks")
    
    def test_get_my_tasks(self):
        """Test getting my tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks/my-tasks", headers=self.headers)
        assert response.status_code == 200, f"Get my tasks failed: {response.text}"
        
        tasks = response.json()
        assert isinstance(tasks, list)
        print(f"PASS: Retrieved {len(tasks)} personal tasks")


class TestCleanup:
    """Cleanup test data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get a process ID
        processes_response = requests.get(f"{BASE_URL}/api/processes", headers=self.headers)
        processes = processes_response.json()
        self.process_id = processes[0]["id"] if processes else None
    
    def test_cleanup_test_emails(self):
        """Clean up TEST_ prefixed emails"""
        if not self.process_id:
            pytest.skip("No process ID available")
        
        # Get all emails for the process
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{self.process_id}",
            headers=self.headers
        )
        
        if response.status_code == 200:
            emails = response.json()
            deleted_count = 0
            for email in emails:
                if email["subject"].startswith("TEST_"):
                    delete_response = requests.delete(
                        f"{BASE_URL}/api/emails/{email['id']}",
                        headers=self.headers
                    )
                    if delete_response.status_code == 200:
                        deleted_count += 1
            
            print(f"PASS: Cleaned up {deleted_count} test emails")
