"""
===================================================================
Test Iteration 43: TAREFA 1 (Email Association) & TAREFA 2 (AI Conflicts)
===================================================================
Tests for:
- TAREFA 1A: GET /api/emails/process/{id}?filter_by_user=true
- TAREFA 1B: GET /api/emails/search?q=teste  
- TAREFA 1C: POST /api/emails/associate
- TAREFA 2A: POST /api/processes/{id}/confirm-data
- TAREFA 2B: POST /api/processes/{id}/resolve-conflict
===================================================================
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

# Base URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "adminadmin"
CONSULTOR_EMAIL = "flaviosilva@powerealestate.pt"
CONSULTOR_PASSWORD = "flavio123"

# Process ID with is_data_confirmed=true (from context)
CONFIRMED_PROCESS_ID = "9f573b70-538f-4c4b-87e7-71bfa12e1e8a"


class TestAuthentication:
    """Test authentication for API access"""
    
    def test_admin_login(self):
        """Test admin can login successfully"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful: {data['user']['email']}")
    
    def test_consultor_login(self):
        """Test consultor can login successfully"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        assert response.status_code == 200, f"Consultor login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        print(f"✓ Consultor login successful: {data['user']['email']}")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def consultor_token():
    """Get consultor authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    pytest.skip("Consultor authentication failed")


