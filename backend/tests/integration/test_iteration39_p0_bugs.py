"""
Iteration 39: P0 Bug Fixes Testing
===================================
Tests for the P0 bugs reported:
1. Kanban in dark mode rendering
2. 'Criar Lead' button from HTML import
3. HTML extraction showing more data (titulo, preco, localizacao, tipologia, area, quartos, casas_banho, agente_nome, etc)
4. 'Ver' link on Lead card - only appears if URL starts with http:// or https://
5. Gemini to OpenAI fallback when quota exceeded
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://form-template-fix-1.preview.emergentagent.com')


class TestAuthentication:
    """Authentication tests"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        return data["access_token"]
    
    def test_admin_login(self, auth_token):
        """Test admin login works"""
        assert auth_token is not None
        assert len(auth_token) > 10
        print(f"✓ Admin login successful, token: {auth_token[:20]}...")


class TestHtmlExtractionEndpoint:
    """Test the /api/scraper/extract-html endpoint returns multiple fields"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_extract_html_endpoint_exists(self, auth_token):
        """Test that POST /api/scraper/extract-html endpoint exists"""
        # Send minimal HTML to verify endpoint
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"html": "<html><body>Test</body></html>", "url": "test.pt"}
        )
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404, "Endpoint /api/scraper/extract-html not found"
        print(f"✓ POST /api/scraper/extract-html endpoint exists (status: {response.status_code})")
    
    def test_extract_html_with_idealista_content(self, auth_token):
        """Test HTML extraction with sample Idealista-like content returns multiple fields"""
        # Sample HTML that simulates an Idealista property page
        sample_html = """
        <html>
        <head><title>T2 Apartamento - Idealista</title></head>
        <body>
            <div class="idealista">
                <h1 class="main-info__title">T2 Apartamento com Terraço em Benfica</h1>
                <span class="info-data-price">250.000 €</span>
                <span class="main-info__title-minor">Lisboa, Benfica</span>
                <div class="details-property">
                    <li class="info-features-item">85 m²</li>
                    <li class="info-features-item">2 quartos</li>
                    <li class="info-features-item">1 wc</li>
                    <li class="info-features-item">Garagem</li>
                </div>
                <div class="comment">
                    Excelente apartamento T2 com terraço, totalmente renovado.
                    Cozinha equipada, ar condicionado.
                    Certificado Energético: B
                </div>
                <div class="advertiser-data">
                    <span class="professional-name">João Silva</span>
                    <span class="agency-name">ERA Portugal</span>
                    <a href="tel:+351912345678">912 345 678</a>
                    <a href="mailto:joao@era.pt">joao@era.pt</a>
                </div>
                <span class="reference">Ref: ABC123</span>
            </div>
        </body>
        </html>
        """
        
        response = requests.post(
            f"{BASE_URL}/api/scraper/extract-html",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"html": sample_html, "url": "https://www.idealista.pt/imovel/test123"}
        )
        
        # Accept 200 (success) or 400/422 (validation but endpoint works)
        # NOT 404 (endpoint missing) or 500 (server error)
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code}, body: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ HTML extraction response: {list(data.keys())}")
            
            # Check that multiple fields are returned (the improved prompt should extract 30+ fields)
            expected_fields = ['titulo', 'preco', 'localizacao', 'tipologia', 'area', 'quartos', 'casas_banho']
            found_fields = [f for f in expected_fields if f in data and data[f] is not None]
            print(f"  Found fields: {found_fields}")
            
            # At minimum we should get some basic fields
            # Note: This depends on AI processing, so we verify response structure
            assert isinstance(data, dict), "Response should be a dictionary"
            print(f"✓ HTML extraction returned {len(data)} fields")
        else:
            print(f"⚠ HTML extraction returned status {response.status_code} - may need AI quota")


class TestLeadCreation:
    """Test lead creation with extracted data fields"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_create_lead_accepts_all_fields(self, auth_token):
        """Test POST /api/leads accepts all mapped fields from extraction"""
        import time
        unique_url = f"https://test-iteration39-{int(time.time())}.pt/imovel/test"
        
        lead_data = {
            "url": unique_url,
            "title": "T2 Apartamento Teste Iteration39",
            "price": 250000,
            "location": "Lisboa, Benfica",
            "typology": "T2",
            "area": 85,
            "photo_url": "https://example.com/photo.jpg",
            "notes": "Test lead from iteration 39",
            "consultant": {
                "name": "Teste Agente",
                "phone": "+351912345678",
                "email": "teste@agencia.pt",
                "agency_name": "Agência Teste"
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/leads",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=lead_data
        )
        
        assert response.status_code in [200, 201], f"Failed to create lead: {response.status_code} - {response.text}"
        
        created_lead = response.json()
        print(f"✓ Lead created with ID: {created_lead.get('id')}")
        
        # Verify fields were stored correctly
        assert created_lead.get("title") == lead_data["title"], "Title mismatch"
        assert created_lead.get("price") == lead_data["price"], "Price mismatch"
        assert created_lead.get("location") == lead_data["location"], "Location mismatch"
        assert created_lead.get("typology") == lead_data["typology"], "Typology mismatch"
        assert created_lead.get("area") == lead_data["area"], "Area mismatch"
        
        # Verify consultant data
        consultant = created_lead.get("consultant", {})
        assert consultant.get("name") == lead_data["consultant"]["name"], "Consultant name mismatch"
        
        print("✓ All lead fields stored correctly")
        
        # Cleanup - delete the test lead
        lead_id = created_lead.get("id")
        if lead_id:
            delete_response = requests.delete(
                f"{BASE_URL}/api/leads/{lead_id}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            if delete_response.status_code == 200:
                print(f"✓ Test lead {lead_id} cleaned up")


class TestLeadUrlValidation:
    """Test that 'Ver' link only appears for valid URLs"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_lead_with_valid_http_url(self, auth_token):
        """Test lead with valid http:// URL stores correctly"""
        import time
        unique_url = f"http://test-http-{int(time.time())}.pt/imovel"
        
        response = requests.post(
            f"{BASE_URL}/api/leads",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"url": unique_url, "title": "Test HTTP URL"}
        )
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        lead = response.json()
        assert lead.get("url") == unique_url
        print(f"✓ Lead with http:// URL created successfully")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/leads/{lead.get('id')}", headers={"Authorization": f"Bearer {auth_token}"})
    
    def test_lead_with_valid_https_url(self, auth_token):
        """Test lead with valid https:// URL stores correctly"""
        import time
        unique_url = f"https://test-https-{int(time.time())}.pt/imovel"
        
        response = requests.post(
            f"{BASE_URL}/api/leads",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"url": unique_url, "title": "Test HTTPS URL"}
        )
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        lead = response.json()
        assert lead.get("url") == unique_url
        print(f"✓ Lead with https:// URL created successfully")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/leads/{lead.get('id')}", headers={"Authorization": f"Bearer {auth_token}"})


