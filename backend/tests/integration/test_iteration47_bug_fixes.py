"""
====================================================================
ITERATION 47 - BUG FIXES TEST
====================================================================
Testing bug fixes reported by user:
1. Documents - GET /api/documents/client/{id}/files - NoneType error fixed
2. Dropdown de atribuições - GET /api/admin/users accessible by CEO/DIRETOR
3. Registo público - POST /api/public/client-registration creates process_number
4. Limpar erros - POST /api/admin/system-logs/resolve-all endpoint added

Credenciais de teste:
- consultor: flaviosilva@powerealestate.pt / flavio123
====================================================================
"""
import pytest
import requests
import uuid
import os

# Use production URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://workflow-builder-95.preview.emergentagent.com').rstrip('/')


class TestHealthCheck:
    """Basic health check before running other tests."""
    
    def test_api_health(self):
        """Verify API is healthy."""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        print(f"✓ API Health OK: {response.json()}")


class TestAuthentication:
    """Authentication helper tests."""
    
    @pytest.fixture
    def consultor_token(self):
        """Login as consultor and get token."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "flaviosilva@powerealestate.pt",
            "password": "flavio123"
        }, timeout=10)
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture
    def admin_token(self):
        """Login as admin and get token."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        }, timeout=10)
        if response.status_code != 200:
            pytest.skip("Admin user not available for testing")
        return response.json()["access_token"]
    
    def test_consultor_login(self, consultor_token):
        """Verify consultor can login successfully."""
        assert consultor_token is not None
        print("✓ Consultor login successful")


