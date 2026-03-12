"""
Iteration 17 - Tests for:
1. Impersonation (admin personifica outro utilizador e para)
2. Visibilidade Clientes (Consultor consegue ver clientes)
3. API Clientes (GET /api/clients com token de consultor)
4. Leads Page (Consultor consegue aceder a /leads)
5. Bulk Upload API (endpoint /api/ai/bulk/clients-list)
6. Processos Kanban (GET /api/processes/kanban com token de consultor)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin2026"
CONSULTOR_EMAIL = "tiagoborges@powerealestate.pt"

class TestAdminLogin:
    """Teste 1: Admin login"""
    
    def test_admin_login_success(self):
        """Admin login com credenciais corretas"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token"
        assert "user" in data, "Missing user"
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"
        print(f"Admin login successful: {data['user']['name']}")


class TestImpersonation:
    """Teste de Impersonation: Admin personifica consultor e volta"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        return response.json().get("access_token")
    
    def test_get_users_list(self, admin_token):
        """Obter lista de utilizadores para encontrar consultor"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        assert response.status_code == 200, f"Failed to get users: {response.text}"
        users = response.json()
        print(f"Found {len(users)} users")
        
        # Find consultor
        consultor = next((u for u in users if u.get("role") == "consultor"), None)
        if consultor:
            print(f"Found consultor: {consultor['name']} ({consultor['email']})")
        else:
            print("No consultor found in users list")
        return users
    
    def test_impersonate_consultor(self, admin_token):
        """Admin personifica consultor e verifica dados"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # 1. Get users list to find consultor ID
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        assert users_response.status_code == 200
        users = users_response.json()
        
        consultor = next((u for u in users if u.get("role") == "consultor"), None)
        if not consultor:
            pytest.skip("No consultor user found to impersonate")
        
        consultor_id = consultor["id"]
        print(f"Impersonating consultor: {consultor['name']} (ID: {consultor_id})")
        
        # 2. Impersonate the consultor
        impersonate_response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{consultor_id}",
            headers=headers
        )
        assert impersonate_response.status_code == 200, f"Impersonate failed: {impersonate_response.text}"
        
        impersonate_data = impersonate_response.json()
        assert "access_token" in impersonate_data
        assert "user" in impersonate_data
        assert impersonate_data["user"]["role"] == "consultor"
        assert impersonate_data["user"]["is_impersonated"] == True
        print(f"Successfully impersonating as: {impersonate_data['user']['name']}")
        print(f"Impersonated by: {impersonate_data['user']['impersonated_by']}")
        
        return impersonate_data["access_token"]
    
    def test_impersonate_and_stop(self, admin_token):
        """Full flow: Admin impersonate -> verify -> stop impersonate -> verify back to admin"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # 1. Get consultor
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        users = users_response.json()
        consultor = next((u for u in users if u.get("role") == "consultor"), None)
        
        if not consultor:
            pytest.skip("No consultor to impersonate")
        
        # 2. Impersonate
        impersonate_response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{consultor['id']}",
            headers=headers
        )
        assert impersonate_response.status_code == 200
        impersonate_token = impersonate_response.json()["access_token"]
        impersonate_user = impersonate_response.json()["user"]
        
        print(f"STEP 1: Now impersonating {impersonate_user['name']} (role: {impersonate_user['role']})")
        assert impersonate_user["is_impersonated"] == True
        
        # 3. Verify current user is consultor with impersonate flag
        impersonate_headers = {"Authorization": f"Bearer {impersonate_token}"}
        me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=impersonate_headers)
        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["role"] == "consultor"
        assert me_data.get("is_impersonated") == True
        print(f"STEP 2: /auth/me confirms impersonation: {me_data['name']} (is_impersonated: {me_data.get('is_impersonated')})")
        
        # 4. Stop impersonation
        stop_response = requests.post(
            f"{BASE_URL}/api/admin/stop-impersonate",
            headers=impersonate_headers
        )
        assert stop_response.status_code == 200, f"Stop impersonate failed: {stop_response.text}"
        stop_data = stop_response.json()
        
        assert "access_token" in stop_data
        assert stop_data["user"]["role"] == "admin"
        print(f"STEP 3: Stopped impersonation. Back to: {stop_data['user']['name']} (role: {stop_data['user']['role']})")
        
        # 5. Verify we're back to admin
        admin_token_new = stop_data["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token_new}"}
        me_admin_response = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        assert me_admin_response.status_code == 200
        me_admin = me_admin_response.json()
        assert me_admin["role"] == "admin"
        assert me_admin.get("is_impersonated") is None or me_admin.get("is_impersonated") == False
        print(f"STEP 4: Confirmed back to admin: {me_admin['name']}")
        
        return True


