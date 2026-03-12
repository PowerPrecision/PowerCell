"""
Test Iteration 65 - New Features:
1. Email Search Page and API (/api/emails/search)
2. Cursor-based Pagination (/api/processes/paginated)
3. My Clients API (/api/my-clients and /api/my-clients/stats)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAuthLogin:
    """Test authentication - required for all other tests"""
    
    def test_login_success(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        assert response.status_code == 200
        data = response.json()
        # The API returns access_token, not token
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == "admin@sistema.pt"


def get_auth_token():
    """Helper function to get auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@sistema.pt",
        "password": "admin"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    return None


class TestEmailSearch:
    """Test email search API (/api/emails/search)"""
    
    def test_email_search_requires_auth(self):
        """Test that email search requires authentication"""
        response = requests.get(f"{BASE_URL}/api/emails/search?q=test")
        assert response.status_code == 401
    
    def test_email_search_min_chars(self):
        """Test that search requires at least 3 characters"""
        token = get_auth_token()
        assert token is not None, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/emails/search?q=ab", headers=headers)
        assert response.status_code == 400
        assert "3 caracteres" in response.json().get("detail", "")
    
    def test_email_search_valid_query(self):
        """Test email search with valid query"""
        token = get_auth_token()
        assert token is not None, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/emails/search?q=test", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "emails" in data
        assert "total" in data
        assert isinstance(data["emails"], list)


class TestCursorPagination:
    """Test cursor-based pagination for processes (/api/processes/paginated)"""
    
    def test_paginated_requires_auth(self):
        """Test that paginated endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/processes/paginated")
        assert response.status_code == 401
    
    def test_paginated_basic(self):
        """Test basic pagination request"""
        token = get_auth_token()
        assert token is not None, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/processes/paginated?limit=5", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "processes" in data
        assert "next_cursor" in data
        assert "has_more" in data
        assert "limit" in data
        
        # Verify types
        assert isinstance(data["processes"], list)
        assert isinstance(data["has_more"], bool)
        assert data["limit"] == 5
        
        # Log results
        print(f"Paginated returned {len(data['processes'])} processes, has_more={data['has_more']}")
    
    def test_paginated_with_cursor(self):
        """Test pagination with cursor for next page"""
        token = get_auth_token()
        assert token is not None, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get first page
        response1 = requests.get(f"{BASE_URL}/api/processes/paginated?limit=5", headers=headers)
        assert response1.status_code == 200
        data1 = response1.json()
        
        print(f"First page: {len(data1['processes'])} processes, has_more={data1['has_more']}")
        
        # If there's a next cursor, test fetching next page
        if data1.get("next_cursor") and data1.get("has_more"):
            cursor = data1["next_cursor"]
            response2 = requests.get(
                f"{BASE_URL}/api/processes/paginated?limit=5&cursor={cursor}", 
                headers=headers
            )
            assert response2.status_code == 200
            data2 = response2.json()
            
            print(f"Second page: {len(data2['processes'])} processes, has_more={data2['has_more']}")
            
            # Verify we got different results
            if len(data1["processes"]) > 0 and len(data2["processes"]) > 0:
                ids1 = set(p.get("id") for p in data1["processes"])
                ids2 = set(p.get("id") for p in data2["processes"])
                # Pages should have different processes
                assert len(ids1.intersection(ids2)) == 0, "Found duplicate processes in pages"


class TestMyClients:
    """Test my clients API (/api/my-clients)"""
    
    def test_my_clients_requires_auth(self):
        """Test that my-clients endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/my-clients")
        assert response.status_code == 401
    
    def test_my_clients_list(self):
        """Test getting my clients list"""
        token = get_auth_token()
        assert token is not None, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/my-clients", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "clients" in data
        assert "total" in data
        assert isinstance(data["clients"], list)
        assert isinstance(data["total"], int)
        
        print(f"My clients: {data['total']} total clients")
        
        # Verify client structure if there are any
        if len(data["clients"]) > 0:
            client = data["clients"][0]
            # These fields should be present
            assert "id" in client
            print(f"First client: {client.get('client_name', 'N/A')}, status: {client.get('status', 'N/A')}")
    
    def test_my_clients_stats(self):
        """Test getting my clients statistics"""
        token = get_auth_token()
        assert token is not None, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/my-clients/stats", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "total_clients" in data
        assert isinstance(data["total_clients"], int)
        
        print(f"My clients stats: {data['total_clients']} total clients")
        
        # Optional fields
        if "by_status" in data:
            assert isinstance(data["by_status"], dict)
            print(f"By status: {data['by_status']}")
        if "pending_tasks" in data:
            assert isinstance(data["pending_tasks"], int)
            print(f"Pending tasks: {data['pending_tasks']}")


class TestHealthCheck:
    """Basic health check test"""
    
    def test_health_endpoint(self):
        """Test /health endpoint"""
        response = requests.get(f"{BASE_URL}/health")
        # Check if status is 200
        assert response.status_code == 200, f"Health check returned {response.status_code}"
        
        # Try to parse JSON, but handle non-JSON responses
        try:
            data = response.json()
            assert "status" in data
            print(f"Health check: {data}")
        except:
            # If not JSON, just check the text
            print(f"Health check response: {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
