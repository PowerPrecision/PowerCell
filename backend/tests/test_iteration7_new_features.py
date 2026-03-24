"""
Iteration 7 - Testing new features and bug fixes:
1. Bug fix: PublicClientForm loads without console errors (draft merge fix)
2. Required fields show red * and '(obrigatório)' text
3. Step 4: 'Trabalha no estrangeiro?' dropdown
4. Step 5: 'Nenhuma' button in bank sections
5. Backend API: GET /api/admin/form-config/fields
6. Backend API: PUT /api/admin/form-config/fields
7. Backend API: POST /api/admin/form-config/reset
8. Backend API: PUT /api/admin/users/{id} with permissions field
9. Frontend: /configuracoes-perfis page
10. Frontend: /gestao-formulario page
11. Frontend: ClientRegistrationsPage details dialog shows ALL fields
12. DashboardLayout sidebar new entries
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://workflow-builder-95.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin"
CEO_EMAIL = "pedroborges@powerealestate.pt"
CEO_PASSWORD = "power2026"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def ceo_token():
    """Get CEO authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CEO_EMAIL, "password": CEO_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"CEO authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def ceo_headers(ceo_token):
    """Headers with CEO auth"""
    return {"Authorization": f"Bearer {ceo_token}", "Content-Type": "application/json"}


class TestFormConfigAPI:
    """Test form configuration API endpoints"""
    
    def test_get_form_config_fields_admin(self, admin_headers):
        """GET /api/admin/form-config/fields - Admin can get form config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "fields" in data, "Response should contain 'fields' key"
        fields = data["fields"]
        assert isinstance(fields, list), "Fields should be a list"
        assert len(fields) >= 20, f"Expected at least 20 fields, got {len(fields)}"
        
        # Verify field structure
        first_field = fields[0]
        assert "field_key" in first_field, "Field should have field_key"
        assert "label" in first_field, "Field should have label"
        assert "step" in first_field, "Field should have step"
        assert "is_visible" in first_field, "Field should have is_visible"
        assert "is_required" in first_field, "Field should have is_required"
        print(f"✓ Form config has {len(fields)} fields")
    
    def test_get_form_config_fields_ceo(self, ceo_headers):
        """GET /api/admin/form-config/fields - CEO can get form config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=ceo_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ CEO can access form config")
    
    def test_form_config_has_trabalha_estrangeiro_field(self, admin_headers):
        """Verify trabalha_estrangeiro field exists in form config"""
        response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        fields = data["fields"]
        field_keys = [f["field_key"] for f in fields]
        
        assert "trabalha_estrangeiro" in field_keys, "trabalha_estrangeiro field should exist"
        
        # Find the field and verify it's in step 4
        trabalha_field = next((f for f in fields if f["field_key"] == "trabalha_estrangeiro"), None)
        assert trabalha_field is not None
        assert trabalha_field["step"] == 4, f"trabalha_estrangeiro should be in step 4, got step {trabalha_field['step']}"
        print(f"✓ trabalha_estrangeiro field found in step {trabalha_field['step']}")
    
    def test_form_config_has_bancos_fields(self, admin_headers):
        """Verify bancos_creditos and bancos_simulacoes fields exist"""
        response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        fields = data["fields"]
        field_keys = [f["field_key"] for f in fields]
        
        assert "bancos_creditos" in field_keys, "bancos_creditos field should exist"
        assert "bancos_simulacoes" in field_keys, "bancos_simulacoes field should exist"
        print("✓ Bank fields (bancos_creditos, bancos_simulacoes) found")
    
    def test_update_form_config_fields(self, admin_headers):
        """PUT /api/admin/form-config/fields - Update form config"""
        # First get current config
        get_response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers
        )
        assert get_response.status_code == 200
        current_fields = get_response.json()["fields"]
        
        # Update config (just send back the same fields)
        response = requests.put(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers,
            json={"fields": current_fields}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should contain message"
        assert "updated_at" in data, "Response should contain updated_at"
        print("✓ Form config updated successfully")
    
    def test_reset_form_config(self, admin_headers):
        """POST /api/admin/form-config/reset - Reset to defaults"""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/reset",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should contain message"
        assert "fields" in data, "Response should contain fields"
        assert len(data["fields"]) >= 20, "Reset should return default fields"
        print(f"✓ Form config reset to defaults ({len(data['fields'])} fields)")
    
    def test_form_config_unauthorized(self):
        """Form config endpoints require authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/form-config/fields")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Form config requires authentication")


class TestUserPermissionsAPI:
    """Test user permissions update API"""
    
    def test_get_users_list(self, admin_headers):
        """GET /api/admin/users - Get list of users"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        users = response.json()
        assert isinstance(users, list), "Response should be a list"
        assert len(users) >= 1, "Should have at least 1 user"
        print(f"✓ Found {len(users)} users")
    
    def test_update_user_with_permissions(self, admin_headers):
        """PUT /api/admin/users/{id} - Update user with permissions field"""
        # First get a user to update
        users_response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers
        )
        assert users_response.status_code == 200
        users = users_response.json()
        
        # Find a non-admin user to update
        test_user = next((u for u in users if u["role"] != "admin"), None)
        if not test_user:
            pytest.skip("No non-admin user found to test")
        
        user_id = test_user["id"]
        
        # Update with permissions
        permissions = {
            "pages": ["dashboard", "kanban", "processes", "clients"],
            "actions": ["create_process", "edit_process", "upload_docs"]
        }
        
        response = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}",
            headers=admin_headers,
            json={"permissions": permissions}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "permissions" in data, "Response should contain permissions"
        assert data["permissions"]["pages"] == permissions["pages"], "Pages should match"
        assert data["permissions"]["actions"] == permissions["actions"], "Actions should match"
        print(f"✓ User {test_user['name']} updated with permissions")
    
    def test_update_user_role(self, admin_headers):
        """PUT /api/admin/users/{id} - Update user role"""
        # Get users
        users_response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers
        )
        users = users_response.json()
        
        # Find a consultor to test role change
        test_user = next((u for u in users if u["role"] == "consultor"), None)
        if not test_user:
            pytest.skip("No consultor user found to test")
        
        user_id = test_user["id"]
        original_role = test_user["role"]
        
        # Change role to mediador
        response = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}",
            headers=admin_headers,
            json={"role": "mediador"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Change back to original
        requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}",
            headers=admin_headers,
            json={"role": original_role}
        )
        print(f"✓ User role update works")
    
    def test_update_user_is_active(self, admin_headers):
        """PUT /api/admin/users/{id} - Update user is_active status"""
        users_response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=admin_headers
        )
        users = users_response.json()
        
        # Find a non-admin user
        test_user = next((u for u in users if u["role"] not in ["admin", "ceo"]), None)
        if not test_user:
            pytest.skip("No suitable user found to test")
        
        user_id = test_user["id"]
        
        # Deactivate user
        response = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}",
            headers=admin_headers,
            json={"is_active": False}
        )
        assert response.status_code == 200
        
        # Reactivate user
        response = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}",
            headers=admin_headers,
            json={"is_active": True}
        )
        assert response.status_code == 200
        print("✓ User is_active toggle works")


