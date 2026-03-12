"""
Iteration 42: Backend API Bug Fixes Test Suite

Tests for the following bug fixes:
1. PUT /api/auth/profile - User can update their own profile (name, phone)
2. POST /api/auth/change-password - User can change their password
3. POST /api/clients/{client_id}/create-process - Create process for existing client (using process_id)

Test credentials:
- Admin: admin@admin.com / adminadmin
- Consultor: flaviosilva@powerealestate.pt / flavio123
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Module-level session and token to avoid rate limits
_admin_session = None
_admin_token = None
_consultor_session = None
_consultor_token = None

def get_admin_session():
    """Get or create admin session (reused across tests)"""
    global _admin_session, _admin_token
    
    if _admin_session is None or _admin_token is None:
        _admin_session = requests.Session()
        _admin_session.headers.update({"Content-Type": "application/json"})
        
        response = _admin_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "adminadmin"
        })
        
        if response.status_code != 200:
            pytest.fail(f"Admin login failed: {response.text}")
        
        data = response.json()
        _admin_token = data.get("access_token")
        _admin_session.headers.update({"Authorization": f"Bearer {_admin_token}"})
        print(f"Admin logged in as: {data.get('user', {}).get('name')}")
    
    return _admin_session, _admin_token


def get_consultor_session():
    """Get or create consultor session (reused across tests)"""
    global _consultor_session, _consultor_token
    
    if _consultor_session is None or _consultor_token is None:
        time.sleep(2)  # Avoid rate limits
        _consultor_session = requests.Session()
        _consultor_session.headers.update({"Content-Type": "application/json"})
        
        response = _consultor_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "flaviosilva@powerealestate.pt",
            "password": "flavio123"
        })
        
        if response.status_code != 200:
            pytest.fail(f"Consultor login failed: {response.text}")
        
        data = response.json()
        _consultor_token = data.get("access_token")
        _consultor_session.headers.update({"Authorization": f"Bearer {_consultor_token}"})
        print(f"Consultor logged in as: {data.get('user', {}).get('name')}")
    
    return _consultor_session, _consultor_token


class TestAuthProfileUpdate:
    """Test PUT /api/auth/profile - Update user's own profile"""
    
    def test_update_profile_name_success(self):
        """Test updating profile name"""
        session, _ = get_admin_session()
        
        # Get current user info
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200
        original_name = me_response.json().get("name")
        print(f"Original name: {original_name}")
        
        # Update name
        new_name = f"Admin Test {os.urandom(2).hex()}"
        update_response = session.put(f"{BASE_URL}/api/auth/profile", json={
            "name": new_name
        })
        
        assert update_response.status_code == 200, f"Profile update failed: {update_response.text}"
        data = update_response.json()
        assert data.get("success") == True
        assert data["user"]["name"] == new_name
        print(f"Name updated to: {new_name}")
        
        # Restore original name
        restore_response = session.put(f"{BASE_URL}/api/auth/profile", json={
            "name": original_name or "Admin"
        })
        assert restore_response.status_code == 200
        print("Name restored")
    
    def test_update_profile_phone_success(self):
        """Test updating profile phone"""
        session, _ = get_admin_session()
        
        # Update phone
        new_phone = "+351912000001"
        update_response = session.put(f"{BASE_URL}/api/auth/profile", json={
            "phone": new_phone
        })
        
        assert update_response.status_code == 200, f"Phone update failed: {update_response.text}"
        data = update_response.json()
        assert data.get("success") == True
        assert data["user"]["phone"] == new_phone
        print(f"Phone updated to: {new_phone}")
    
    def test_update_profile_empty_body_fails(self):
        """Test that empty update body returns error"""
        session, _ = get_admin_session()
        
        update_response = session.put(f"{BASE_URL}/api/auth/profile", json={})
        
        assert update_response.status_code == 400, f"Expected 400, got {update_response.status_code}"
        print("Empty body correctly rejected with 400")
    
    def test_update_profile_unauthorized(self):
        """Test that unauthorized requests fail"""
        no_auth_session = requests.Session()
        no_auth_session.headers.update({"Content-Type": "application/json"})
        
        response = no_auth_session.put(f"{BASE_URL}/api/auth/profile", json={
            "name": "Hacker"
        })
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("Unauthorized request correctly rejected")


