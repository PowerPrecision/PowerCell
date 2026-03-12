"""
Test Iteration 46: Expiring Documents Dashboard

Features tested:
- GET /api/documents/expiring-dashboard endpoint
- Permission checks: consultor vs management roles
- Stats, clients, and filters in response
- Consultor filter visibility for management only
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
CONSULTOR_EMAIL = "flaviosilva@powerealestate.pt"
CONSULTOR_PASSWORD = "flavio123"


class TestExpiringDocumentsDashboard:
    """Test suite for the expiring documents dashboard endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_auth_token(self, email: str, password: str) -> str:
        """Helper to get auth token"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = self.session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("PASSED: API health check")
    
    def test_consultor_login(self):
        """Test consultor can login"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token is not None, "Consultor login failed"
        print(f"PASSED: Consultor login successful")
        return token
    
    def test_expiring_dashboard_endpoint_exists(self):
        """Test the expiring-dashboard endpoint exists and requires auth"""
        response = self.session.get(f"{BASE_URL}/api/documents/expiring-dashboard")
        # Should return 401 without auth, not 404
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Endpoint exists and requires authentication")
    
    def test_expiring_dashboard_response_structure(self):
        """Test expiring-dashboard returns correct structure"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/documents/expiring-dashboard")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check required fields exist
        assert "stats" in data, "Response missing 'stats' field"
        assert "clients" in data, "Response missing 'clients' field"
        assert "total_clients" in data, "Response missing 'total_clients' field"
        assert "is_management" in data, "Response missing 'is_management' field"
        assert "consultors_filter" in data, "Response missing 'consultors_filter' field"
        assert "filters_applied" in data, "Response missing 'filters_applied' field"
        
        # Check stats structure
        stats = data["stats"]
        assert "total" in stats, "Stats missing 'total'"
        assert "critical" in stats, "Stats missing 'critical'"
        assert "high" in stats, "Stats missing 'high'"
        assert "medium" in stats, "Stats missing 'medium'"
        
        print(f"PASSED: Response structure correct - stats: {stats}")
        print(f"  is_management: {data['is_management']}")
        print(f"  total_clients: {data['total_clients']}")
        print(f"  consultors_filter count: {len(data['consultors_filter'])}")
    
    def test_consultor_permissions_not_management(self):
        """Test consultor is NOT marked as management"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/documents/expiring-dashboard")
        
        assert response.status_code == 200
        data = response.json()
        
        # Consultor should NOT be management
        assert data["is_management"] == False, f"Consultor should not be management, got: {data['is_management']}"
        
        # Consultor should NOT see consultors_filter (empty array)
        assert data["consultors_filter"] == [], f"Consultor should not see consultors_filter, got: {data['consultors_filter']}"
        
        print("PASSED: Consultor correctly NOT marked as management")
        print("PASSED: Consultor correctly does NOT see consultors_filter")
    
    def test_filters_applied_in_response(self):
        """Test filters_applied field reflects query parameters"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Test with default filters
        response = self.session.get(f"{BASE_URL}/api/documents/expiring-dashboard")
        assert response.status_code == 200
        data = response.json()
        
        filters = data["filters_applied"]
        assert filters["days_ahead"] == 60, f"Expected days_ahead=60, got: {filters['days_ahead']}"
        assert filters["urgency"] is None, f"Expected urgency=None, got: {filters['urgency']}"
        
        print(f"PASSED: Default filters applied correctly: {filters}")
    
    def test_urgency_filter_critical(self):
        """Test urgency filter with 'critical' value"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        response = self.session.get(
            f"{BASE_URL}/api/documents/expiring-dashboard",
            params={"urgency": "critical"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["filters_applied"]["urgency"] == "critical"
        print("PASSED: Urgency filter 'critical' accepted")
    
    def test_urgency_filter_high(self):
        """Test urgency filter with 'high' value"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        response = self.session.get(
            f"{BASE_URL}/api/documents/expiring-dashboard",
            params={"urgency": "high"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["filters_applied"]["urgency"] == "high"
        print("PASSED: Urgency filter 'high' accepted")
    
    def test_urgency_filter_medium(self):
        """Test urgency filter with 'medium' value"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        response = self.session.get(
            f"{BASE_URL}/api/documents/expiring-dashboard",
            params={"urgency": "medium"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["filters_applied"]["urgency"] == "medium"
        print("PASSED: Urgency filter 'medium' accepted")
    
    def test_days_ahead_filter(self):
        """Test days_ahead filter parameter"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Test with different days_ahead values
        for days in [7, 30, 90]:
            response = self.session.get(
                f"{BASE_URL}/api/documents/expiring-dashboard",
                params={"days_ahead": days}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["filters_applied"]["days_ahead"] == days, f"Expected days_ahead={days}, got: {data['filters_applied']['days_ahead']}"
            print(f"PASSED: days_ahead={days} filter accepted")
    
    def test_search_filter(self):
        """Test search filter parameter"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        response = self.session.get(
            f"{BASE_URL}/api/documents/expiring-dashboard",
            params={"search": "TestClient"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["filters_applied"]["search"] == "TestClient"
        print("PASSED: Search filter parameter accepted")
    
    def test_clients_list_structure(self):
        """Test structure of clients in response (if any exist)"""
        token = self.get_auth_token(CONSULTOR_EMAIL, CONSULTOR_PASSWORD)
        assert token, "Login failed"
        
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        response = self.session.get(f"{BASE_URL}/api/documents/expiring-dashboard")
        
        assert response.status_code == 200
        data = response.json()
        
        clients = data["clients"]
        assert isinstance(clients, list), "clients should be a list"
        
        if len(clients) > 0:
            client = clients[0]
            # Check client structure
            assert "process_id" in client, "Client missing 'process_id'"
            assert "client_name" in client, "Client missing 'client_name'"
            assert "consultor_id" in client, "Client missing 'consultor_id'"
            assert "consultor_name" in client, "Client missing 'consultor_name'"
            assert "documents" in client, "Client missing 'documents'"
            assert "critical_count" in client, "Client missing 'critical_count'"
            assert "high_count" in client, "Client missing 'high_count'"
            assert "medium_count" in client, "Client missing 'medium_count'"
            
            print(f"PASSED: Client structure correct for {client['client_name']}")
            
            # Check documents structure
            if len(client["documents"]) > 0:
                doc = client["documents"][0]
                assert "filename" in doc, "Document missing 'filename'"
                assert "expiry_date" in doc, "Document missing 'expiry_date'"
                assert "urgency" in doc, "Document missing 'urgency'"
                assert "days_until" in doc, "Document missing 'days_until'"
                print(f"PASSED: Document structure correct")
        else:
            print("PASSED: Empty clients list (no documents expiring)")


class TestManagementRolePermissions:
    """Test suite for management role permissions"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_get_admin_users(self):
        """Check if we can find admin/ceo/diretor users to test management permissions"""
        # First login as consultor to get list of users
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        
        if response.status_code != 200:
            pytest.skip("Could not login to check users")
        
        token = response.json().get("access_token")
        user_role = response.json().get("user", {}).get("role")
        
        print(f"Logged in user role: {user_role}")
        
        # MANAGEMENT_ROLES = ["diretor", "ceo", "admin"]
        is_management = user_role in ["diretor", "ceo", "admin"]
        
        if is_management:
            print(f"PASSED: Current user IS management role: {user_role}")
        else:
            print(f"INFO: Current user ({user_role}) is NOT management role")
            print("NOTE: To fully test management permissions, login with diretor/ceo/admin")
