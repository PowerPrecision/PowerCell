"""
====================================================================
ITERATION 9 - TASKS SYSTEM TESTS
====================================================================
Tests for the new Tasks feature:
- CRUD operations (create, read, update, delete)
- Task assignment and notifications
- Task completion and reopening
- My tasks endpoint
- Process-specific tasks
====================================================================
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestTasksSystem:
    """Tests for the Tasks CRUD system"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.admin_email = "admin@sistema.pt"
        self.admin_password = "admin2026"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.admin_email,
            "password": self.admin_password
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.user_id = login_response.json().get("user", {}).get("id")
        
        # Get list of users for task assignment
        users_response = self.session.get(f"{BASE_URL}/api/users")
        if users_response.status_code == 200:
            self.users = users_response.json()
        else:
            self.users = []
        
        yield
        
        # Cleanup - delete test tasks
        self._cleanup_test_tasks()
    
    def _cleanup_test_tasks(self):
        """Delete all test tasks created during tests"""
        try:
            tasks_response = self.session.get(f"{BASE_URL}/api/tasks", params={"include_completed": True})
            if tasks_response.status_code == 200:
                tasks = tasks_response.json()
                for task in tasks:
                    if task.get("title", "").startswith("TEST_"):
                        self.session.delete(f"{BASE_URL}/api/tasks/{task['id']}")
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    # ==================== AUTHENTICATION TESTS ====================
    
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
            "email": self.admin_email,
            "password": self.admin_password
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == self.admin_email
        print("✓ Admin login passed")
    
    # ==================== TASKS CRUD TESTS ====================
    
    def test_create_task(self):
        """Test creating a new task"""
        task_data = {
            "title": "TEST_Task_Create_" + str(uuid.uuid4())[:8],
            "description": "Test task description",
            "assigned_to": [self.user_id]
        }
        
        response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert response.status_code == 200, f"Create task failed: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["title"] == task_data["title"]
        assert data["description"] == task_data["description"]
        assert self.user_id in data["assigned_to"]
        assert data["completed"] == False
        assert "created_at" in data
        print(f"✓ Task created: {data['id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{data['id']}")
    
    def test_create_task_with_process(self):
        """Test creating a task associated with a process"""
        # First get a process
        processes_response = self.session.get(f"{BASE_URL}/api/processes")
        if processes_response.status_code != 200 or not processes_response.json():
            pytest.skip("No processes available for testing")
        
        process = processes_response.json()[0]
        process_id = process["id"]
        client_name = process.get("client_name", "Cliente")
        
        task_data = {
            "title": "TEST_Process_Task_" + str(uuid.uuid4())[:8],
            "description": "Task for process",
            "assigned_to": [self.user_id],
            "process_id": process_id
        }
        
        response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert response.status_code == 200, f"Create task failed: {response.text}"
        
        data = response.json()
        assert data["process_id"] == process_id
        # Title should be prefixed with client name
        assert client_name in data["title"] or task_data["title"] in data["title"]
        print(f"✓ Task with process created: {data['id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{data['id']}")
    
    def test_get_tasks_list(self):
        """Test getting list of tasks"""
        # Create a test task first
        task_data = {
            "title": "TEST_List_Task_" + str(uuid.uuid4())[:8],
            "description": "Test task for listing",
            "assigned_to": [self.user_id]
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        
        # Get tasks list
        response = self.session.get(f"{BASE_URL}/api/tasks")
        assert response.status_code == 200
        
        tasks = response.json()
        assert isinstance(tasks, list)
        
        # Find our created task
        found = any(t["id"] == created_task["id"] for t in tasks)
        assert found, "Created task not found in list"
        print(f"✓ Tasks list retrieved: {len(tasks)} tasks")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
    
    def test_get_my_tasks(self):
        """Test getting tasks assigned to current user"""
        # Create a task assigned to current user
        task_data = {
            "title": "TEST_MyTask_" + str(uuid.uuid4())[:8],
            "description": "My task",
            "assigned_to": [self.user_id]
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        
        # Get my tasks
        response = self.session.get(f"{BASE_URL}/api/tasks/my-tasks")
        assert response.status_code == 200
        
        tasks = response.json()
        assert isinstance(tasks, list)
        
        # Our task should be in the list
        found = any(t["id"] == created_task["id"] for t in tasks)
        assert found, "Task not found in my-tasks"
        print(f"✓ My tasks retrieved: {len(tasks)} tasks")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
    
    def test_get_task_by_id(self):
        """Test getting a specific task by ID"""
        # Create a task
        task_data = {
            "title": "TEST_GetById_" + str(uuid.uuid4())[:8],
            "description": "Task to get by ID",
            "assigned_to": [self.user_id]
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        
        # Get task by ID
        response = self.session.get(f"{BASE_URL}/api/tasks/{created_task['id']}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == created_task["id"]
        assert data["title"] == created_task["title"]
        print(f"✓ Task retrieved by ID: {data['id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
    
    def test_complete_task(self):
        """Test marking a task as completed"""
        # Create a task
        task_data = {
            "title": "TEST_Complete_" + str(uuid.uuid4())[:8],
            "description": "Task to complete",
            "assigned_to": [self.user_id]
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        assert created_task["completed"] == False
        
        # Complete the task
        response = self.session.put(f"{BASE_URL}/api/tasks/{created_task['id']}/complete")
        assert response.status_code == 200
        
        data = response.json()
        assert data["completed"] == True
        assert data["completed_at"] is not None
        assert data["completed_by"] == self.user_id
        print(f"✓ Task completed: {data['id']}")
        
        # Verify by getting the task again
        get_response = self.session.get(f"{BASE_URL}/api/tasks/{created_task['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["completed"] == True
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
    
    def test_reopen_task(self):
        """Test reopening a completed task"""
        # Create and complete a task
        task_data = {
            "title": "TEST_Reopen_" + str(uuid.uuid4())[:8],
            "description": "Task to reopen",
            "assigned_to": [self.user_id]
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        
        # Complete the task
        complete_response = self.session.put(f"{BASE_URL}/api/tasks/{created_task['id']}/complete")
        assert complete_response.status_code == 200
        assert complete_response.json()["completed"] == True
        
        # Reopen the task
        response = self.session.put(f"{BASE_URL}/api/tasks/{created_task['id']}/reopen")
        assert response.status_code == 200
        
        data = response.json()
        assert data["completed"] == False
        assert data["completed_at"] is None
        assert data["completed_by"] is None
        print(f"✓ Task reopened: {data['id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
    
    def test_update_task(self):
        """Test updating a task"""
        # Create a task
        task_data = {
            "title": "TEST_Update_" + str(uuid.uuid4())[:8],
            "description": "Original description",
            "assigned_to": [self.user_id]
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        
        # Update the task
        update_data = {
            "title": "TEST_Updated_Title",
            "description": "Updated description"
        }
        response = self.session.put(f"{BASE_URL}/api/tasks/{created_task['id']}", json=update_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["title"] == update_data["title"]
        assert data["description"] == update_data["description"]
        print(f"✓ Task updated: {data['id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
    
    def test_delete_task(self):
        """Test deleting a task"""
        # Create a task
        task_data = {
            "title": "TEST_Delete_" + str(uuid.uuid4())[:8],
            "description": "Task to delete",
            "assigned_to": [self.user_id]
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        
        # Delete the task
        response = self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        print(f"✓ Task deleted: {created_task['id']}")
        
        # Verify task is gone
        get_response = self.session.get(f"{BASE_URL}/api/tasks/{created_task['id']}")
        assert get_response.status_code == 404
    
    def test_get_tasks_with_completed_filter(self):
        """Test filtering tasks by completion status"""
        # Create and complete a task
        task_data = {
            "title": "TEST_Filter_" + str(uuid.uuid4())[:8],
            "description": "Task for filter test",
            "assigned_to": [self.user_id]
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        
        # Complete the task
        self.session.put(f"{BASE_URL}/api/tasks/{created_task['id']}/complete")
        
        # Get tasks without completed (default)
        response_no_completed = self.session.get(f"{BASE_URL}/api/tasks")
        assert response_no_completed.status_code == 200
        tasks_no_completed = response_no_completed.json()
        
        # Get tasks with completed
        response_with_completed = self.session.get(f"{BASE_URL}/api/tasks", params={"include_completed": True})
        assert response_with_completed.status_code == 200
        tasks_with_completed = response_with_completed.json()
        
        # Completed task should only appear in include_completed=True
        found_in_no_completed = any(t["id"] == created_task["id"] for t in tasks_no_completed)
        found_in_with_completed = any(t["id"] == created_task["id"] for t in tasks_with_completed)
        
        assert not found_in_no_completed, "Completed task should not appear without include_completed"
        assert found_in_with_completed, "Completed task should appear with include_completed=True"
        print("✓ Task completion filter works correctly")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
    
    def test_get_process_tasks(self):
        """Test getting tasks for a specific process"""
        # Get a process
        processes_response = self.session.get(f"{BASE_URL}/api/processes")
        if processes_response.status_code != 200 or not processes_response.json():
            pytest.skip("No processes available for testing")
        
        process = processes_response.json()[0]
        process_id = process["id"]
        
        # Create a task for this process
        task_data = {
            "title": "TEST_ProcessTask_" + str(uuid.uuid4())[:8],
            "description": "Task for specific process",
            "assigned_to": [self.user_id],
            "process_id": process_id
        }
        create_response = self.session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert create_response.status_code == 200
        created_task = create_response.json()
        
        # Get tasks for this process
        response = self.session.get(f"{BASE_URL}/api/tasks", params={"process_id": process_id})
        assert response.status_code == 200
        
        tasks = response.json()
        assert isinstance(tasks, list)
        
        # Our task should be in the list
        found = any(t["id"] == created_task["id"] for t in tasks)
        assert found, "Task not found in process tasks"
        print(f"✓ Process tasks retrieved: {len(tasks)} tasks for process {process_id[:8]}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/tasks/{created_task['id']}")
    
    def test_task_requires_authentication(self):
        """Test that task endpoints require authentication"""
        # Create a new session without auth
        no_auth_session = requests.Session()
        no_auth_session.headers.update({"Content-Type": "application/json"})
        
        # Try to get tasks without auth
        response = no_auth_session.get(f"{BASE_URL}/api/tasks")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        
        # Try to create task without auth
        response = no_auth_session.post(f"{BASE_URL}/api/tasks", json={
            "title": "Unauthorized task",
            "assigned_to": ["some-id"]
        })
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✓ Task endpoints require authentication")
    
    def test_task_not_found(self):
        """Test 404 for non-existent task"""
        fake_id = str(uuid.uuid4())
        response = self.session.get(f"{BASE_URL}/api/tasks/{fake_id}")
        assert response.status_code == 404
        print("✓ 404 returned for non-existent task")


class TestCalendarEndpoints:
    """Tests for Calendar/Deadlines endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.admin_email = "admin@sistema.pt"
        self.admin_password = "admin2026"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.admin_email,
            "password": self.admin_password
        })
        assert login_response.status_code == 200
        
        token = login_response.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        yield
    
    def test_get_calendar_deadlines(self):
        """Test getting calendar deadlines"""
        response = self.session.get(f"{BASE_URL}/api/deadlines/calendar")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Calendar deadlines retrieved: {len(data)} events")
    
    def test_create_calendar_event(self):
        """Test creating a calendar event"""
        event_data = {
            "title": "TEST_Event_" + str(uuid.uuid4())[:8],
            "description": "Test calendar event",
            "due_date": "2026-02-15",
            "priority": "medium",
            "participants": []
        }
        
        response = self.session.post(f"{BASE_URL}/api/deadlines", json=event_data)
        assert response.status_code == 200, f"Create event failed: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["title"] == event_data["title"]
        print(f"✓ Calendar event created: {data['id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/deadlines/{data['id']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
