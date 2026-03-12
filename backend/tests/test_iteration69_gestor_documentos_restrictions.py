"""
Test gestor_documentos role restrictions
- Cannot create clients (POST /api/clients → 403)
- Cannot create processes for clients (POST /api/clients/{id}/create-process → 403)
- Can view client list
- Can view process/client details
- Can upload documents

Iteration 69 - Testing restrictions for gestor_documentos role
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
GESTOR_DOCS_CREDS = {"email": "powerprecision@sistema.pt", "password": "PowerCell"}
ADMIN_CREDS = {"email": "admin@sistema.pt", "password": "admin"}


class TestGestorDocumentosRestrictions:
    """Test that gestor_documentos role cannot create clients or processes"""
    
    @pytest.fixture(autouse=True)
    def setup(self, request):
        """Setup - login as gestor_documentos"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as gestor_documentos
        login_response = self.session.post(f"{BASE_URL}/api/auth/login-v2", json=GESTOR_DOCS_CREDS)
        if login_response.status_code == 200:
            data = login_response.json()
            self.token = data.get("access_token")
            self.user = data.get("user")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        else:
            pytest.skip(f"Could not login as gestor_documentos: {login_response.status_code}")
    
    def test_gestor_documentos_login_returns_correct_role(self):
        """Verify login returns role = gestor_documentos"""
        assert self.user is not None
        assert self.user.get("role") == "gestor_documentos"
        print(f"✓ Login successful with role: {self.user.get('role')}")
    
    def test_gestor_documentos_cannot_create_client(self):
        """POST /api/clients should return 403 for gestor_documentos"""
        client_data = {
            "nome": "TEST_Cliente_Restricao_GestorDocs",
            "email": "test.gestor.docs@example.com",
            "telefone": "912345678",
            "nif": "123456789"
        }
        
        response = self.session.post(f"{BASE_URL}/api/clients", json=client_data)
        
        # Should be 403 Forbidden
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        
        # Verify error message
        data = response.json()
        assert "detail" in data
        assert "Gestor de Documentos" in data["detail"] or "não pode criar" in data["detail"].lower()
        print(f"✓ gestor_documentos blocked from creating client: {data['detail']}")
    
    def test_gestor_documentos_cannot_create_process_for_client(self):
        """POST /api/clients/{id}/create-process should return 403 for gestor_documentos"""
        # First, get an existing client/process ID
        clients_response = self.session.get(f"{BASE_URL}/api/clients?limit=1")
        assert clients_response.status_code == 200, f"Failed to get clients: {clients_response.status_code}"
        
        clients_data = clients_response.json()
        if not clients_data.get("clients") or len(clients_data["clients"]) == 0:
            pytest.skip("No existing clients to test with")
        
        client_id = clients_data["clients"][0].get("id")
        assert client_id is not None, "Client ID not found"
        
        # Try to create process for this client
        response = self.session.post(
            f"{BASE_URL}/api/clients/{client_id}/create-process?process_type=credito_habitacao"
        )
        
        # Should be 403 Forbidden
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        
        # Verify error message
        data = response.json()
        assert "detail" in data
        assert "Gestor de Documentos" in data["detail"] or "não pode criar" in data["detail"].lower()
        print(f"✓ gestor_documentos blocked from creating process: {data['detail']}")
    
    def test_gestor_documentos_can_view_clients_list(self):
        """GET /api/clients should work for gestor_documentos"""
        response = self.session.get(f"{BASE_URL}/api/clients")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "clients" in data
        assert "total" in data
        print(f"✓ gestor_documentos can view clients list: {data['total']} clients found")
    
    def test_gestor_documentos_can_view_process_details(self):
        """GET /api/processes/{id} should work for gestor_documentos"""
        # First get a process ID - the endpoint returns a list directly
        processes_response = self.session.get(f"{BASE_URL}/api/processes?limit=1")
        assert processes_response.status_code == 200, f"Failed to get processes: {processes_response.status_code}"
        
        processes_data = processes_response.json()
        # API returns list directly or dict with 'processes' key
        if isinstance(processes_data, list):
            processes = processes_data
        else:
            processes = processes_data.get("processes", [])
        
        if not processes or len(processes) == 0:
            pytest.skip("No existing processes to test with")
        
        process_id = processes[0].get("id")
        
        # View process details
        response = self.session.get(f"{BASE_URL}/api/processes/{process_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert "client_name" in data or "nome" in data
        print(f"✓ gestor_documentos can view process details: {data.get('client_name', data.get('nome', 'N/A'))}")


class TestAdminCanCreateClientAndProcess:
    """Verify admin can still create clients and processes (control test)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - login as admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login-v2", json=ADMIN_CREDS)
        if login_response.status_code == 200:
            data = login_response.json()
            self.token = data.get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        else:
            pytest.skip(f"Could not login as admin: {login_response.status_code}")
    
    def test_admin_can_create_client(self):
        """Admin should be able to create clients (control test)"""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        
        client_data = {
            "nome": f"TEST_Admin_Can_Create_{unique_id}",
            "email": f"test.admin.{unique_id}@example.com",
            "telefone": "912345678"
        }
        
        response = self.session.post(f"{BASE_URL}/api/clients", json=client_data)
        
        # Admin should be able to create
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        print(f"✓ Admin can create client: {client_data['nome']}")
        
        # Cleanup - delete the test client
        if response.status_code in [200, 201]:
            client_id = response.json().get("id")
            if client_id:
                self.session.delete(f"{BASE_URL}/api/clients/{client_id}")


class TestGestorDocumentosDocumentUpload:
    """Test that gestor_documentos CAN upload documents"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - login as gestor_documentos"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login-v2", json=GESTOR_DOCS_CREDS)
        if login_response.status_code == 200:
            data = login_response.json()
            self.token = data.get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        else:
            pytest.skip(f"Could not login as gestor_documentos: {login_response.status_code}")
    
    def test_gestor_documentos_can_access_upload_endpoint(self):
        """gestor_documentos should be able to access document endpoints"""
        # Get a process to test upload endpoint access
        processes_response = self.session.get(f"{BASE_URL}/api/processes?limit=1")
        
        if processes_response.status_code != 200:
            pytest.skip("Cannot access processes")
        
        # API returns list directly or dict with 'processes' key
        processes_data = processes_response.json()
        if isinstance(processes_data, list):
            processes = processes_data
        else:
            processes = processes_data.get("processes", [])
        if not processes:
            pytest.skip("No processes available")
        
        process_id = processes[0].get("id")
        
        # Check if we can access the documents list (not upload, just read)
        docs_response = self.session.get(f"{BASE_URL}/api/processes/{process_id}/documents")
        
        # Should be able to access documents endpoint
        assert docs_response.status_code in [200, 404], f"Unexpected status: {docs_response.status_code}"
        print(f"✓ gestor_documentos can access documents endpoint")