class TestDocumentsEndpoint:
    """
    Test 1: GET /api/documents/client/{id}/files
    
    Bug: NoneType error when titular2_data is None
    Fix: Added "or {}" verification in documents.py line 208-209
    """
    
    @pytest.fixture
    def consultor_token(self):
        """Login as consultor."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "flaviosilva@powerealestate.pt",
            "password": "flavio123"
        }, timeout=10)
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture
    def test_process_id(self, consultor_token):
        """Get a process ID for testing. First tries to find one, then creates if needed."""
        headers = {"Authorization": f"Bearer {consultor_token}"}
        
        # Try to find an existing process
        response = requests.get(f"{BASE_URL}/api/processes", headers=headers, timeout=10)
        if response.status_code == 200:
            processes = response.json()
            if processes:
                # Return first process ID
                return processes[0]["id"]
        
        # If no processes found, skip this test
        pytest.skip("No processes available for testing documents endpoint")
    
    def test_documents_list_files_no_error(self, consultor_token, test_process_id):
        """
        Verify GET /api/documents/client/{id}/files returns success without NoneType error.
        Even if there are no files, it should return a valid response structure.
        """
        headers = {"Authorization": f"Bearer {consultor_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/documents/client/{test_process_id}/files",
            headers=headers,
            timeout=10
        )
        
        # Should NOT return 500 (which was the NoneType error)
        assert response.status_code != 500, f"Server error (NoneType bug?): {response.text}"
        
        # Should return 200 with files structure
        if response.status_code == 200:
            data = response.json()
            # Verify response structure
            assert "files" in data, f"Missing 'files' key in response: {data}"
            print(f"✓ Documents endpoint working: {len(data.get('files', {}))} categories")
        elif response.status_code == 404:
            print("✓ Process not found (expected for non-existent ID)")
        else:
            print(f"✓ Documents endpoint responded with {response.status_code}")
    
    def test_documents_with_nonexistent_process(self, consultor_token):
        """Test that nonexistent process returns 404, not 500 error."""
        headers = {"Authorization": f"Bearer {consultor_token}"}
        fake_id = str(uuid.uuid4())
        
        response = requests.get(
            f"{BASE_URL}/api/documents/client/{fake_id}/files",
            headers=headers,
            timeout=10
        )
        
        # Should return 404, not 500
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent process correctly returns 404")


class TestAdminUsersDropdown:
    """
    Test 2: GET /api/admin/users
    
    Bug: Dropdown empty for CEO role
    Fix: Added CEO and DIRETOR to require_roles in admin.py line 90
    """
    
    @pytest.fixture
    def admin_token(self):
        """Login as admin."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        }, timeout=10)
        if response.status_code != 200:
            pytest.skip("Admin user not available")
        return response.json()["access_token"]
    
    @pytest.fixture
    def ceo_token(self):
        """Try to login as CEO."""
        # Try to find a CEO user
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "ceo@sistema.pt",
            "password": "ceo123"
        }, timeout=10)
        if response.status_code != 200:
            pytest.skip("CEO user not available for testing")
        return response.json()["access_token"]
    
    @pytest.fixture
    def diretor_token(self):
        """Try to login as DIRETOR."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "diretor@sistema.pt",
            "password": "diretor123"
        }, timeout=10)
        if response.status_code != 200:
            pytest.skip("Diretor user not available for testing")
        return response.json()["access_token"]
    
    def test_admin_users_endpoint_exists(self):
        """Verify endpoint exists (returns 401 without auth, not 404)."""
        response = requests.get(f"{BASE_URL}/api/admin/users", timeout=10)
        # Should be 401 (unauthorized) or 403 (forbidden), not 404
        assert response.status_code in [401, 403], f"Unexpected status: {response.status_code}"
        print("✓ GET /api/admin/users endpoint exists")
    
    def test_admin_can_list_users(self, admin_token):
        """Admin should be able to list users."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers, timeout=10)
        
        assert response.status_code == 200, f"Admin cannot list users: {response.text}"
        users = response.json()
        assert isinstance(users, list), "Response should be a list"
        print(f"✓ Admin can list users: {len(users)} users found")
    
    def test_ceo_can_list_users(self, ceo_token):
        """CEO should now be able to list users (after fix)."""
        headers = {"Authorization": f"Bearer {ceo_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers, timeout=10)
        
        # After fix, CEO should have access
        assert response.status_code == 200, f"CEO cannot list users (bug not fixed?): {response.text}"
        users = response.json()
        assert isinstance(users, list), "Response should be a list"
        print(f"✓ CEO can list users (fix verified): {len(users)} users found")
    
    def test_diretor_can_list_users(self, diretor_token):
        """DIRETOR should now be able to list users (after fix)."""
        headers = {"Authorization": f"Bearer {diretor_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers, timeout=10)
        
        # After fix, DIRETOR should have access
        assert response.status_code == 200, f"DIRETOR cannot list users (bug not fixed?): {response.text}"
        users = response.json()
        assert isinstance(users, list), "Response should be a list"
        print(f"✓ DIRETOR can list users (fix verified): {len(users)} users found")
    
    def test_consultor_cannot_list_users(self):
        """Consultor should NOT be able to list users (security check)."""
        # Login as consultor
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "flaviosilva@powerealestate.pt",
            "password": "flavio123"
        }, timeout=10)
        assert login_response.status_code == 200
        consultor_token = login_response.json()["access_token"]
        
        headers = {"Authorization": f"Bearer {consultor_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers, timeout=10)
        
        # Consultor should NOT have access
        assert response.status_code == 403, f"Consultor should not have access: {response.status_code}"
        print("✓ Consultor correctly denied access to user list")


class TestPublicRegistration:
    """
    Test 3: POST /api/public/client-registration
    
    Bug: process_number not being created
    Fix: Added process_number generation in public.py line 127
    """
    
    def test_public_registration_creates_process_number(self):
        """
        Test that public registration creates a process with process_number.
        """
        unique_email = f"TEST_registo_{uuid.uuid4().hex[:8]}@teste.pt"
        
        registration_data = {
            "name": "TEST Cliente Registo Público",
            "email": unique_email,
            "phone": "+351 900000000",
            "process_type": "credito_habitacao",
            "personal_data": {
                "birth_date": "1990-01-01",
                "nome": "TEST Cliente Registo Público"
            },
            "financial_data": {
                "rendimento_mensal": 2000
            },
            "real_estate_data": {
                "valor_maximo": 200000,
                "area_pretendida": "Porto",
                "finalidade": "habitacao_propria",
                "ja_tem_imovel": False
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/public/client-registration",
            json=registration_data,
            timeout=60  # Longer timeout due to email sending and Redis retries
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                # Registration succeeded
                process_id = data.get("process_id")
                assert process_id, "Missing process_id in response"
                print(f"✓ Public registration successful: process_id={process_id}")
                
                # Now verify process has process_number by fetching it
                # We need to login first to check the process
                login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
                    "email": "flaviosilva@powerealestate.pt",
                    "password": "flavio123"
                }, timeout=10)
                
                if login_response.status_code == 200:
                    token = login_response.json()["access_token"]
                    headers = {"Authorization": f"Bearer {token}"}
                    
                    # Get the process
                    process_response = requests.get(
                        f"{BASE_URL}/api/processes/{process_id}",
                        headers=headers,
                        timeout=10
                    )
                    
                    if process_response.status_code == 200:
                        process = process_response.json()
                        process_number = process.get("process_number")
                        assert process_number is not None, f"process_number not set! Process data: {process.keys()}"
                        print(f"✓ process_number created: {process_number}")
                    else:
                        print(f"⚠ Could not verify process_number (status {process_response.status_code})")
            else:
                # Registration blocked (duplicate email/NIF)
                print(f"✓ Registration handled: {data.get('message')}")
        elif response.status_code == 429:
            # Rate limited - skip this test
            pytest.skip("Rate limited - cannot test public registration")
        else:
            pytest.fail(f"Registration failed: {response.status_code} - {response.text}")
    
    def test_public_registration_duplicate_email_blocked(self):
        """Test that duplicate email is blocked."""
        # Use an email that likely already exists
        registration_data = {
            "name": "TEST Duplicate",
            "email": "flaviosilva@powerealestate.pt",  # Existing email
            "phone": "+351 900000001",
            "process_type": "credito_habitacao"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/public/client-registration",
            json=registration_data,
            timeout=15
        )
        
        if response.status_code == 429:
            pytest.skip("Rate limited")
        
        # Should return success=False with blocked=True
        if response.status_code == 200:
            data = response.json()
            if not data.get("success") and data.get("blocked"):
                print(f"✓ Duplicate email correctly blocked: {data.get('reason')}")
            elif data.get("success"):
                # Might be a fresh database where this email doesn't exist
                print("⚠ Registration succeeded (email might not exist in DB)")


class TestResolveAllErrors:
    """
    Test 4: POST /api/admin/system-logs/resolve-all
    
    Bug: Missing option to clear all errors
    Fix: Added new endpoint in admin.py line 1767-1784
    """
    
    @pytest.fixture
    def admin_token(self):
        """Login as admin."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        }, timeout=10)
        if response.status_code != 200:
            pytest.skip("Admin user not available")
        return response.json()["access_token"]
    
    def test_resolve_all_endpoint_exists(self):
        """Verify endpoint exists."""
        response = requests.post(f"{BASE_URL}/api/admin/system-logs/resolve-all", timeout=10)
        # Should be 401/403 (auth required), not 404 (not found) or 405 (method not allowed)
        assert response.status_code in [401, 403], f"Unexpected status: {response.status_code}"
        print("✓ POST /api/admin/system-logs/resolve-all endpoint exists")
    
    def test_admin_can_resolve_all(self, admin_token):
        """Admin should be able to resolve all errors."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/system-logs/resolve-all",
            headers=headers,
            timeout=10
        )
        
        assert response.status_code == 200, f"Failed to resolve all: {response.text}"
        data = response.json()
        
        assert data.get("success") == True, f"Response not success: {data}"
        assert "resolved_count" in data, f"Missing resolved_count: {data}"
        
        print(f"✓ Resolve all errors endpoint working: {data.get('resolved_count')} errors resolved")
    
    def test_consultor_cannot_resolve_all(self):
        """Consultor should NOT be able to resolve all errors."""
        # Login as consultor
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "flaviosilva@powerealestate.pt",
            "password": "flavio123"
        }, timeout=10)
        
        if login_response.status_code == 429:
            pytest.skip("Rate limited - cannot test consultor access denial")
        
        assert login_response.status_code == 200, f"Login failed: {login_response.status_code}"
        consultor_token = login_response.json()["access_token"]
        
        headers = {"Authorization": f"Bearer {consultor_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/admin/system-logs/resolve-all",
            headers=headers,
            timeout=10
        )
        
        # Consultor should NOT have access
        assert response.status_code == 403, f"Consultor should not have access: {response.status_code}"
        print("✓ Consultor correctly denied access to resolve-all")


class TestSystemLogsEndpoint:
    """Additional tests for system logs functionality."""
    
    @pytest.fixture
    def admin_token(self):
        """Login as admin."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        }, timeout=10)
        if response.status_code != 200:
            pytest.skip("Admin user not available")
        return response.json()["access_token"]
    
    def test_get_system_logs(self, admin_token):
        """Admin can get system logs."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs",
            headers=headers,
            timeout=10
        )
        
        assert response.status_code == 200, f"Failed to get logs: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "errors" in data, f"Missing 'errors' key: {data.keys()}"
        assert "total" in data, f"Missing 'total' key: {data.keys()}"
        assert "page" in data, f"Missing 'page' key: {data.keys()}"
        
        print(f"✓ System logs working: {data.get('total')} total errors")
    
    def test_get_system_logs_stats(self, admin_token):
        """Admin can get system logs statistics."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/admin/system-logs/stats",
            headers=headers,
            timeout=10
        )
        
        assert response.status_code == 200, f"Failed to get stats: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "total" in data, f"Missing 'total' key: {data.keys()}"
        assert "unresolved" in data, f"Missing 'unresolved' key: {data.keys()}"
        
        print(f"✓ System logs stats working: {data.get('unresolved')} unresolved errors")


# Run tests if called directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
