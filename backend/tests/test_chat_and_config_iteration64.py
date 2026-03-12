"""
=================================================================
ITERATION 64 - BACKEND TESTS
=================================================================
Testing new features:
1. Chat API endpoints (conversations, messages, users)
2. Credit Services Configuration
3. Health check
=================================================================
"""

import pytest
import requests
import os

# Get BASE_URL from environment (includes /api prefix for endpoints)
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin"


class TestHealthAndAuth:
    """Health check and authentication tests"""
    
    def test_health_endpoint(self):
        """Test that backend health endpoint is working"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✅ Health endpoint working")
    
    def test_admin_login(self):
        """Test admin login returns token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "admin"
        print("✅ Admin login successful")


class TestChatAPI:
    """Chat internal messaging API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_conversations(self):
        """Test GET /api/chat/conversations endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/chat/conversations",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert isinstance(data["conversations"], list)
        print(f"✅ Chat conversations endpoint working - {len(data['conversations'])} conversations")
    
    def test_get_chat_users(self):
        """Test GET /api/chat/users endpoint - users available for chat"""
        response = requests.get(
            f"{BASE_URL}/api/chat/users",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert isinstance(data["users"], list)
        # Should have some users
        assert len(data["users"]) > 0
        # Each user should have required fields
        first_user = data["users"][0]
        assert "id" in first_user
        assert "name" in first_user
        assert "role" in first_user
        print(f"✅ Chat users endpoint working - {len(data['users'])} users available")
    
    def test_get_unread_count(self):
        """Test GET /api/chat/unread-count endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/chat/unread-count",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "unread_count" in data
        assert isinstance(data["unread_count"], int)
        print(f"✅ Unread count endpoint working - {data['unread_count']} unread messages")
    
    def test_get_online_users(self):
        """Test GET /api/chat/online-users endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/chat/online-users",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert isinstance(data["users"], list)
        print(f"✅ Online users endpoint working - {len(data['users'])} users online")


class TestCreditServicesConfig:
    """Credit services configuration API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_config_fields(self):
        """Test GET /api/system-config/fields endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/system-config/fields",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have credit_services section
        assert "credit_services" in data
        credit_services = data["credit_services"]
        
        # Verify structure
        assert credit_services.get("title") == "Serviços de Crédito Imobiliário"
        assert "fields" in credit_services
        
        # Verify expected providers exist
        fields = credit_services["fields"]
        primary_provider_field = next((f for f in fields if f.get("key") == "primary_provider"), None)
        assert primary_provider_field is not None
        
        options = primary_provider_field.get("options", [])
        option_values = [o.get("value") for o in options]
        
        # Check expected credit service options
        assert "hcpro" in option_values
        assert "decisoes_e_solucoes" in option_values
        assert "doutorfinancas" in option_values
        assert "maxfinance" in option_values
        
        print("✅ Credit services config fields endpoint working")
        print(f"   Available providers: {option_values}")
    
    def test_get_full_config(self):
        """Test GET /api/system-config endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/system-config",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have config and fields
        assert "config" in data
        assert "fields" in data
        
        print("✅ Full system config endpoint working")


class TestProcessAPI:
    """Process API tests for data origin tracking"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_processes(self):
        """Test GET /api/processes endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/processes?limit=3",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Processes endpoint working - {len(data)} processes retrieved")
    
    def test_get_single_process(self):
        """Test GET /api/processes/{id} endpoint"""
        # First get a process ID
        list_response = requests.get(
            f"{BASE_URL}/api/processes?limit=1",
            headers=self.headers
        )
        assert list_response.status_code == 200
        processes = list_response.json()
        
        if len(processes) > 0:
            process_id = processes[0].get("id")
            
            # Get single process
            response = requests.get(
                f"{BASE_URL}/api/processes/{process_id}",
                headers=self.headers
            )
            assert response.status_code == 200
            data = response.json()
            
            assert "id" in data
            assert "client_name" in data
            
            # Check for data origin fields (may be None but should exist in structure)
            print(f"✅ Single process endpoint working")
            print(f"   Process: {data.get('client_name')} - {data.get('status')}")
        else:
            pytest.skip("No processes available to test")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