class TestPublicClientRegistration:
    """Test public client registration form API"""
    
    def test_public_registration_endpoint_exists(self):
        """POST /api/public/client-registration - Endpoint exists"""
        # Just verify the endpoint exists (don't actually create a client)
        response = requests.post(
            f"{BASE_URL}/api/public/client-registration",
            json={}  # Empty body to trigger validation error
        )
        # Should get 422 (validation error) not 404
        assert response.status_code in [422, 400], f"Expected 422 or 400, got {response.status_code}"
        print("✓ Public registration endpoint exists")
    
    def test_public_registration_validation(self):
        """POST /api/public/client-registration - Validates required fields"""
        response = requests.post(
            f"{BASE_URL}/api/public/client-registration",
            json={
                "name": "",  # Empty name
                "email": "invalid-email",  # Invalid email
                "phone": "",
                "process_type": "ambos"
            }
        )
        # Should fail validation
        assert response.status_code in [422, 400], f"Expected validation error, got {response.status_code}"
        print("✓ Public registration validates input")


class TestClientRegistrationsAPI:
    """Test client registrations list API"""
    
    def test_get_registered_clients(self, admin_headers):
        """GET /api/clients/registered - Get list of registered clients"""
        response = requests.get(
            f"{BASE_URL}/api/clients/registered",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "clients" in data, "Response should contain 'clients'"
        assert "total" in data, "Response should contain 'total'"
        print(f"✓ Found {data['total']} registered clients")
    
    def test_get_client_details(self, admin_headers):
        """GET /api/clients/{id} - Get client details"""
        # First get a client
        clients_response = requests.get(
            f"{BASE_URL}/api/clients/registered?limit=1",
            headers=admin_headers
        )
        if clients_response.status_code != 200:
            pytest.skip("Could not get clients list")
        
        clients = clients_response.json().get("clients", [])
        if not clients:
            pytest.skip("No clients found to test")
        
        client_id = clients[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/clients/{client_id}",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "nome" in data or "name" in data, "Client should have name"
        print(f"✓ Client details retrieved successfully")


class TestWorkflowStatusesAPI:
    """Test workflow statuses API (used by new pages)"""
    
    def test_get_workflow_statuses(self, admin_headers):
        """GET /api/admin/workflow-statuses - Get workflow statuses"""
        response = requests.get(
            f"{BASE_URL}/api/admin/workflow-statuses",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        statuses = response.json()
        assert isinstance(statuses, list), "Response should be a list"
        assert len(statuses) >= 1, "Should have at least 1 status"
        print(f"✓ Found {len(statuses)} workflow statuses")


class TestAutomationAPI:
    """Test automation API (sidebar entry)"""
    
    def test_get_automation_rules(self, admin_headers):
        """GET /api/admin/automation/rules - Get automation rules"""
        response = requests.get(
            f"{BASE_URL}/api/admin/automation/rules",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "rules" in data, "Response should contain 'rules'"
        print(f"✓ Automation rules endpoint works")
    
    def test_get_automation_triggers(self, admin_headers):
        """GET /api/admin/automation/triggers - Get available triggers"""
        response = requests.get(
            f"{BASE_URL}/api/admin/automation/triggers",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        triggers = data.get("triggers", data) if isinstance(data, dict) else data
        assert isinstance(triggers, list), "Response should contain a list of triggers"
        print(f"✓ Found {len(triggers)} automation triggers")
    
    def test_get_automation_actions(self, admin_headers):
        """GET /api/admin/automation/actions - Get available actions"""
        response = requests.get(
            f"{BASE_URL}/api/admin/automation/actions",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        actions = data.get("actions", data) if isinstance(data, dict) else data
        assert isinstance(actions, list), "Response should contain a list of actions"
        print(f"✓ Found {len(actions)} automation actions")


class TestHealthAndAuth:
    """Basic health and auth tests"""
    
    def test_health_endpoint(self):
        """GET /api/health - Health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health endpoint working")
    
    def test_admin_login(self):
        """POST /api/auth/login - Admin login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"
        print("✓ Admin login successful")
    
    def test_ceo_login(self):
        """POST /api/auth/login - CEO login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CEO_EMAIL, "password": CEO_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "ceo"
        print("✓ CEO login successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
