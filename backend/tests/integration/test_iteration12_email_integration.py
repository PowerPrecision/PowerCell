"""
====================================================================
TEST ITERATION 12 - EMAIL INTEGRATION (IMAP/SMTP)
====================================================================
Tests for:
1. Email connection test endpoint (both accounts: precision, power)
2. Email accounts listing endpoint
3. Email sync endpoint for process
4. Email panel filters (Todos, Enviados, Recebidos)
5. Manual email creation
6. Regression: Calendar with user filter
7. Regression: Tasks system
====================================================================
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin2026"


class TestEmailConnection:
    """Tests for Email IMAP/SMTP connection"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_email_connection_all_accounts(self):
        """Test GET /api/emails/test-connection - both accounts should return imap:true, smtp:true"""
        response = requests.get(f"{BASE_URL}/api/emails/test-connection", headers=self.headers)
        assert response.status_code == 200, f"Test connection failed: {response.text}"
        
        data = response.json()
        
        # Check Precision account
        assert "precision" in data, "Precision account not found in response"
        assert data["precision"]["imap"] == True, f"Precision IMAP failed: {data['precision'].get('error')}"
        assert data["precision"]["smtp"] == True, f"Precision SMTP failed: {data['precision'].get('error')}"
        print(f"PASS: Precision account - IMAP: {data['precision']['imap']}, SMTP: {data['precision']['smtp']}")
        
        # Check Power account
        assert "power" in data, "Power account not found in response"
        assert data["power"]["imap"] == True, f"Power IMAP failed: {data['power'].get('error')}"
        assert data["power"]["smtp"] == True, f"Power SMTP failed: {data['power'].get('error')}"
        print(f"PASS: Power account - IMAP: {data['power']['imap']}, SMTP: {data['power']['smtp']}")
    
    def test_email_connection_precision_only(self):
        """Test connection for Precision account only"""
        response = requests.get(
            f"{BASE_URL}/api/emails/test-connection",
            params={"account": "precision"},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "precision" in data
        assert data["precision"]["imap"] == True
        assert data["precision"]["smtp"] == True
        print("PASS: Precision account connection test passed")
    
    def test_email_connection_power_only(self):
        """Test connection for Power account only"""
        response = requests.get(
            f"{BASE_URL}/api/emails/test-connection",
            params={"account": "power"},
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "power" in data
        assert data["power"]["imap"] == True
        assert data["power"]["smtp"] == True
        print("PASS: Power account connection test passed")


class TestEmailAccounts:
    """Tests for Email accounts listing"""
    
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
    
    def test_get_email_accounts(self):
        """Test GET /api/emails/accounts - should list precision and power"""
        response = requests.get(f"{BASE_URL}/api/emails/accounts", headers=self.headers)
        assert response.status_code == 200, f"Get accounts failed: {response.text}"
        
        accounts = response.json()
        assert isinstance(accounts, list), "Response should be a list"
        assert len(accounts) >= 2, f"Expected at least 2 accounts, got {len(accounts)}"
        
        # Check account names
        account_names = [a["name"] for a in accounts]
        assert "precision" in account_names, "Precision account not found"
        assert "power" in account_names, "Power account not found"
        
        # Check Precision details
        precision = next(a for a in accounts if a["name"] == "precision")
        assert precision["email"] == "geral@precisioncredito.pt"
        assert "imap_server" in precision
        assert "smtp_server" in precision
        print(f"PASS: Precision account - {precision['email']}")
        
        # Check Power details
        power = next(a for a in accounts if a["name"] == "power")
        assert power["email"] == "geral@powerealestate.pt"
        assert "imap_server" in power
        assert "smtp_server" in power
        print(f"PASS: Power account - {power['email']}")


class TestEmailSync:
    """Tests for Email sync functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token and process ID"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get a process ID
        processes_response = requests.get(f"{BASE_URL}/api/processes", headers=self.headers)
        assert processes_response.status_code == 200
        processes = processes_response.json()
        assert len(processes) > 0, "No processes found"
        self.process_id = processes[0]["id"]
        self.client_email = processes[0].get("client_email", "")
    
    def test_sync_emails_for_process(self):
        """Test POST /api/emails/sync/{process_id} - sync emails for client"""
        response = requests.post(
            f"{BASE_URL}/api/emails/sync/{self.process_id}",
            params={"days": 60},
            headers=self.headers
        )
        assert response.status_code == 200, f"Sync failed: {response.text}"
        
        data = response.json()
        assert data["success"] == True, f"Sync not successful: {data.get('error')}"
        assert "total_found" in data
        assert "new_imported" in data
        assert data["process_id"] == self.process_id
        print(f"PASS: Sync completed - Found: {data['total_found']}, Imported: {data['new_imported']}")
    
    def test_sync_emails_invalid_process(self):
        """Test sync with invalid process ID"""
        response = requests.post(
            f"{BASE_URL}/api/emails/sync/invalid-process-id",
            params={"days": 30},
            headers=self.headers
        )
        assert response.status_code == 200  # Returns success:false, not 404
        data = response.json()
        assert data["success"] == False
        assert "error" in data
        print(f"PASS: Invalid process handled correctly - {data['error']}")


class TestEmailFilters:
    """Tests for Email filtering (Todos, Enviados, Recebidos)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token and process ID"""
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
        self.process_id = processes[0]["id"]
        self.client_email = processes[0].get("client_email", "test@example.com")
        
        # Create test emails for filtering
        self._create_test_emails()
    
    def _create_test_emails(self):
        """Create test emails for filter testing"""
        # Create sent email
        sent_email = {
            "process_id": self.process_id,
            "direction": "sent",
            "from_email": "admin@sistema.pt",
            "to_emails": [self.client_email],
            "subject": "TEST_FILTER_Email enviado",
            "body": "Email de teste enviado.",
            "status": "sent"
        }
        requests.post(f"{BASE_URL}/api/emails", json=sent_email, headers=self.headers)
        
        # Create received email
        received_email = {
            "process_id": self.process_id,
            "direction": "received",
            "from_email": self.client_email,
            "to_emails": ["admin@sistema.pt"],
            "subject": "TEST_FILTER_Email recebido",
            "body": "Email de teste recebido.",
            "status": "sent"
        }
        requests.post(f"{BASE_URL}/api/emails", json=received_email, headers=self.headers)
    
    def test_filter_all_emails(self):
        """Test getting all emails (no filter)"""
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{self.process_id}",
            headers=self.headers
        )
        assert response.status_code == 200
        emails = response.json()
        assert isinstance(emails, list)
        print(f"PASS: All emails filter - {len(emails)} emails")
    
    def test_filter_sent_emails(self):
        """Test filtering by sent direction"""
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{self.process_id}",
            params={"direction": "sent"},
            headers=self.headers
        )
        assert response.status_code == 200
        emails = response.json()
        
        for email in emails:
            assert email["direction"] == "sent", f"Expected sent, got {email['direction']}"
        print(f"PASS: Sent filter - {len(emails)} sent emails")
    
    def test_filter_received_emails(self):
        """Test filtering by received direction"""
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{self.process_id}",
            params={"direction": "received"},
            headers=self.headers
        )
        assert response.status_code == 200
        emails = response.json()
        
        for email in emails:
            assert email["direction"] == "received", f"Expected received, got {email['direction']}"
        print(f"PASS: Received filter - {len(emails)} received emails")
    
    def test_email_stats(self):
        """Test email statistics endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/emails/stats/{self.process_id}",
            headers=self.headers
        )
        assert response.status_code == 200
        stats = response.json()
        
        assert "total" in stats
        assert "sent" in stats
        assert "received" in stats
        assert stats["total"] == stats["sent"] + stats["received"]
        print(f"PASS: Email stats - Total: {stats['total']}, Sent: {stats['sent']}, Received: {stats['received']}")


class TestManualEmailCreation:
    """Tests for manual email creation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token and process ID"""
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
        self.process_id = processes[0]["id"]
        self.client_email = processes[0].get("client_email", "test@example.com")
    
    def test_create_manual_sent_email(self):
        """Test creating a manual sent email record"""
        email_data = {
            "process_id": self.process_id,
            "direction": "sent",
            "from_email": "geral@precisioncredito.pt",
            "to_emails": [self.client_email],
            "subject": "TEST_MANUAL_Email enviado manualmente",
            "body": "Este é um email registado manualmente.",
            "notes": "Nota de teste",
            "status": "sent"
        }
        
        response = requests.post(f"{BASE_URL}/api/emails", json=email_data, headers=self.headers)
        assert response.status_code == 200, f"Create email failed: {response.text}"
        
        data = response.json()
        assert data["id"] is not None
        assert data["direction"] == "sent"
        assert data["subject"] == "TEST_MANUAL_Email enviado manualmente"
        assert data["notes"] == "Nota de teste"
        print(f"PASS: Created manual sent email - ID: {data['id']}")
    
    def test_create_manual_received_email(self):
        """Test creating a manual received email record"""
        email_data = {
            "process_id": self.process_id,
            "direction": "received",
            "from_email": self.client_email,
            "to_emails": ["geral@precisioncredito.pt"],
            "subject": "TEST_MANUAL_Email recebido manualmente",
            "body": "Este é um email recebido registado manualmente.",
            "status": "sent"
        }
        
        response = requests.post(f"{BASE_URL}/api/emails", json=email_data, headers=self.headers)
        assert response.status_code == 200, f"Create email failed: {response.text}"
        
        data = response.json()
        assert data["direction"] == "received"
        print(f"PASS: Created manual received email - ID: {data['id']}")


class TestCalendarRegression:
    """Regression tests for Calendar with user filter"""
    
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
    
    def test_calendar_deadlines_endpoint(self):
        """Test calendar deadlines endpoint works"""
        response = requests.get(f"{BASE_URL}/api/deadlines/calendar", headers=self.headers)
        assert response.status_code == 200, f"Calendar deadlines failed: {response.text}"
        
        deadlines = response.json()
        assert isinstance(deadlines, list)
        print(f"PASS: Calendar deadlines - {len(deadlines)} events")
    
    def test_calendar_with_user_filter(self):
        """Test calendar with user filter"""
        # Get users
        users_response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert users_response.status_code == 200
        users = users_response.json()
        
        # Find a consultor to filter by
        consultor = next((u for u in users if u["role"] == "consultor"), None)
        if consultor:
            response = requests.get(
                f"{BASE_URL}/api/deadlines/calendar",
                params={"consultor_id": consultor["id"]},
                headers=self.headers
            )
            assert response.status_code == 200
            print(f"PASS: Calendar filter by user works")
        else:
            print("SKIP: No consultor found for filter test")
    
    def test_admin_can_see_all_users(self):
        """Test admin can see all users for calendar filter dropdown"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200
        
        users = response.json()
        assert len(users) > 0
        
        roles = set(u["role"] for u in users)
        print(f"PASS: Admin sees users with roles: {roles}")


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
        """Test getting all tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=self.headers)
        assert response.status_code == 200, f"Get tasks failed: {response.text}"
        
        tasks = response.json()
        assert isinstance(tasks, list)
        print(f"PASS: Tasks endpoint - {len(tasks)} tasks")
    
    def test_get_my_tasks(self):
        """Test getting my tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks/my-tasks", headers=self.headers)
        assert response.status_code == 200, f"Get my tasks failed: {response.text}"
        
        tasks = response.json()
        assert isinstance(tasks, list)
        print(f"PASS: My tasks endpoint - {len(tasks)} tasks")
    
    def test_create_and_complete_task(self):
        """Test creating and completing a task"""
        # Get a process
        processes_response = requests.get(f"{BASE_URL}/api/processes", headers=self.headers)
        processes = processes_response.json()
        process_id = processes[0]["id"] if processes else None
        
        if not process_id:
            pytest.skip("No process available")
        
        # Get current user ID for assigned_to
        me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=self.headers)
        user_id = me_response.json()["id"] if me_response.status_code == 200 else None
        
        if not user_id:
            pytest.skip("Could not get user ID")
        
        # Create task
        task_data = {
            "title": "TEST_REGRESSION_Tarefa de teste",
            "description": "Tarefa criada para teste de regressão",
            "process_id": process_id,
            "priority": "medium",
            "assigned_to": [user_id]
        }
        
        create_response = requests.post(f"{BASE_URL}/api/tasks", json=task_data, headers=self.headers)
        assert create_response.status_code == 200, f"Create task failed: {create_response.text}"
        
        task_id = create_response.json()["id"]
        print(f"PASS: Created task - ID: {task_id}")
        
        # Complete task
        complete_response = requests.put(f"{BASE_URL}/api/tasks/{task_id}/complete", headers=self.headers)
        assert complete_response.status_code == 200
        print("PASS: Task completed")
        
        # Delete task (cleanup)
        delete_response = requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=self.headers)
        assert delete_response.status_code == 200
        print("PASS: Task deleted (cleanup)")


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
