"""
Iteration 44: Document Categorization and Search Feature Tests
================================================================
Tests for new document categorization with AI endpoints:
- GET /api/documents/metadata/{process_id}
- POST /api/documents/search
- GET /api/documents/categories
- POST /api/documents/categorize/{process_id}
- POST /api/documents/categorize-all/{process_id}
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "flaviosilva@powerealestate.pt"
TEST_PASSWORD = "flavio123"
TEST_PROCESS_ID = "9f573b70-538f-4c4b-87e7-71bfa12e1e8a"

# Module-level token storage to avoid rate limits
_cached_token = None


def get_auth_token():
    """Get authentication token (cached to avoid rate limits)"""
    global _cached_token
    if _cached_token:
        return _cached_token
    
    time.sleep(0.5)  # Rate limit avoidance
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        _cached_token = response.json().get("access_token")
        return _cached_token
    return None


class TestDocumentCategorizationAuth:
    """Test authentication for document endpoints"""
    
    def test_document_metadata_requires_auth(self):
        """Test that document metadata endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/documents/metadata/{TEST_PROCESS_ID}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ Document metadata requires authentication")
    
    def test_document_search_requires_auth(self):
        """Test that document search endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "test", "limit": 20}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ Document search requires authentication")
    
    def test_categories_requires_auth(self):
        """Test that categories endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/documents/categories")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ Categories endpoint requires authentication")


class TestDocumentMetadata:
    """Test GET /api/documents/metadata/{process_id}"""
    
    def test_get_metadata_success(self):
        """Test successful retrieval of document metadata"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.get(
            f"{BASE_URL}/api/documents/metadata/{TEST_PROCESS_ID}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "process_id" in data, "Response should contain process_id"
        assert data["process_id"] == TEST_PROCESS_ID
        assert "client_name" in data, "Response should contain client_name"
        assert "documents" in data, "Response should contain documents list"
        assert "total" in data, "Response should contain total count"
        assert "categorized" in data, "Response should contain categorized count"
        assert "categories" in data, "Response should contain categories list"
        assert isinstance(data["documents"], list)
        assert isinstance(data["categories"], list)
        print(f"✅ Got metadata for process {TEST_PROCESS_ID}: {data['total']} documents, {data['categorized']} categorized")
    
    def test_get_metadata_invalid_process(self):
        """Test metadata retrieval with invalid process ID"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.get(
            f"{BASE_URL}/api/documents/metadata/invalid-process-id",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✅ Invalid process ID returns 404")


