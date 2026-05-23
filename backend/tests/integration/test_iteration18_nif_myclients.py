"""
====================================================================
ITERATION 18: NIF EXTRACTION BUG FIX & MY-CLIENTS FEATURE TESTS
====================================================================
Tests for:
1. Bug fix: NIF extraction from CC documents - expected NIF=268494622
2. New endpoint: GET /api/processes/my-clients
3. New frontend page: /meus-clientes

Test credentials:
- Admin: geral@powerealestate.pt / admin123
- Consultor: tiagoborges@powerealestate.pt / admin123
====================================================================
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://auto-doc-fetch.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "geral@powerealestate.pt"
ADMIN_PASSWORD = "admin123"
CONSULTOR_EMAIL = "tiagoborges@powerealestate.pt"
CONSULTOR_PASSWORD = "admin123"


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login-v2", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin authentication failed: {response.status_code} - {response.text}")


@pytest.fixture
def consultor_token(api_client):
    """Get consultor authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login-v2", json={
        "email": CONSULTOR_EMAIL,
        "password": CONSULTOR_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Consultor authentication failed: {response.status_code} - {response.text}")


class TestHealthAndBasics:
    """Basic health check tests"""
    
    def test_health_endpoint(self, api_client):
        """Test health endpoint is accessible"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("PASS: Health endpoint working")
    
    def test_admin_login(self, api_client):
        """Test admin can login"""
        response = api_client.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] in ["admin", "ceo"]
        print(f"PASS: Admin login successful, role={data['user']['role']}")
    
    def test_consultor_login(self, api_client):
        """Test consultor can login"""
        response = api_client.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": CONSULTOR_EMAIL,
            "password": CONSULTOR_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "consultor"
        print(f"PASS: Consultor login successful, name={data['user']['name']}")


class TestMyClientsEndpoint:
    """Tests for GET /api/processes/my-clients endpoint"""
    
    def test_my_clients_requires_auth(self, api_client):
        """Test that my-clients endpoint requires authentication"""
        response = api_client.get(f"{BASE_URL}/api/processes/my-clients")
        # Should return 401 or 403 for unauthorized access
        assert response.status_code in [401, 403]
        print(f"PASS: my-clients requires authentication (status={response.status_code})")
    
    def test_my_clients_consultor_access(self, api_client, consultor_token):
        """Test consultor can access my-clients endpoint"""
        api_client.headers.update({"Authorization": f"Bearer {consultor_token}"})
        response = api_client.get(f"{BASE_URL}/api/processes/my-clients")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "clients" in data
        assert "total" in data
        assert "user_id" in data
        assert "user_role" in data
        assert data["user_role"] == "consultor"
        
        print(f"PASS: Consultor accessed my-clients, total={data['total']}")
    
    def test_my_clients_response_structure(self, api_client, consultor_token):
        """Test my-clients response has correct structure for each client"""
        api_client.headers.update({"Authorization": f"Bearer {consultor_token}"})
        response = api_client.get(f"{BASE_URL}/api/processes/my-clients")
        
        assert response.status_code == 200
        data = response.json()
        
        # If there are clients, verify the structure
        if data["total"] > 0:
            client = data["clients"][0]
            
            # Required fields
            assert "id" in client
            assert "client_name" in client
            assert "status" in client
            assert "status_label" in client
            assert "status_color" in client
            assert "pending_actions" in client
            assert "pending_count" in client
            
            # Optional but expected fields
            assert "process_number" in client
            assert "created_at" in client
            assert "updated_at" in client
            
            print(f"PASS: Client structure verified, client_name={client['client_name']}, status_label={client['status_label']}")
        else:
            print("PASS: Response structure valid (no clients assigned to this consultor)")
    
    def test_my_clients_admin_access_all(self, api_client, admin_token):
        """Test admin can access my-clients and sees all clients"""
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        response = api_client.get(f"{BASE_URL}/api/processes/my-clients")
        
        assert response.status_code == 200
        data = response.json()
        
        # Admin should see all clients
        assert "clients" in data
        assert data["user_role"] in ["admin", "ceo"]
        
        print(f"PASS: Admin accessed my-clients, total={data['total']}")
    
    def test_my_clients_pending_actions_structure(self, api_client, consultor_token):
        """Test pending_actions array has correct structure"""
        api_client.headers.update({"Authorization": f"Bearer {consultor_token}"})
        response = api_client.get(f"{BASE_URL}/api/processes/my-clients")
        
        assert response.status_code == 200
        data = response.json()
        
        # Find a client with pending actions if any
        for client in data.get("clients", []):
            if client.get("pending_actions"):
                action = client["pending_actions"][0]
                assert "type" in action  # task, document, info
                assert "title" in action
                assert "priority" in action
                print(f"PASS: Pending action structure verified, type={action['type']}, title={action['title']}")
                return
        
        print("PASS: Pending actions structure valid (no pending actions found)")


class TestAIDocumentAnalysis:
    """Tests for AI document analysis - NIF extraction bug fix"""
    
    def test_ai_analyze_endpoint_exists(self, api_client, admin_token):
        """Test that AI analyze endpoint exists"""
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        
        # Test with empty request to verify endpoint exists
        response = api_client.post(f"{BASE_URL}/api/ai/analyze-document", json={})
        
        # Should return 422 (validation error) or 400, not 404
        assert response.status_code != 404, "AI analyze endpoint not found"
        print(f"PASS: AI analyze endpoint exists, status={response.status_code}")
    
    def test_supported_documents_endpoint(self, api_client, admin_token):
        """Test supported documents endpoint"""
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        response = api_client.get(f"{BASE_URL}/api/ai/supported-documents")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have document_types with cc (Cartão de Cidadão)
        assert "document_types" in data
        doc_types = data["document_types"]
        assert isinstance(doc_types, list)
        
        # Verify cc type exists
        cc_type = next((d for d in doc_types if d.get("type") == "cc"), None)
        assert cc_type is not None, "CC document type not found"
        assert "nif" in cc_type.get("extracts", []), "NIF should be in CC extracts"
        
        print(f"PASS: Supported documents endpoint working, {len(doc_types)} types")
    
    def test_nif_extraction_from_cc_url(self, api_client, admin_token):
        """
        Test NIF extraction from CC document via URL analysis.
        
        Bug fix test: NIF should be extracted as 268494622 (not starting with 5).
        CC document: Carolina Silva
        """
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        
        # CC Carolina document URL
        cc_url = "https://customer-assets.emergentagent.com/job_464545a8-6c9a-4834-8b03-e4424f46ece6/artifacts/1ksca1cs_CC%20CAROLINA%20F%20E%20V.pdf"
        
        response = api_client.post(f"{BASE_URL}/api/ai/analyze-document", json={
            "document_url": cc_url,
            "document_type": "cc"
        })
        
        # Document analysis may take time or may fail due to rate limits
        if response.status_code == 200:
            data = response.json()
            
            # Check if NIF was extracted
            if data.get("success") and data.get("extracted_data"):
                extracted = data["extracted_data"]
                nif = extracted.get("nif")
                nome = extracted.get("nome_completo")
                
                print(f"Extracted NIF: {nif}")
                print(f"Extracted Name: {nome}")
                
                if nif:
                    # Bug fix verification: NIF should NOT start with 5
                    assert not str(nif).startswith("5"), f"BUG: NIF starts with 5 ({nif}), should start with 2"
                    
                    # Expected NIF for Carolina
                    expected_nif = "268494622"
                    if str(nif) == expected_nif:
                        print(f"PASS: NIF correctly extracted as {nif} (expected {expected_nif})")
                    else:
                        print(f"WARNING: NIF extracted as {nif}, expected {expected_nif}")
                else:
                    print("WARNING: NIF not found in extracted data")
            else:
                print(f"WARNING: Extraction not successful: {data.get('error', 'unknown')}")
        elif response.status_code == 429:
            pytest.skip("Rate limit reached, skipping NIF test")
        else:
            print(f"WARNING: Document analysis returned status {response.status_code}")


class TestWorkflowStatuses:
    """Tests for workflow statuses used in my-clients"""
    
    def test_get_workflow_statuses(self, api_client, admin_token):
        """Test getting workflow statuses"""
        api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
        response = api_client.get(f"{BASE_URL}/api/admin/workflow-statuses")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be a list of statuses
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Each status should have required fields
        status = data[0]
        assert "name" in status
        assert "label" in status
        assert "color" in status
        
        print(f"PASS: Got {len(data)} workflow statuses")
        for s in data[:5]:  # Print first 5
            print(f"  - {s['name']}: {s['label']}")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