class TestConsultorClientVisibility:
    """Teste de visibilidade de clientes para consultor"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin token for impersonation"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        return response.json().get("access_token")
    
    @pytest.fixture
    def consultor_token(self, admin_token):
        """Get consultor token via impersonation"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get consultor user
        users_response = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
        users = users_response.json()
        consultor = next((u for u in users if u.get("role") == "consultor"), None)
        
        if not consultor:
            pytest.skip("No consultor found")
        
        # Impersonate
        impersonate_response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{consultor['id']}",
            headers=headers
        )
        return impersonate_response.json().get("access_token")
    
    def test_consultor_can_access_clients_api(self, consultor_token):
        """Consultor consegue aceder a /api/clients"""
        headers = {"Authorization": f"Bearer {consultor_token}"}
        response = requests.get(f"{BASE_URL}/api/clients", headers=headers)
        
        assert response.status_code == 200, f"Clients API failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert "clients" in data, "Missing 'clients' key in response"
        print(f"Consultor sees {data.get('total', len(data.get('clients', [])))} clients")
        
        if data.get("clients"):
            first_client = data["clients"][0]
            print(f"First client: {first_client.get('nome', first_client.get('name', 'N/A'))}")
    
    def test_consultor_can_access_kanban(self, consultor_token):
        """Consultor consegue aceder a /api/processes/kanban"""
        headers = {"Authorization": f"Bearer {consultor_token}"}
        response = requests.get(f"{BASE_URL}/api/processes/kanban", headers=headers)
        
        assert response.status_code == 200, f"Kanban API failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert "columns" in data, "Missing 'columns' in kanban response"
        print(f"Kanban has {len(data['columns'])} columns, user_role: {data.get('user_role')}")
        print(f"Total processes visible: {data.get('total_processes', 'N/A')}")


class TestLeadsAccess:
    """Teste de acesso a leads"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        return response.json().get("access_token")
    
    def test_admin_can_access_leads(self, admin_token):
        """Admin pode aceder a /api/leads"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/leads", headers=headers)
        
        assert response.status_code == 200, f"Leads API failed: {response.text}"
        data = response.json()
        print(f"Leads API returned {len(data) if isinstance(data, list) else 'object'}")
    
    def test_admin_can_access_leads_by_status(self, admin_token):
        """Admin pode aceder a /api/leads/by-status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/leads/by-status", headers=headers)
        
        assert response.status_code == 200, f"Leads by-status API failed: {response.text}"
        data = response.json()
        print(f"Leads by status keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")


class TestBulkUploadAPI:
    """Teste de API de Bulk Upload"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        return response.json().get("access_token")
    
    def test_bulk_clients_list_endpoint(self, admin_token):
        """Testar endpoint /api/ai/bulk/clients-list"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/ai/bulk/clients-list", headers=headers)
        
        assert response.status_code == 200, f"Bulk clients-list failed: {response.status_code} - {response.text}"
        data = response.json()
        
        assert "total" in data, "Missing 'total' in response"
        assert "clients" in data, "Missing 'clients' in response"
        
        print(f"Bulk clients-list returned {data['total']} clients")
        
        if data["clients"]:
            first_client = data["clients"][0]
            print(f"First client: {first_client.get('name')} (#{first_client.get('number')})")
            
            # Validate structure
            assert "id" in first_client, "Client missing 'id'"
            assert "name" in first_client, "Client missing 'name'"


class TestHealthAndBasics:
    """Testes básicos de saúde do sistema"""
    
    def test_health_endpoint(self):
        """Health endpoint acessível"""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("Health endpoint OK")
    
    def test_api_docs_accessible(self):
        """API docs accessible"""
        response = requests.get(f"{BASE_URL}/docs")
        assert response.status_code == 200, "Swagger docs not accessible"
        print("Swagger docs accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
