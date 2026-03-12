"""
Test Iteration 38 - Kanban Dark Mode and Idealista Import Features

Tests:
1. POST /api/leads - Create lead with correct field mapping (title, price, location, etc)
2. GET /api/leads/by-status - Verify Kanban endpoint works
3. Admin login and authentication
4. API verification for lead creation with Portuguese field mapping
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestLeadCreationFieldMapping:
    """Tests for lead creation with proper field mapping"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    def test_admin_login(self):
        """Test admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data or "token" in data, "Token not returned"
        print("Admin login successful - PASSED")

    def test_create_lead_with_field_mapping(self, auth_headers):
        """
        Test creating a lead with the correct field mapping.
        
        The IdealistaImportPage maps Portuguese fields to English:
        - titulo -> title
        - preco -> price
        - localizacao -> location
        - tipologia -> typology
        - area_util -> area
        """
        import uuid
        test_url = f"https://test-idealista-import-{uuid.uuid4().hex[:8]}.pt"
        
        lead_data = {
            "url": test_url,
            "title": "TEST_T2 em Lisboa com terraço",
            "price": 350000,
            "location": "Lisboa, Benfica",
            "typology": "T2",
            "area": 85,
            "photo_url": "https://example.com/photo.jpg",
            "notes": "TEST: Importado do Idealista via HTML paste",
            "consultant": {
                "name": "João Silva",
                "phone": "+351 912 345 678",
                "email": "joao@imobiliaria.pt",
                "agency_name": "Imobiliária Teste"
            }
        }
        
        response = requests.post(f"{BASE_URL}/api/leads", json=lead_data, headers=auth_headers)
        
        # Should create successfully
        assert response.status_code == 200, f"Lead creation failed: {response.status_code} - {response.text}"
        
        created_lead = response.json()
        
        # Verify all fields were correctly mapped
        assert created_lead.get("title") == "TEST_T2 em Lisboa com terraço", "title not mapped correctly"
        assert created_lead.get("price") == 350000, "price not mapped correctly"
        assert created_lead.get("location") == "Lisboa, Benfica", "location not mapped correctly"
        assert created_lead.get("typology") == "T2", "typology not mapped correctly"
        assert created_lead.get("area") == 85, "area not mapped correctly"
        assert created_lead.get("status") == "novo", "Status should be 'novo'"
        assert created_lead.get("id") is not None, "ID should be generated"
        
        # Verify consultant data
        consultant = created_lead.get("consultant")
        assert consultant is not None, "Consultant data should be present"
        assert consultant.get("name") == "João Silva", "Consultant name not mapped"
        assert consultant.get("phone") == "+351 912 345 678", "Consultant phone not mapped"
        
        print(f"Lead created successfully with ID: {created_lead.get('id')} - PASSED")
        
        # Cleanup - delete test lead
        lead_id = created_lead.get("id")
        if lead_id:
            delete_response = requests.delete(f"{BASE_URL}/api/leads/{lead_id}", headers=auth_headers)
            assert delete_response.status_code == 200, f"Failed to cleanup test lead: {delete_response.text}"
            print(f"Test lead {lead_id} cleaned up - PASSED")

    def test_leads_by_status_endpoint(self, auth_headers):
        """Test GET /api/leads/by-status for Kanban"""
        response = requests.get(f"{BASE_URL}/api/leads/by-status", headers=auth_headers)
        
        assert response.status_code == 200, f"Leads by status failed: {response.status_code} - {response.text}"
        
        data = response.json()
        
        # Should have all status columns
        expected_statuses = ["novo", "contactado", "visita_agendada", "proposta", "reservado", "descartado"]
        for status in expected_statuses:
            assert status in data, f"Missing status column: {status}"
            assert isinstance(data[status], list), f"Status {status} should be a list"
        
        print(f"Leads by status endpoint working - Found {len(expected_statuses)} columns - PASSED")

    def test_leads_list_endpoint(self, auth_headers):
        """Test GET /api/leads endpoint"""
        response = requests.get(f"{BASE_URL}/api/leads", headers=auth_headers)
        
        assert response.status_code == 200, f"Leads list failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        print(f"Leads list endpoint working - Found {len(data)} leads - PASSED")

    def test_consultores_endpoint(self, auth_headers):
        """Test GET /api/leads/consultores for filter dropdown"""
        response = requests.get(f"{BASE_URL}/api/leads/consultores", headers=auth_headers)
        
        assert response.status_code == 200, f"Consultores endpoint failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        print(f"Consultores endpoint working - Found {len(data)} consultores - PASSED")


class TestIdealistaImportAPI:
    """Tests for Idealista Import functionality"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    def test_extract_html_endpoint_exists(self, auth_headers):
        """Test that extract-html endpoint exists and validates input"""
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html", 
            json={"html": "", "url": ""},
            headers=auth_headers
        )
        
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404, "Extract-html endpoint should exist"
        
        print(f"Extract-html endpoint exists - Status: {response.status_code} - PASSED")

    def test_extract_html_with_sample_content(self, auth_headers):
        """Test extract-html with minimal HTML content"""
        sample_html = """
        <html>
            <head><title>T3 em Cascais - 450.000€</title></head>
            <body>
                <h1>Apartamento T3</h1>
                <span class="info-price">450.000 €</span>
                <span class="location">Cascais, Lisboa</span>
            </body>
        </html>
        """
        
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html", 
            json={"html": sample_html, "url": "https://test.idealista.pt/12345"},
            headers=auth_headers
        )
        
        # Endpoint should accept the request
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code}"
        
        print(f"Extract-html accepts content - Status: {response.status_code} - PASSED")


class TestDuplicateLeadHandling:
    """Test that duplicate leads are correctly rejected"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}

    def test_duplicate_lead_rejected(self, auth_headers):
        """Test that creating a lead with duplicate URL is rejected"""
        import uuid
        test_url = f"https://duplicate-test-{uuid.uuid4().hex[:8]}.pt"
        
        lead_data = {
            "url": test_url,
            "title": "TEST_Duplicate Test Lead",
            "price": 100000
        }
        
        # Create first lead
        response1 = requests.post(f"{BASE_URL}/api/leads", json=lead_data, headers=auth_headers)
        assert response1.status_code == 200, f"First lead creation failed: {response1.text}"
        
        first_lead = response1.json()
        first_id = first_lead.get("id")
        
        # Try to create duplicate
        response2 = requests.post(f"{BASE_URL}/api/leads", json=lead_data, headers=auth_headers)
        
        # Should be rejected with 400
        assert response2.status_code == 400, f"Duplicate should be rejected: {response2.status_code}"
        
        error_msg = response2.json().get("detail", "")
        assert "já existe" in error_msg.lower() or "duplicate" in error_msg.lower() or "url" in error_msg.lower(), \
            f"Error message should mention duplicate: {error_msg}"
        
        print(f"Duplicate lead correctly rejected - PASSED")
        
        # Cleanup
        if first_id:
            requests.delete(f"{BASE_URL}/api/leads/{first_id}", headers=auth_headers)
            print(f"Test lead {first_id} cleaned up - PASSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