class TestDocumentSearch:
    """Test POST /api/documents/search"""
    
    def test_search_success(self):
        """Test successful document search"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "contrato", "process_id": TEST_PROCESS_ID, "limit": 20},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "query" in data, "Response should contain query"
        assert data["query"] == "contrato"
        assert "total_results" in data, "Response should contain total_results"
        assert "results" in data, "Response should contain results list"
        assert isinstance(data["results"], list)
        print(f"✅ Search for 'contrato' returned {data['total_results']} results")
    
    def test_search_minimum_query_length(self):
        """Test search with minimum 2 character query"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "cc", "limit": 20},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["query"] == "cc"
        print("✅ Search accepts 2 character queries")
    
    def test_search_empty_query_validation(self):
        """Test search with empty query returns validation error"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "", "limit": 20},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✅ Empty query returns 422 validation error")
    
    def test_search_single_char_query_validation(self):
        """Test search with single character query returns validation error"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "a", "limit": 20},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("✅ Single character query returns 422 validation error")
    
    def test_search_with_categories_filter(self):
        """Test search with category filter"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "documento", "categories": ["Identificação", "Rendimentos"], "limit": 20},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "results" in data
        print("✅ Search with category filter works")
    
    def test_search_without_process_id(self):
        """Test global search without process_id filter"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "teste", "limit": 20},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "results" in data
        print("✅ Global search without process_id works")
    
    def test_search_limit_validation_upper(self):
        """Test search limit parameter validation (upper bound)"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "test", "limit": 150},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 422, f"Expected 422 for limit > 100, got {response.status_code}"
        print("✅ Limit > 100 returns 422")
    
    def test_search_limit_validation_lower(self):
        """Test search limit parameter validation (lower bound)"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": "test", "limit": 0},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 422, f"Expected 422 for limit < 1, got {response.status_code}"
        print("✅ Limit < 1 returns 422")
    
    def test_search_query_max_length(self):
        """Test search query max length validation"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        long_query = "a" * 501
        response = requests.post(
            f"{BASE_URL}/api/documents/search",
            json={"query": long_query, "limit": 20},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        assert response.status_code == 422, f"Expected 422 for query > 500 chars, got {response.status_code}"
        print("✅ Query > 500 chars returns 422")


class TestDocumentCategories:
    """Test GET /api/documents/categories"""
    
    def test_get_all_categories(self):
        """Test retrieval of all categories"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.get(
            f"{BASE_URL}/api/documents/categories",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "categories" in data, "Response should contain categories list"
        assert "total_categories" in data, "Response should contain total_categories count"
        assert isinstance(data["categories"], list)
        
        # Each category should have name and count
        for cat in data["categories"]:
            assert "name" in cat, "Category should have name"
            assert "count" in cat, "Category should have count"
        
        print(f"✅ Got {data['total_categories']} categories")
    
    def test_get_categories_by_process(self):
        """Test retrieval of categories filtered by process"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.get(
            f"{BASE_URL}/api/documents/categories",
            params={"process_id": TEST_PROCESS_ID},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "categories" in data
        assert "total_categories" in data
        print(f"✅ Got {data['total_categories']} categories for process {TEST_PROCESS_ID}")


class TestDocumentCategorization:
    """Test POST /api/documents/categorize/{process_id}"""
    
    def test_categorize_missing_params(self):
        """Test categorization with missing parameters"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/categorize/{TEST_PROCESS_ID}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✅ Categorize endpoint requires s3_path and filename")
    
    def test_categorize_invalid_process(self):
        """Test categorization with invalid process ID"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/categorize/invalid-process-id",
            data={"s3_path": "test/path/doc.pdf", "filename": "doc.pdf"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✅ Invalid process returns 404")
    
    def test_categorize_file_not_found(self):
        """Test categorization with non-existent S3 file"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/categorize/{TEST_PROCESS_ID}",
            data={"s3_path": "nonexistent/path/document.pdf", "filename": "document.pdf"},
            headers={"Authorization": f"Bearer {token}"}
        )
        # Should return error because file doesn't exist in S3
        # 404 = file not found, 500 = S3 error, 520 = Cloudflare error (server returned unknown error)
        assert response.status_code in [404, 500, 520], f"Expected 404, 500, or 520, got {response.status_code}"
        print(f"✅ Non-existent S3 file returns {response.status_code}")


class TestCategorizeAll:
    """Test POST /api/documents/categorize-all/{process_id}"""
    
    def test_categorize_all_success(self):
        """Test categorize all documents for a process"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/categorize-all/{TEST_PROCESS_ID}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "total" in data, "Response should contain total"
        assert "categorized" in data, "Response should contain categorized"
        assert "skipped" in data, "Response should contain skipped"
        assert "errors" in data, "Response should contain errors"
        assert "documents" in data, "Response should contain documents list"
        assert isinstance(data["documents"], list)
        
        print(f"✅ Categorize all: {data['total']} total, {data['categorized']} categorized, {data['skipped']} skipped, {data['errors']} errors")
    
    def test_categorize_all_invalid_process(self):
        """Test categorize all with invalid process ID"""
        token = get_auth_token()
        assert token, "Failed to get auth token"
        
        response = requests.post(
            f"{BASE_URL}/api/documents/categorize-all/invalid-process-id",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        print("✅ Invalid process ID returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
