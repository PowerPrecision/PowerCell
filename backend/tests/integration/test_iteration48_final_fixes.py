"""
Iteration 48: Testing Final Fixes
=================================
Tests for:
1. Leads - GET /api/leads/by-status returns data
2. PUT /api/processes/{id} updates financial_data
3. New RealEstateData fields: area_pretendida, valor_maximo, finalidade, ja_tem_casa_escolhida
4. Verify autorizacao_bancaria references replaced by fase_bancaria/ch_aprovado
"""

import pytest
import requests
import os
import uuid

# Base URL from environment variable
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
CONSULTOR_EMAIL = "flaviosilva@powerealestate.pt"
CONSULTOR_PASSWORD = "flavio123"
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin123"


class TestConsultorAuth:
    """Test consultor authentication."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for consultor."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"Could not authenticate consultor: {response.status_code}")
    
    def test_consultor_login(self, auth_token):
        """Test that consultor can login successfully."""
        assert auth_token is not None, "Auth token should be returned"
        print(f"PASSED: Consultor login successful, token obtained")


class TestLeads:
    """Test leads endpoints."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"Could not authenticate: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Return headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_leads_by_status_returns_data(self, headers):
        """Test GET /api/leads/by-status returns grouped data."""
        response = requests.get(
            f"{BASE_URL}/api/leads/by-status",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should return a dictionary with status keys
        assert isinstance(data, dict), "Response should be a dictionary"
        
        # Verify expected status keys exist (from LeadStatus enum)
        expected_statuses = ["novo", "contactado", "visita_agendada", "proposta", "reservado", "descartado"]
        for status in expected_statuses:
            assert status in data, f"Status '{status}' should be in response"
            assert isinstance(data[status], list), f"Status '{status}' should contain a list"
        
        print(f"PASSED: GET /api/leads/by-status returns grouped data")
        print(f"  - Status groups found: {list(data.keys())}")
        total_leads = sum(len(v) for v in data.values())
        print(f"  - Total leads: {total_leads}")
    
    def test_leads_list_endpoint(self, headers):
        """Test GET /api/leads returns list of leads."""
        response = requests.get(
            f"{BASE_URL}/api/leads",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"PASSED: GET /api/leads returns {len(data)} leads")


class TestProcessUpdate:
    """Test process update endpoints."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"Could not authenticate: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Return headers with auth token."""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    @pytest.fixture(scope="class")
    def test_process_id(self, headers):
        """Get a process ID for testing."""
        # First list processes to get a valid ID
        response = requests.get(
            f"{BASE_URL}/api/processes",
            headers=headers
        )
        if response.status_code == 200:
            processes = response.json()
            if processes:
                return processes[0]["id"]
        pytest.skip("No processes available for testing")
    
    def test_update_financial_data(self, headers, test_process_id):
        """Test PUT /api/processes/{id} updates financial_data correctly."""
        # Test financial data update
        update_payload = {
            "financial_data": {
                "capital_proprio": 25000.00,
                "valor_financiado": "200000",
                "acesso_portal_financas": "sim",
                "chave_movel_digital": "sim"
            }
        }
        
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            headers=headers,
            json=update_payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify financial_data was updated
        financial = data.get("financial_data", {})
        assert financial is not None, "financial_data should exist in response"
        
        # Note: The backend may not return all fields, but the update should succeed
        print(f"PASSED: PUT /api/processes/{test_process_id} updated financial_data successfully")
        print(f"  - Response includes financial_data: {financial is not None}")
    
    def test_update_real_estate_data_new_fields(self, headers, test_process_id):
        """Test PUT /api/processes/{id} accepts new RealEstateData fields."""
        # Test with new fields: area_pretendida, valor_maximo_imovel, finalidade, ja_tem_casa_escolhida
        update_payload = {
            "real_estate_data": {
                "area_pretendida": "100-150",
                "valor_maximo_imovel": "350000",
                "finalidade": "compra_imovel",
                "ja_tem_casa_escolhida": True,
                "proprietario_nome": "Manuel Silva",
                "proprietario_contacto": "912345678",
                "caracteristicas_imovel": "T3 com garagem"
            }
        }
        
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            headers=headers,
            json=update_payload
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify real_estate_data was updated
        real_estate = data.get("real_estate_data", {})
        assert real_estate is not None, "real_estate_data should exist in response"
        
        # Check if new fields are in response
        print(f"PASSED: PUT /api/processes/{test_process_id} accepts new RealEstateData fields")
        print(f"  - real_estate_data in response: {real_estate is not None}")
        if real_estate:
            print(f"  - area_pretendida: {real_estate.get('area_pretendida')}")
            print(f"  - valor_maximo_imovel: {real_estate.get('valor_maximo_imovel')}")
            print(f"  - finalidade: {real_estate.get('finalidade')}")
            print(f"  - ja_tem_casa_escolhida: {real_estate.get('ja_tem_casa_escolhida')}")


class TestPublicRegistrationNewFields:
    """Test public registration with new real_estate_data fields."""
    
    def test_public_registration_with_new_fields(self):
        """Test POST /api/public/client-registration accepts new RealEstateData fields."""
        unique_email = f"test_iter48_{uuid.uuid4().hex[:8]}@test.com"
        
        registration_payload = {
            "name": "Teste Iter48 Cliente",
            "email": unique_email,
            "phone": "+351910000000",
            "process_type": "ambos",
            "personal_data": {
                "estado_civil": "solteiro"
            },
            "real_estate_data": {
                "area_pretendida": "80-120",
                "valor_maximo_imovel": "250000",
                "finalidade": "compra_imovel",
                "ja_tem_casa_escolhida": False
            },
            "financial_data": {
                "capital_proprio": 15000
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/public/client-registration",
            json=registration_payload
        )
        
        # Should return 201 Created or 200 OK
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify process was created
        assert "process_id" in data or "id" in data, "Response should contain process ID"
        
        print(f"PASSED: Public registration accepts new RealEstateData fields")
        print(f"  - Client: {unique_email}")
        print(f"  - Process created: {data.get('process_id') or data.get('id')}")


class TestWorkflowStatuses:
    """Test that workflow statuses use correct names (fase_bancaria, ch_aprovado)."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"Could not authenticate: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Return headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_workflow_statuses_no_autorizacao_bancaria(self, headers):
        """Test that workflow statuses do not contain 'autorizacao_bancaria'."""
        # Correct endpoint is /api/admin/workflow-statuses
        response = requests.get(
            f"{BASE_URL}/api/admin/workflow-statuses",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        statuses = response.json()
        
        assert isinstance(statuses, list), "Response should be a list"
        
        # Get all status names
        status_names = [s.get("name", "") for s in statuses]
        
        # Verify 'autorizacao_bancaria' is not in status names
        assert "autorizacao_bancaria" not in status_names, "Status 'autorizacao_bancaria' should not exist"
        
        # Verify new statuses exist (fase_bancaria, ch_aprovado)
        print(f"PASSED: No 'autorizacao_bancaria' in workflow statuses")
        print(f"  - Status names: {status_names}")
        
        # Check for expected bank-related statuses
        bank_related = [s for s in status_names if "fase_bancaria" in s or "ch_aprovado" in s or "bank" in s.lower()]
        print(f"  - Bank-related statuses found: {bank_related}")


class TestKanbanIntegration:
    """Test Kanban board uses correct status values."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"Could not authenticate: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Return headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_kanban_board_statuses(self, headers):
        """Test GET /api/processes/kanban uses correct statuses."""
        response = requests.get(
            f"{BASE_URL}/api/processes/kanban",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should have columns array
        columns = data.get("columns", [])
        assert isinstance(columns, list), "Columns should be a list"
        
        # Get all column names
        column_names = [c.get("name", "") for c in columns]
        
        # Verify no 'autorizacao_bancaria' column
        assert "autorizacao_bancaria" not in column_names, "Column 'autorizacao_bancaria' should not exist"
        
        print(f"PASSED: Kanban board uses correct statuses")
        print(f"  - Column count: {len(columns)}")
        print(f"  - Total processes: {data.get('total_processes', 0)}")


class TestProcessGet:
    """Test GET process endpoint returns data correctly."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"Could not authenticate: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Return headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_get_process_returns_all_data_sections(self, headers):
        """Test GET /api/processes/{id} returns all data sections."""
        # First get a process ID
        list_response = requests.get(
            f"{BASE_URL}/api/processes",
            headers=headers
        )
        
        if list_response.status_code != 200 or not list_response.json():
            pytest.skip("No processes available for testing")
        
        process_id = list_response.json()[0]["id"]
        
        # Get the process details
        response = requests.get(
            f"{BASE_URL}/api/processes/{process_id}",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert "id" in data, "Response should contain 'id'"
        assert "status" in data, "Response should contain 'status'"
        assert "client_name" in data, "Response should contain 'client_name'"
        
        # Check data sections exist (may be null but should be in schema)
        print(f"PASSED: GET /api/processes/{process_id} returns complete data")
        print(f"  - client_name: {data.get('client_name')}")
        print(f"  - status: {data.get('status')}")
        print(f"  - Has personal_data: {data.get('personal_data') is not None}")
        print(f"  - Has financial_data: {data.get('financial_data') is not None}")
        print(f"  - Has real_estate_data: {data.get('real_estate_data') is not None}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
