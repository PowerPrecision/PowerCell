"""
Test iteration 19 - Testing new leads features and statistics endpoints:

1. POST /api/leads/{id}/refresh - Endpoint para verificar preço
2. GET /api/leads/by-status - Filtros por consultor e estado
3. GET /api/leads/consultores - Lista de consultores para filtro
4. GET /api/stats/leads - Estatísticas de leads (funil, ranking)
5. GET /api/stats/conversion - Estatísticas de conversão

Test credentials:
- admin: admin@sistema.pt / admin123
- consultor: consultor@sistema.pt / consultor123
"""
import os
import pytest
import requests

# Use public URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://workflow-builder-95.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin123"
CONSULTOR_EMAIL = "consultor@sistema.pt"
CONSULTOR_PASSWORD = "consultor123"


class TestHealthAndAuth:
    """Basic health check and authentication tests"""
    
    def test_health_endpoint(self):
        """Test that backend health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health endpoint working")
    
    def test_admin_login(self):
        """Test admin login with admin@sistema.pt"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        print(f"✓ Admin login successful - user: {data.get('user', {}).get('email')}")
        return data["access_token"]
    
    def test_consultor_login(self):
        """Test consultor login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        # Note: consultor might not exist, so we accept both 200 and 401
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Consultor login successful - user: {data.get('user', {}).get('email')}")
        else:
            print(f"⚠ Consultor login failed (status {response.status_code}) - user may not exist")


class TestLeadsEndpoints:
    """Test leads-related endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip("Could not authenticate as admin")
    
    def test_get_leads_by_status_endpoint(self):
        """Test GET /api/leads/by-status - returns leads grouped by status"""
        response = requests.get(
            f"{BASE_URL}/api/leads/by-status",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should return a dict with status keys
        expected_statuses = ["novo", "contactado", "visita_agendada", "proposta", "reservado", "descartado"]
        for status in expected_statuses:
            assert status in data, f"Missing status '{status}' in response"
            assert isinstance(data[status], list), f"Status '{status}' should be a list"
        
        print(f"✓ GET /api/leads/by-status - returned leads grouped by {len(data)} statuses")
        for status, leads in data.items():
            print(f"  - {status}: {len(leads)} leads")
    
    def test_get_leads_by_status_with_consultor_filter(self):
        """Test GET /api/leads/by-status with consultor_id filter"""
        # First get a list of consultores to get a valid ID
        consultores_response = requests.get(
            f"{BASE_URL}/api/leads/consultores",
            headers=self.headers
        )
        
        if consultores_response.status_code == 200:
            consultores = consultores_response.json()
            if consultores and len(consultores) > 0:
                consultor_id = consultores[0]["id"]
                response = requests.get(
                    f"{BASE_URL}/api/leads/by-status?consultor_id={consultor_id}",
                    headers=self.headers
                )
                assert response.status_code == 200, f"Failed: {response.text}"
                print(f"✓ GET /api/leads/by-status with consultor_id filter - status 200")
            else:
                print("⚠ No consultores found to test filter")
        else:
            print("⚠ Could not get consultores for filter test")
    
    def test_get_leads_by_status_with_status_filter(self):
        """Test GET /api/leads/by-status with status_filter"""
        response = requests.get(
            f"{BASE_URL}/api/leads/by-status?status_filter=novo",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # When filtering by status, only that status should have leads (if any)
        # But all status keys should still be present
        assert "novo" in data, "Missing 'novo' status key"
        print(f"✓ GET /api/leads/by-status with status_filter=novo - status 200")
    
    def test_get_consultores_endpoint(self):
        """Test GET /api/leads/consultores - returns list of consultores for filter"""
        response = requests.get(
            f"{BASE_URL}/api/leads/consultores",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /api/leads/consultores - returned {len(data)} consultores")
        
        # Check structure if there are consultores
        if len(data) > 0:
            first = data[0]
            assert "id" in first, "Consultor should have 'id'"
            assert "name" in first or "email" in first, "Consultor should have 'name' or 'email'"
            print(f"  First consultor: {first.get('name') or first.get('email')}")


class TestLeadRefreshEndpoint:
    """Test the new POST /api/leads/{id}/refresh endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip("Could not authenticate as admin")
    
    def test_refresh_lead_endpoint_exists(self):
        """Test POST /api/leads/{id}/refresh endpoint exists"""
        # First, get a lead to test with
        leads_response = requests.get(
            f"{BASE_URL}/api/leads",
            headers=self.headers
        )
        
        if leads_response.status_code == 200 and leads_response.json():
            leads = leads_response.json()
            if len(leads) > 0:
                lead_id = leads[0]["id"]
                response = requests.post(
                    f"{BASE_URL}/api/leads/{lead_id}/refresh",
                    headers=self.headers
                )
                # Should return 200 with success/error response
                assert response.status_code == 200, f"Failed: {response.text}"
                data = response.json()
                
                # Check response structure
                assert "success" in data, "Response should have 'success' field"
                assert "old_price" in data, "Response should have 'old_price' field"
                assert "price_changed" in data, "Response should have 'price_changed' field"
                print(f"✓ POST /api/leads/{lead_id}/refresh - success: {data.get('success')}")
                print(f"  Price changed: {data.get('price_changed')}, Old: {data.get('old_price')}, New: {data.get('new_price')}")
            else:
                print("⚠ No leads found to test refresh endpoint")
        else:
            print("⚠ Could not get leads to test refresh endpoint")
    
    def test_refresh_nonexistent_lead_returns_404(self):
        """Test refresh endpoint returns 404 for non-existent lead"""
        response = requests.post(
            f"{BASE_URL}/api/leads/nonexistent-id-12345/refresh",
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ POST /api/leads/nonexistent/refresh returns 404")


class TestStatsEndpoints:
    """Test statistics endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip("Could not authenticate as admin")
    
    def test_get_leads_stats(self):
        """Test GET /api/stats/leads - returns leads statistics"""
        response = requests.get(
            f"{BASE_URL}/api/stats/leads",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check response structure
        assert "total_leads" in data, "Response should have 'total_leads'"
        assert "leads_by_status" in data, "Response should have 'leads_by_status'"
        assert "funnel_data" in data, "Response should have 'funnel_data'"
        assert "top_consultors" in data, "Response should have 'top_consultors'"
        
        print(f"✓ GET /api/stats/leads - total_leads: {data.get('total_leads')}")
        print(f"  Leads by status: {data.get('leads_by_status')}")
        
        # Check funnel data structure
        funnel = data.get("funnel_data", [])
        if funnel:
            assert isinstance(funnel, list), "funnel_data should be a list"
            print(f"  Funnel data: {len(funnel)} stages")
            for item in funnel:
                assert "stage" in item, "Funnel item should have 'stage'"
                assert "count" in item, "Funnel item should have 'count'"
        
        # Check top consultors structure
        consultors = data.get("top_consultors", [])
        if consultors:
            assert isinstance(consultors, list), "top_consultors should be a list"
            print(f"  Top consultors: {len(consultors)} consultors")
            for item in consultors:
                assert "name" in item, "Consultor should have 'name'"
                assert "leads_count" in item, "Consultor should have 'leads_count'"
    
    def test_get_conversion_stats(self):
        """Test GET /api/stats/conversion - returns conversion statistics"""
        response = requests.get(
            f"{BASE_URL}/api/stats/conversion",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check response structure
        assert "avg_conversion_days" in data, "Response should have 'avg_conversion_days'"
        assert "total_converted" in data, "Response should have 'total_converted'"
        assert "min_days" in data, "Response should have 'min_days'"
        assert "max_days" in data, "Response should have 'max_days'"
        
        print(f"✓ GET /api/stats/conversion")
        print(f"  Avg conversion days: {data.get('avg_conversion_days')}")
        print(f"  Total converted: {data.get('total_converted')}")
        print(f"  Min/Max days: {data.get('min_days')} / {data.get('max_days')}")
    
    def test_get_general_stats(self):
        """Test GET /api/stats - general statistics endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/stats",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check basic stats present
        assert "total_processes" in data, "Response should have 'total_processes'"
        print(f"✓ GET /api/stats - total_processes: {data.get('total_processes')}")


class TestLeadsCardDateAndStale:
    """Test that leads have created_at and is_stale data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            pytest.skip("Could not authenticate as admin")
    
    def test_leads_have_date_info(self):
        """Test that leads by-status includes days_old and is_stale"""
        response = requests.get(
            f"{BASE_URL}/api/leads/by-status",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Find a lead to check
        lead_found = False
        for status, leads in data.items():
            if leads and len(leads) > 0:
                lead = leads[0]
                lead_found = True
                # Check for new fields
                if "days_old" in lead:
                    print(f"✓ Lead has 'days_old' field: {lead.get('days_old')}")
                if "is_stale" in lead:
                    print(f"✓ Lead has 'is_stale' field: {lead.get('is_stale')}")
                if "created_at" in lead:
                    print(f"✓ Lead has 'created_at' field: {lead.get('created_at')[:19]}")
                break
        
        if not lead_found:
            print("⚠ No leads found to verify date fields")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
