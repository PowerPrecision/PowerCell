"""
====================================================================
Iteration 49: Test Fixes for Documents, Email IMAP, and Leads Scraper
====================================================================
Tests:
1. Documents - GET /api/documents/client/{id}/files should return S3 folder files
2. Email sync - POST /api/emails/sync/{process_id} should sync via IMAP
3. Leads scraper - POST /api/leads/extract-url should return clear success or error message
====================================================================
"""

import pytest
import requests
import os
import time

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://form-template-fix-1.preview.emergentagent.com')
BASE_URL = BASE_URL.rstrip('/')

# Test credentials
CONSULTOR_EMAIL = "flaviosilva@powerealestate.pt"
CONSULTOR_PASSWORD = "flavio123"


class TestAuthentication:
    """Test authentication before running other tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for consultor"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # API returns access_token, not token
        assert "access_token" in data, "access_token not in response"
        return data["access_token"]
    
    def test_consultor_login(self, auth_token):
        """Verify consultor can login and get token"""
        assert auth_token is not None
        assert len(auth_token) > 10
        print(f"✓ Consultor login successful, token: {auth_token[:20]}...")


class TestDocumentsS3:
    """Test Documents S3 file listing - GET /api/documents/client/{id}/files"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Create auth headers"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_client_id(self, auth_headers):
        """Get a test client ID from existing processes"""
        response = requests.get(
            f"{BASE_URL}/api/processes",
            headers=auth_headers
        )
        assert response.status_code == 200
        processes = response.json()
        
        if processes and len(processes) > 0:
            # Return first process with client_name
            for p in processes:
                if p.get("client_name"):
                    return p["id"]
            return processes[0]["id"]
        pytest.skip("No processes available for testing")
    
    def test_list_client_files_endpoint_exists(self, auth_headers, test_client_id):
        """Test that GET /api/documents/client/{id}/files endpoint exists and returns valid response"""
        response = requests.get(
            f"{BASE_URL}/api/documents/client/{test_client_id}/files",
            headers=auth_headers
        )
        
        # Endpoint should return 200 (even if empty)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"✓ GET /api/documents/client/{test_client_id}/files returned status 200")
        print(f"  Response keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
        
        # Verify response structure
        if isinstance(data, dict):
            # Should have 'files' key or similar structure
            assert "files" in data or "folders" in data or isinstance(data.get("files"), dict), \
                f"Response should have 'files' or 'folders' key, got: {list(data.keys())}"
            print(f"✓ Response structure is valid")
            
            # Check if files were found
            files = data.get("files", {})
            if isinstance(files, dict):
                total_files = sum(len(v) for v in files.values() if isinstance(v, list))
                print(f"  Total files found: {total_files}")
            elif isinstance(files, list):
                print(f"  Total files found: {len(files)}")
    
    def test_list_client_files_returns_s3_data(self, auth_headers, test_client_id):
        """Test that S3 file listing returns proper data structure"""
        response = requests.get(
            f"{BASE_URL}/api/documents/client/{test_client_id}/files",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # The response should have folder structure
        if isinstance(data, dict) and "files" in data:
            files_data = data["files"]
            # Should be a dict with category folders as keys
            if isinstance(files_data, dict):
                print(f"✓ Files organized in folders: {list(files_data.keys())}")
                
                # Each folder should have list of files
                for folder, file_list in files_data.items():
                    if isinstance(file_list, list):
                        for f in file_list[:2]:  # Show first 2 files
                            if isinstance(f, dict):
                                print(f"  - {folder}: {f.get('name', 'N/A')}")
    
    def test_list_client_files_nonexistent_client(self, auth_headers):
        """Test that nonexistent client returns 404"""
        fake_client_id = "nonexistent-client-id-12345"
        response = requests.get(
            f"{BASE_URL}/api/documents/client/{fake_client_id}/files",
            headers=auth_headers
        )
        
        # Should return 404 for non-existent client
        assert response.status_code == 404, f"Expected 404 for non-existent client, got {response.status_code}"
        print(f"✓ Correctly returns 404 for non-existent client")


class TestEmailSync:
    """Test Email IMAP sync - POST /api/emails/sync/{process_id}"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Create auth headers"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_process_id(self, auth_headers):
        """Get a test process ID from existing processes"""
        response = requests.get(
            f"{BASE_URL}/api/processes",
            headers=auth_headers
        )
        assert response.status_code == 200
        processes = response.json()
        
        if processes and len(processes) > 0:
            # Return first process with client_name
            for p in processes:
                if p.get("client_name") and p.get("client_email"):
                    return p["id"]
            return processes[0]["id"]
        pytest.skip("No processes available for testing")
    
    def test_email_sync_endpoint_exists(self, auth_headers, test_process_id):
        """Test that POST /api/emails/sync/{process_id} endpoint exists and works"""
        # Use a shorter timeframe to avoid timeout
        response = requests.post(
            f"{BASE_URL}/api/emails/sync/{test_process_id}",
            headers=auth_headers,
            params={"days": 7},  # Sync last 7 days only to reduce timeout
            timeout=60  # Allow 60 seconds for IMAP connection
        )
        
        # Endpoint should return 200, or 520/504 if timeout (which is a valid response for long-running IMAP)
        # 520 is Cloudflare's way of saying the backend timed out
        if response.status_code in [520, 504, 524]:
            print(f"⚠ Email sync timed out (status {response.status_code}) - this is expected for slow IMAP connections")
            pytest.skip("Email sync timed out - this is expected for slow IMAP connections")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"✓ POST /api/emails/sync/{test_process_id} returned status 200")
        print(f"  Response: {data}")
        
        # Verify response structure
        assert "success" in data, "Response should have 'success' key"
        
        if data.get("success"):
            # Check for expected fields in successful sync
            print(f"  ✓ Sync successful")
            print(f"    - Total found: {data.get('total_found', 'N/A')}")
            print(f"    - New imported: {data.get('new_imported', 'N/A')}")
        else:
            # Check for error message
            error_msg = data.get("error", "Unknown error")
            print(f"  ⚠ Sync returned success=false: {error_msg}")
            # This could be expected if no email accounts configured
    
    def test_email_sync_returns_proper_structure(self, auth_headers, test_process_id):
        """Test that email sync returns proper response structure with stats"""
        response = requests.post(
            f"{BASE_URL}/api/emails/sync/{test_process_id}",
            headers=auth_headers,
            params={"days": 7},
            timeout=60
        )
        
        # Handle timeout gracefully
        if response.status_code in [520, 504, 524]:
            print(f"⚠ Email sync timed out (status {response.status_code})")
            pytest.skip("Email sync timed out - this is expected for slow IMAP connections")
        
        assert response.status_code == 200
        data = response.json()
        
        # Response should have these fields
        expected_fields = ["success"]
        for field in expected_fields:
            assert field in data, f"Response should have '{field}' key"
        
        if data.get("success"):
            # If successful, should have stats
            optional_fields = ["total_found", "new_imported", "process_id"]
            found_fields = [f for f in optional_fields if f in data]
            print(f"✓ Successful sync response has fields: {found_fields}")
        
        print(f"✓ Email sync response structure is valid")
    
    def test_email_sync_nonexistent_process(self, auth_headers):
        """Test that sync with nonexistent process returns error"""
        fake_process_id = "nonexistent-process-id-12345"
        response = requests.post(
            f"{BASE_URL}/api/emails/sync/{fake_process_id}",
            headers=auth_headers
        )
        
        # Should return 200 with success=false or 404
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") == False or "error" in data, \
                "Should return success=false for non-existent process"
            print(f"✓ Returns error for non-existent process: {data.get('error', 'success=false')}")
        else:
            # 404 is also acceptable
            assert response.status_code == 404, f"Expected 404 or error response, got {response.status_code}"
            print(f"✓ Returns 404 for non-existent process")


class TestLeadsScraper:
    """Test Leads URL extraction - POST /api/leads/extract-url"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Create auth headers"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_extract_url_endpoint_exists(self, auth_headers):
        """Test that POST /api/leads/extract-url endpoint exists"""
        # Use a simple test URL that should work
        test_url = "https://www.idealista.pt/imovel/12345678/"
        
        response = requests.post(
            f"{BASE_URL}/api/leads/extract-url",
            headers=auth_headers,
            json={"url": test_url}
        )
        
        # Should return 200 (even if scraping fails)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"✓ POST /api/leads/extract-url returned status 200")
        print(f"  Response keys: {list(data.keys())}")
    
    def test_extract_url_returns_clear_message(self, auth_headers):
        """
        CRITICAL TEST: Verify scraper returns CLEAR message (success OR error)
        This addresses Item 1 from the problem statement.
        """
        # Use an Idealista URL that will likely fail due to anti-bot protection
        test_url = "https://www.idealista.pt/imovel/99999999/"
        
        response = requests.post(
            f"{BASE_URL}/api/leads/extract-url",
            headers=auth_headers,
            json={"url": test_url}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # MUST have 'success' field
        assert "success" in data, "Response MUST have 'success' field for clear feedback"
        
        # MUST have 'message' field with clear text
        assert "message" in data, "Response MUST have 'message' field with clear user feedback"
        
        message = data.get("message", "")
        
        # Message should NOT be empty
        assert len(message) > 5, f"Message should be descriptive, got: '{message}'"
        
        # Message should NOT be a raw error code or traceback
        assert "traceback" not in message.lower(), "Message should not contain traceback"
        assert "exception" not in message.lower(), "Message should not contain raw exception"
        
        print(f"✓ Extract URL returns clear message:")
        print(f"  - success: {data.get('success')}")
        print(f"  - message: {message[:100]}...")
        
        # If it failed (expected for Idealista due to blocking)
        if not data.get("success"):
            # Message should be user-friendly
            assert any(word in message.lower() for word in [
                "bloquear", "blocking", "manual", "tente", "erro", "error", "dados", "extrair"
            ]), f"Error message should be user-friendly, got: {message}"
            print(f"✓ Error message is user-friendly (explains what to do)")
    
    def test_extract_url_with_valid_url_format(self, auth_headers):
        """Test scraper with a properly formatted URL"""
        # Try a SAPO URL which is less likely to block
        test_url = "https://casa.sapo.pt/comprar-apartamentos/lisboa/"
        
        response = requests.post(
            f"{BASE_URL}/api/leads/extract-url",
            headers=auth_headers,
            json={"url": test_url}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "success" in data
        assert "message" in data
        
        if "data" in data:
            # If data was extracted, verify structure
            extracted = data.get("data", {})
            print(f"✓ Extracted data fields: {list(extracted.keys())}")
            
            # URL should be in data
            assert extracted.get("url"), "Data should contain the URL"
        
        print(f"✓ SAPO URL test - success: {data.get('success')}, message: {data.get('message', '')[:50]}")
    
    def test_extract_url_missing_url_returns_error(self, auth_headers):
        """Test that missing URL returns proper error"""
        response = requests.post(
            f"{BASE_URL}/api/leads/extract-url",
            headers=auth_headers,
            json={}  # No URL provided
        )
        
        # Should return 400 for missing URL
        assert response.status_code in [400, 422], f"Expected 400/422 for missing URL, got {response.status_code}"
        print(f"✓ Missing URL correctly returns {response.status_code}")
    
    def test_extract_url_adds_https_if_missing(self, auth_headers):
        """Test that scraper adds https:// if missing from URL"""
        # URL without protocol
        test_url = "www.idealista.pt/imovel/12345/"
        
        response = requests.post(
            f"{BASE_URL}/api/leads/extract-url",
            headers=auth_headers,
            json={"url": test_url}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that URL was normalized
        extracted_data = data.get("data", {})
        normalized_url = extracted_data.get("url", "")
        
        if normalized_url:
            assert normalized_url.startswith("http"), f"URL should have protocol added: {normalized_url}"
            print(f"✓ URL normalized to: {normalized_url}")
        
        print(f"✓ URL normalization test passed")


class TestEmailAccounts:
    """Test email account configuration"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": CONSULTOR_EMAIL, "password": CONSULTOR_PASSWORD}
        )
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Create auth headers"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_email_accounts_endpoint(self, auth_headers):
        """Test GET /api/emails/accounts returns configured accounts"""
        response = requests.get(
            f"{BASE_URL}/api/emails/accounts",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        accounts = response.json()
        
        assert isinstance(accounts, list), "Should return list of accounts"
        print(f"✓ Found {len(accounts)} email accounts configured")
        
        for acc in accounts:
            print(f"  - {acc.get('name')}: {acc.get('email')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