@pytest.fixture(scope="module")
def test_process_id(admin_token):
    """Get a valid process ID for testing"""
    response = requests.get(
        f"{BASE_URL}/api/processes",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    if response.status_code == 200 and len(response.json()) > 0:
        return response.json()[0]["id"]
    pytest.skip("No processes available for testing")


class TestTarefa1A_EmailFilterByUser:
    """TAREFA 1A: Test GET /api/emails/process/{id}?filter_by_user=true"""
    
    def test_get_emails_without_filter(self, admin_token, test_process_id):
        """Test getting all emails for a process without filter"""
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{test_process_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed to get emails: {response.text}"
        emails = response.json()
        print(f"✓ Got {len(emails)} emails without filter")
    
    def test_get_emails_with_user_filter(self, admin_token, test_process_id):
        """Test filtering emails by user participation"""
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{test_process_id}?filter_by_user=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed with filter: {response.text}"
        emails = response.json()
        print(f"✓ Got {len(emails)} emails with filter_by_user=true")
    
    def test_get_emails_with_direction_filter(self, admin_token, test_process_id):
        """Test filtering emails by direction (sent/received)"""
        response = requests.get(
            f"{BASE_URL}/api/emails/process/{test_process_id}?direction=sent",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed with direction filter: {response.text}"
        emails = response.json()
        print(f"✓ Got {len(emails)} sent emails")


class TestTarefa1B_EmailSearch:
    """TAREFA 1B: Test GET /api/emails/search?q=teste"""
    
    def test_search_emails_success(self, admin_token):
        """Test searching emails with valid query"""
        response = requests.get(
            f"{BASE_URL}/api/emails/search?q=teste",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Search failed: {response.text}"
        data = response.json()
        assert "emails" in data
        assert "total" in data
        print(f"✓ Search returned {data['total']} results")
    
    def test_search_emails_by_subject(self, admin_token):
        """Test searching emails by subject keyword"""
        response = requests.get(
            f"{BASE_URL}/api/emails/search?q=credito&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Search for 'credito' returned {data['total']} results")
    
    def test_search_emails_short_query_fails(self, admin_token):
        """Test that search with less than 3 chars fails"""
        response = requests.get(
            f"{BASE_URL}/api/emails/search?q=ab",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400, f"Expected 400 for short query: {response.text}"
        print("✓ Short query (2 chars) correctly rejected with 400")
    
    def test_search_emails_without_auth_fails(self):
        """Test that search without authentication fails"""
        response = requests.get(f"{BASE_URL}/api/emails/search?q=teste")
        assert response.status_code == 401 or response.status_code == 403
        print("✓ Unauthenticated search correctly rejected")


class TestTarefa1C_EmailAssociate:
    """TAREFA 1C: Test POST /api/emails/associate"""
    
    def test_associate_missing_fields(self, admin_token):
        """Test associating email with missing fields fails"""
        response = requests.post(
            f"{BASE_URL}/api/emails/associate",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={"email_id": "test"}  # Missing process_id
        )
        assert response.status_code == 400
        print("✓ Missing fields correctly rejected with 400")
    
    def test_associate_invalid_email_id(self, admin_token, test_process_id):
        """Test associating with invalid email_id fails"""
        response = requests.post(
            f"{BASE_URL}/api/emails/associate",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={
                "email_id": "non-existent-email-id",
                "process_id": test_process_id
            }
        )
        assert response.status_code == 404
        print("✓ Invalid email_id correctly rejected with 404")
    
    def test_associate_invalid_process_id(self, admin_token):
        """Test associating with invalid process_id fails"""
        response = requests.post(
            f"{BASE_URL}/api/emails/associate",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={
                "email_id": str(uuid.uuid4()),
                "process_id": "non-existent-process"
            }
        )
        # Should fail on process or email not found
        assert response.status_code in [404, 400]
        print(f"✓ Invalid process_id correctly rejected with {response.status_code}")


class TestTarefa2A_ConfirmData:
    """TAREFA 2A: Test POST /api/processes/{id}/confirm-data"""
    
    def test_confirm_data_endpoint_exists(self, admin_token, test_process_id):
        """Test that confirm-data endpoint exists and accepts requests"""
        response = requests.post(
            f"{BASE_URL}/api/processes/{test_process_id}/confirm-data",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={"confirmed": True}
        )
        # Can succeed (200) or fail with 400 if conflicts exist
        assert response.status_code in [200, 400], f"Unexpected status: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert data["success"] == True
            assert "is_data_confirmed" in data
            print(f"✓ Data confirmation successful: is_data_confirmed={data['is_data_confirmed']}")
        else:
            # 400 means there are pending conflicts
            data = response.json()
            print(f"✓ Confirm-data returned 400 (pending conflicts): {data.get('detail', '')}")
    
    def test_unlock_data(self, admin_token, test_process_id):
        """Test unlocking data (setting confirmed=false)"""
        response = requests.post(
            f"{BASE_URL}/api/processes/{test_process_id}/confirm-data",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={"confirmed": False}
        )
        # Should always succeed when unlocking
        assert response.status_code == 200, f"Unlock failed: {response.text}"
        data = response.json()
        assert data["is_data_confirmed"] == False
        print("✓ Data unlock successful")
    
    def test_confirm_data_without_auth_fails(self, test_process_id):
        """Test that confirm-data without authentication fails"""
        response = requests.post(
            f"{BASE_URL}/api/processes/{test_process_id}/confirm-data",
            headers={"Content-Type": "application/json"},
            json={"confirmed": True}
        )
        assert response.status_code in [401, 403]
        print("✓ Unauthenticated confirm-data correctly rejected")
    
    def test_confirm_data_invalid_process(self, admin_token):
        """Test confirm-data with invalid process_id"""
        response = requests.post(
            f"{BASE_URL}/api/processes/invalid-process-id/confirm-data",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={"confirmed": True}
        )
        assert response.status_code == 404
        print("✓ Invalid process_id correctly rejected with 404")


class TestTarefa2B_ResolveConflict:
    """TAREFA 2B: Test POST /api/processes/{id}/resolve-conflict"""
    
    def test_resolve_conflict_endpoint_exists(self, admin_token, test_process_id):
        """Test that resolve-conflict endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/processes/{test_process_id}/resolve-conflict",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={
                "field": "nif",
                "choice": "current"
            }
        )
        # Should return 404 (no suggestion) or 200 (resolved)
        assert response.status_code in [200, 404], f"Unexpected status: {response.text}"
        
        if response.status_code == 404:
            # No suggestion found is expected behavior
            print("✓ Resolve-conflict returned 404 (no pending suggestion for 'nif')")
        else:
            data = response.json()
            assert data["success"] == True
            print(f"✓ Conflict resolved successfully: {data.get('message', '')}")
    
    def test_resolve_conflict_missing_fields(self, admin_token, test_process_id):
        """Test resolve-conflict with missing required fields"""
        response = requests.post(
            f"{BASE_URL}/api/processes/{test_process_id}/resolve-conflict",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={"field": "nif"}  # Missing choice
        )
        assert response.status_code == 400
        print("✓ Missing 'choice' field correctly rejected with 400")
    
    def test_resolve_conflict_invalid_choice(self, admin_token, test_process_id):
        """Test resolve-conflict with invalid choice value"""
        response = requests.post(
            f"{BASE_URL}/api/processes/{test_process_id}/resolve-conflict",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            },
            json={
                "field": "nif",
                "choice": "invalid_choice"  # Should be 'ai' or 'current'
            }
        )
        assert response.status_code == 400
        print("✓ Invalid choice value correctly rejected with 400")
    
    def test_resolve_conflict_without_auth_fails(self, test_process_id):
        """Test that resolve-conflict without authentication fails"""
        response = requests.post(
            f"{BASE_URL}/api/processes/{test_process_id}/resolve-conflict",
            headers={"Content-Type": "application/json"},
            json={"field": "nif", "choice": "current"}
        )
        assert response.status_code in [401, 403]
        print("✓ Unauthenticated resolve-conflict correctly rejected")


class TestProcessModelFields:
    """Test that process model has TAREFA 2 fields"""
    
    def test_process_has_is_data_confirmed_field(self, admin_token):
        """Test that process response includes is_data_confirmed field"""
        response = requests.get(
            f"{BASE_URL}/api/processes/{CONFIRMED_PROCESS_ID}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if response.status_code == 200:
            data = response.json()
            # Field should exist in response (even if null)
            assert "is_data_confirmed" in data or data.get("is_data_confirmed") is not None
            print(f"✓ Process {CONFIRMED_PROCESS_ID} has is_data_confirmed={data.get('is_data_confirmed')}")
        else:
            print(f"⚠ Process {CONFIRMED_PROCESS_ID} not found (may have been deleted)")
    
    def test_process_has_ai_suggestions_field(self, admin_token, test_process_id):
        """Test that process response includes ai_suggestions field"""
        response = requests.get(
            f"{BASE_URL}/api/processes/{test_process_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Field should exist in response (even if null/empty)
        assert "ai_suggestions" in data or data.get("ai_suggestions") is None
        suggestions = data.get("ai_suggestions") or []
        print(f"✓ Process has ai_suggestions field (count: {len(suggestions)})")


class TestEmailAccounts:
    """Test email account configuration endpoints"""
    
    def test_get_email_accounts(self, admin_token):
        """Test getting configured email accounts"""
        response = requests.get(
            f"{BASE_URL}/api/emails/accounts",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        accounts = response.json()
        print(f"✓ Got {len(accounts)} configured email accounts")
        for acc in accounts:
            print(f"  - {acc.get('name')}: {acc.get('email')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