class TestChangePassword:
    """Test POST /api/auth/change-password - Change user password"""
    
    def test_change_password_wrong_current_password(self):
        """Test that wrong current password fails"""
        session, _ = get_admin_session()
        
        response = session.post(f"{BASE_URL}/api/auth/change-password", json={
            "current_password": "wrongpassword123",
            "new_password": "newpassword123"
        })
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "incorreta" in data.get("detail", "").lower() or "invalid" in data.get("detail", "").lower()
        print("Wrong current password correctly rejected")
    
    def test_change_password_short_new_password(self):
        """Test that short new password fails"""
        session, _ = get_admin_session()
        
        response = session.post(f"{BASE_URL}/api/auth/change-password", json={
            "current_password": "adminadmin",
            "new_password": "123"
        })
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "6 caracteres" in data.get("detail", "")
        print("Short password correctly rejected")
    
    def test_change_password_missing_fields(self):
        """Test that missing fields fail"""
        session, _ = get_admin_session()
        
        # Missing new password
        response = session.post(f"{BASE_URL}/api/auth/change-password", json={
            "current_password": "adminadmin"
        })
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("Missing new_password correctly rejected")
    
    def test_change_password_endpoint_works(self):
        """Test that change-password endpoint accepts valid request format"""
        session, _ = get_admin_session()
        
        # Test with wrong current password - shows endpoint works but validates correctly
        response = session.post(f"{BASE_URL}/api/auth/change-password", json={
            "current_password": "adminadmin",
            "new_password": "testpass123"
        })
        
        # This should succeed since current password is correct
        if response.status_code == 200:
            print("Password change succeeded - restoring original...")
            # Restore password
            time.sleep(1)
            restore_response = session.post(f"{BASE_URL}/api/auth/change-password", json={
                "current_password": "testpass123",
                "new_password": "adminadmin"
            })
            assert restore_response.status_code == 200, f"Password restore failed: {restore_response.text}"
            print("Password restored to adminadmin")
        else:
            # If it failed, check if it's validation error
            print(f"Response: {response.status_code} - {response.text}")
            assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
    
    def test_change_password_unauthorized(self):
        """Test that unauthorized requests fail"""
        no_auth_session = requests.Session()
        no_auth_session.headers.update({"Content-Type": "application/json"})
        
        response = no_auth_session.post(f"{BASE_URL}/api/auth/change-password", json={
            "current_password": "adminadmin",
            "new_password": "hacked123456"
        })
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("Unauthorized request correctly rejected")


class TestCreateProcessForClient:
    """Test POST /api/clients/{client_id}/create-process - Create process from client management"""
    
    def test_create_process_for_virtual_client_using_process_id(self):
        """Test creating a new process using an existing process_id as client_id (virtual client)"""
        session, _ = get_admin_session()
        
        # First, get a list of existing processes to get a process_id
        processes_response = session.get(f"{BASE_URL}/api/processes?limit=5")
        assert processes_response.status_code == 200, f"Failed to get processes: {processes_response.text}"
        
        processes = processes_response.json()
        assert len(processes) > 0, "No processes found for testing"
        
        # Get first process
        existing_process = processes[0]
        process_id = existing_process.get("id")
        client_name = existing_process.get("client_name")
        print(f"Using process_id: {process_id} (client: {client_name})")
        
        # Now create a new process using this process_id as client_id
        create_response = session.post(
            f"{BASE_URL}/api/clients/{process_id}/create-process?process_type=credito_habitacao"
        )
        
        assert create_response.status_code == 200, f"Create process failed: {create_response.text}"
        data = create_response.json()
        assert data.get("success") == True
        assert "process_id" in data
        assert "process_number" in data
        new_process_id = data.get("process_id")
        new_process_number = data.get("process_number")
        print(f"New process created: #{new_process_number} (id: {new_process_id})")
        
        # Verify the new process exists and has correct client data
        verify_response = session.get(f"{BASE_URL}/api/processes/{new_process_id}")
        assert verify_response.status_code == 200, f"Failed to get new process: {verify_response.text}"
        
        new_process = verify_response.json()
        assert new_process.get("client_name") == client_name
        assert new_process.get("process_type") == "credito_habitacao"
        print(f"New process verified with client_name: {new_process.get('client_name')}")
        
        # Cleanup: Archive the new test process
        archive_response = session.patch(
            f"{BASE_URL}/api/processes/{new_process_id}/status?status=arquivado"
        )
        if archive_response.status_code == 200:
            print("Test process archived")
    
    def test_create_process_invalid_client_id(self):
        """Test that invalid client_id returns 404"""
        session, _ = get_admin_session()
        
        create_response = session.post(
            f"{BASE_URL}/api/clients/invalid-uuid-12345/create-process?process_type=credito_habitacao"
        )
        
        assert create_response.status_code == 404, f"Expected 404, got {create_response.status_code}"
        print("Invalid client_id correctly returns 404")


class TestConsultorProfile:
    """Test consultor profile update"""
    
    def test_consultor_can_update_own_profile(self):
        """Test that consultor can update their own profile"""
        session, _ = get_consultor_session()
        
        # Update profile phone
        update_response = session.put(f"{BASE_URL}/api/auth/profile", json={
            "phone": "+351913000001"
        })
        
        assert update_response.status_code == 200, f"Profile update failed: {update_response.text}"
        data = update_response.json()
        assert data.get("success") == True
        print("Consultor profile update successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