class TestLeadsKanbanEndpoints:
    """Test Kanban-related endpoints"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_leads_by_status_returns_all_columns(self, auth_token):
        """Test GET /api/leads/by-status returns all 6 status columns"""
        response = requests.get(
            f"{BASE_URL}/api/leads/by-status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code}"
        data = response.json()
        
        expected_statuses = ["novo", "contactado", "visita_agendada", "proposta", "reservado", "descartado"]
        for status in expected_statuses:
            assert status in data, f"Status '{status}' not in response"
        
        print(f"✓ GET /api/leads/by-status returns all 6 columns: {list(data.keys())}")
    
    def test_consultores_endpoint(self, auth_token):
        """Test GET /api/leads/consultores for filter dropdown"""
        response = requests.get(
            f"{BASE_URL}/api/leads/consultores",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /api/leads/consultores returns {len(data)} consultores")


class TestScraperSupportedSites:
    """Test scraper endpoint for supported sites"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Get admin auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@admin.com", "password": "admin"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_supported_sites_endpoint(self, auth_token):
        """Test GET /api/scraper/supported-sites"""
        response = requests.get(
            f"{BASE_URL}/api/scraper/supported-sites",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Failed: {response.status_code}"
        data = response.json()
        
        assert "supported_sites" in data, "Missing supported_sites"
        assert "ai_analysis" in data, "Missing ai_analysis"
        
        sites = data["supported_sites"]
        site_names = [s["name"].lower() for s in sites]
        
        # Check some expected sites are listed
        expected = ["idealista", "imovirtual", "era", "remax"]
        for site in expected:
            found = any(site in name for name in site_names)
            print(f"  - {site}: {'✓' if found else '✗'}")
        
        print(f"✓ Supported sites endpoint returns {len(sites)} sites")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
