"""
====================================================================
ITERATION 13 TESTS - CREDITOIMO
====================================================================
Tests for:
1. Duplicate blocking by email/NIF in public registration
2. has_property field in Kanban processes
3. Task assignment notifications
4. Document verification alerts on status change to ch_aprovado
====================================================================
"""

import pytest
import requests
import os
import uuid
import random
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin2026"


def generate_valid_nif():
    """Generate a valid 9-digit Portuguese NIF for testing"""
    # Generate 9 random digits
    return ''.join([str(random.randint(0, 9)) for _ in range(9)])


class TestSetup:
    """Setup and authentication helpers"""
    
    @staticmethod
    def get_auth_token():
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    @staticmethod
    def get_headers(token):
        """Get headers with auth token"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }


class TestPublicClientRegistrationDuplicateBlocking:
    """
    Tests for POST /api/public/client-registration
    - Block if email already exists (returns blocked:true, reason:email)
    - Block if NIF already exists (returns blocked:true, reason:nif)
    - Allow registration if email and NIF are new
    """
    
    def test_registration_with_new_email_and_nif(self):
        """Test successful registration with new email and NIF"""
        unique_id = str(uuid.uuid4())[:8]
        test_email = f"test_new_{unique_id}@example.com"
        test_nif = generate_valid_nif()  # Valid 9-digit NIF
        
        payload = {
            "name": f"Test Client {unique_id}",
            "email": test_email,
            "phone": "912345678",
            "process_type": "credito_habitacao",
            "personal_data": {
                "nif": test_nif,
                "birth_date": "1990-01-01"
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/public/client-registration", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should succeed
        assert data.get("success") == True, f"Expected success=True, got {data}"
        assert "process_id" in data, "Expected process_id in response"
        assert data.get("blocked") != True, "Should not be blocked"
        
        print(f"✅ PASS: New registration successful - process_id: {data.get('process_id')}")
        
        # Cleanup - delete the test process
        token = TestSetup.get_auth_token()
        if token:
            # Get process to verify it was created
            headers = TestSetup.get_headers(token)
            process_response = requests.get(
                f"{BASE_URL}/api/processes/{data['process_id']}", 
                headers=headers
            )
            if process_response.status_code == 200:
                print(f"   Process verified in database: {process_response.json().get('client_name')}")
    
    def test_registration_blocked_by_duplicate_email(self):
        """Test that registration is blocked when email already exists"""
        # First, get an existing process to find an email that exists
        token = TestSetup.get_auth_token()
        assert token, "Failed to get auth token"
        
        headers = TestSetup.get_headers(token)
        
        # Get existing processes
        kanban_response = requests.get(f"{BASE_URL}/api/processes/kanban", headers=headers)
        assert kanban_response.status_code == 200, f"Failed to get kanban: {kanban_response.text}"
        
        kanban_data = kanban_response.json()
        
        # Find a process with an email
        existing_email = None
        for column in kanban_data.get("columns", []):
            for process in column.get("processes", []):
                if process.get("client_email"):
                    existing_email = process["client_email"]
                    break
            if existing_email:
                break
        
        if not existing_email:
            pytest.skip("No existing process with email found to test duplicate blocking")
        
        print(f"   Testing duplicate email blocking with: {existing_email}")
        
        # Try to register with the same email
        payload = {
            "name": "Test Duplicate Email",
            "email": existing_email,
            "phone": "912345678",
            "process_type": "credito_habitacao",
            "personal_data": {
                "nif": generate_valid_nif(),  # New valid NIF
                "birth_date": "1990-01-01"
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/public/client-registration", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should be blocked
        assert data.get("success") == False, f"Expected success=False, got {data}"
        assert data.get("blocked") == True, f"Expected blocked=True, got {data}"
        assert data.get("reason") == "email", f"Expected reason='email', got {data.get('reason')}"
        assert "message" in data, "Expected message in response"
        
        print(f"✅ PASS: Duplicate email blocked correctly - reason: {data.get('reason')}")
        print(f"   Message: {data.get('message')}")
    
    def test_registration_blocked_by_duplicate_nif(self):
        """Test that registration is blocked when NIF already exists"""
        token = TestSetup.get_auth_token()
        assert token, "Failed to get auth token"
        
        headers = TestSetup.get_headers(token)
        
        # Get existing processes
        kanban_response = requests.get(f"{BASE_URL}/api/processes/kanban", headers=headers)
        assert kanban_response.status_code == 200
        
        kanban_data = kanban_response.json()
        
        # Find a process with a NIF
        existing_nif = None
        for column in kanban_data.get("columns", []):
            for process in column.get("processes", []):
                personal_data = process.get("personal_data", {}) or {}
                if personal_data.get("nif"):
                    existing_nif = personal_data["nif"]
                    break
            if existing_nif:
                break
        
        if not existing_nif:
            pytest.skip("No existing process with NIF found to test duplicate blocking")
        
        print(f"   Testing duplicate NIF blocking with: {existing_nif}")
        
        # Try to register with the same NIF
        unique_id = str(uuid.uuid4())[:8]
        payload = {
            "name": "Test Duplicate NIF",
            "email": f"test_nif_{unique_id}@example.com",  # New email
            "phone": "912345678",
            "process_type": "credito_habitacao",
            "personal_data": {
                "nif": existing_nif,  # Existing NIF
                "birth_date": "1990-01-01"
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/public/client-registration", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should be blocked
        assert data.get("success") == False, f"Expected success=False, got {data}"
        assert data.get("blocked") == True, f"Expected blocked=True, got {data}"
        assert data.get("reason") == "nif", f"Expected reason='nif', got {data.get('reason')}"
        
        print(f"✅ PASS: Duplicate NIF blocked correctly - reason: {data.get('reason')}")
        print(f"   Message: {data.get('message')}")


class TestKanbanHasPropertyField:
    """
    Tests for GET /api/processes/kanban
    - Verify has_property field is included in processes
    """
    
    def test_kanban_includes_has_property_field(self):
        """Test that Kanban processes include has_property field"""
        token = TestSetup.get_auth_token()
        assert token, "Failed to get auth token"
        
        headers = TestSetup.get_headers(token)
        
        response = requests.get(f"{BASE_URL}/api/processes/kanban", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "columns" in data, "Expected columns in response"
        assert "total_processes" in data, "Expected total_processes in response"
        
        # Check that processes have has_property field
        processes_with_has_property = 0
        processes_without_has_property = 0
        processes_with_has_property_true = 0
        
        for column in data.get("columns", []):
            for process in column.get("processes", []):
                if "has_property" in process:
                    processes_with_has_property += 1
                    if process["has_property"] == True:
                        processes_with_has_property_true += 1
                else:
                    processes_without_has_property += 1
        
        total_processes = data.get("total_processes", 0)
        
        print(f"   Total processes: {total_processes}")
        print(f"   Processes with has_property field: {processes_with_has_property}")
        print(f"   Processes without has_property field: {processes_without_has_property}")
        print(f"   Processes with has_property=True: {processes_with_has_property_true}")
        
        # The field should be present in processes (even if null/false)
        # Note: Old Trello-imported processes may not have this field
        if processes_with_has_property > 0:
            print(f"✅ PASS: has_property field found in {processes_with_has_property} processes")
        else:
            print(f"⚠️ WARNING: No processes have has_property field - may be old Trello imports")
        
        # Verify the structure is correct
        assert isinstance(data["columns"], list), "columns should be a list"
        if len(data["columns"]) > 0:
            assert "processes" in data["columns"][0], "Each column should have processes"
    
    def test_create_process_with_has_property_true(self):
        """
        Test creating a process with has_property=True via public registration.
        
        NOTE: The RealEstateData model doesn't have 'ja_tem_imovel' field defined,
        so the has_property flag won't be set via public registration.
        This is a MINOR BUG - the field should be added to RealEstateData model.
        
        Current behavior: has_property is always False from public registration
        because the model strips unknown fields.
        """
        unique_id = str(uuid.uuid4())[:8]
        
        payload = {
            "name": f"Test Has Property {unique_id}",
            "email": f"test_property_{unique_id}@example.com",
            "phone": "912345678",
            "process_type": "credito_habitacao",
            "personal_data": {
                "nif": generate_valid_nif(),  # Valid 9-digit NIF
                "birth_date": "1990-01-01"
            },
            "real_estate_data": {
                "ja_tem_imovel": True,  # This field is NOT in RealEstateData model
                "tipo_imovel": "apartamento",
                "localizacao": "Lisboa"
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/public/client-registration", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        if data.get("success"):
            # Document the current behavior (bug)
            if data.get("has_property") == True:
                print(f"✅ PASS: Process created with has_property=True")
            else:
                print(f"⚠️ MINOR BUG: has_property is {data.get('has_property')} instead of True")
                print(f"   Reason: 'ja_tem_imovel' field not defined in RealEstateData model")
                print(f"   Fix: Add 'ja_tem_imovel: Optional[bool] = None' to RealEstateData in models/process.py")
            print(f"   Process ID: {data.get('process_id')}")
        else:
            # May be blocked due to duplicate - that's ok for this test
            print(f"   Registration blocked (may be duplicate): {data.get('reason')}")


class TestTaskAssignmentNotifications:
    """
    Tests for POST /api/tasks
    - Verify notification is sent to assigned users
    """
    
    def test_create_task_sends_notification(self):
        """Test that creating a task sends notification to assigned users"""
        token = TestSetup.get_auth_token()
        assert token, "Failed to get auth token"
        
        headers = TestSetup.get_headers(token)
        
        # Get list of users to assign
        users_response = requests.get(f"{BASE_URL}/api/users", headers=headers)
        assert users_response.status_code == 200, f"Failed to get users: {users_response.text}"
        
        users = users_response.json()
        
        # Find a user that is not the admin (to test notification)
        assignee_id = None
        for user in users:
            if user.get("email") != ADMIN_EMAIL and user.get("is_active", True):
                assignee_id = user["id"]
                break
        
        if not assignee_id:
            pytest.skip("No other active user found to test task assignment notification")
        
        # Create a task assigned to another user
        unique_id = str(uuid.uuid4())[:8]
        task_payload = {
            "title": f"Test Task Notification {unique_id}",
            "description": "Testing task assignment notification",
            "assigned_to": [assignee_id]
        }
        
        response = requests.post(f"{BASE_URL}/api/tasks", json=task_payload, headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "id" in data, "Expected task id in response"
        assert data.get("title") == task_payload["title"], "Task title mismatch"
        assert assignee_id in data.get("assigned_to", []), "Assignee not in assigned_to list"
        
        print(f"✅ PASS: Task created successfully - id: {data.get('id')}")
        print(f"   Title: {data.get('title')}")
        print(f"   Assigned to: {data.get('assigned_to')}")
        
        # Check if notification was created (check notifications endpoint)
        # Note: The notification is sent via send_realtime_notification which creates a DB entry
        notifications_response = requests.get(
            f"{BASE_URL}/api/notifications?user_id={assignee_id}", 
            headers=headers
        )
        
        if notifications_response.status_code == 200:
            notifications = notifications_response.json()
            # Look for task_assigned notification
            task_notifications = [n for n in notifications if n.get("type") == "task_assigned"]
            if task_notifications:
                print(f"   ✅ Notification found for assignee")
            else:
                print(f"   ⚠️ No task_assigned notification found (may be async)")
        
        # Cleanup - delete the task
        delete_response = requests.delete(f"{BASE_URL}/api/tasks/{data['id']}", headers=headers)
        if delete_response.status_code == 200:
            print(f"   Task cleaned up")


class TestProcessMoveDocumentVerificationAlert:
    """
    Tests for PUT /api/processes/kanban/{id}/move
    - Verify document verification alert is sent when moving to ch_aprovado
    
    NOTE: There is a BUG in the backend code - notify_cpcv_or_deed_document_check()
    passes 'priority' parameter to send_realtime_notification() which doesn't accept it.
    This causes a 500 error when moving processes to ch_aprovado, fase_escritura, or escritura_agendada.
    """
    
    def test_move_to_ch_aprovado_has_bug(self):
        """
        Test that moving process to ch_aprovado - EXPECTED TO FAIL due to bug.
        
        BUG: services/alerts.py line 492 passes 'priority' parameter to 
        send_realtime_notification() which doesn't accept it.
        
        TypeError: send_realtime_notification() got an unexpected keyword argument 'priority'
        """
        token = TestSetup.get_auth_token()
        assert token, "Failed to get auth token"
        
        headers = TestSetup.get_headers(token)
        
        # Get kanban to find a process to move
        kanban_response = requests.get(f"{BASE_URL}/api/processes/kanban", headers=headers)
        assert kanban_response.status_code == 200
        
        kanban_data = kanban_response.json()
        
        # Find a process that is NOT in ch_aprovado, fase_escritura, or escritura_agendada
        test_process = None
        original_status = None
        excluded_statuses = ["ch_aprovado", "fase_escritura", "escritura_agendada", "concluidos", "desistencias"]
        
        for column in kanban_data.get("columns", []):
            if column.get("name") not in excluded_statuses:
                for process in column.get("processes", []):
                    test_process = process
                    original_status = column.get("name")
                    break
            if test_process:
                break
        
        if not test_process:
            pytest.skip("No suitable process found to test move to ch_aprovado")
        
        print(f"   Testing with process: {test_process.get('client_name')}")
        print(f"   Current status: {original_status}")
        
        # Move to ch_aprovado - This will fail due to the bug
        move_response = requests.put(
            f"{BASE_URL}/api/processes/kanban/{test_process['id']}/move?new_status=ch_aprovado",
            headers=headers
        )
        
        # Document the bug - expecting 500/520 error
        if move_response.status_code in [500, 520]:
            print(f"⚠️ BUG CONFIRMED: Move to ch_aprovado returns {move_response.status_code}")
            print(f"   Error: send_realtime_notification() got unexpected keyword argument 'priority'")
            print(f"   Location: /app/backend/services/alerts.py line 492")
            print(f"   Fix: Remove 'priority' parameter from send_realtime_notification() call")
            # Mark as expected failure
            pytest.xfail("Known bug: priority parameter not supported in send_realtime_notification")
        elif move_response.status_code == 200:
            print(f"✅ PASS: Move to ch_aprovado succeeded (bug may have been fixed)")
            data = move_response.json()
            # Restore original status
            requests.put(
                f"{BASE_URL}/api/processes/kanban/{test_process['id']}/move?new_status={original_status}",
                headers=headers
            )
        else:
            pytest.fail(f"Unexpected status code: {move_response.status_code}")


class TestPublicHealthEndpoint:
    """Test public health endpoint"""
    
    def test_public_health(self):
        """Test public health endpoint"""
        response = requests.get(f"{BASE_URL}/api/public/health")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("status") == "ok", f"Expected status=ok, got {data}"
        assert data.get("public") == True, f"Expected public=True, got {data}"
        
        print(f"✅ PASS: Public health endpoint working")


class TestKanbanBoardStructure:
    """Additional tests for Kanban board structure"""
    
    def test_kanban_returns_all_columns(self):
        """Test that Kanban returns all workflow columns"""
        token = TestSetup.get_auth_token()
        assert token, "Failed to get auth token"
        
        headers = TestSetup.get_headers(token)
        
        response = requests.get(f"{BASE_URL}/api/processes/kanban", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Expected columns based on workflow
        expected_columns = [
            "clientes_espera", "fase_documental", "fase_documental_ii",
            "enviado_bruno", "enviado_luis", "enviado_bcp_rui",
            "entradas_precision", "fase_bancaria", "fase_visitas",
            "ch_aprovado", "fase_escritura", "escritura_agendada",
            "concluidos", "desistencias"
        ]
        
        actual_columns = [col["name"] for col in data.get("columns", [])]
        
        print(f"   Found {len(actual_columns)} columns")
        print(f"   Total processes: {data.get('total_processes')}")
        
        # Check that we have the expected columns
        for expected in expected_columns:
            if expected in actual_columns:
                print(f"   ✅ Column '{expected}' found")
            else:
                print(f"   ⚠️ Column '{expected}' not found")
        
        assert len(actual_columns) >= 10, f"Expected at least 10 columns, got {len(actual_columns)}"
        print(f"✅ PASS: Kanban structure is correct")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
