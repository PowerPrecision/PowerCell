"""
====================================================================
ITERATION 24 - Testing New Features:
====================================================================
Features to test:
1. API de Minutas: POST /api/minutas, GET /api/minutas, PUT /api/minutas/{id}, DELETE /api/minutas/{id}
2. API de Backups: GET /api/backup/statistics, POST /api/backup/trigger
3. API de Scraper: POST /api/scraper/single - friendly error messages when scraping fails
4. Menu Lateral: Admin vê 'Backups' e 'Minutas', Staff vê 'Minutas'
5. Página de Backups: /admin/backups shows statistics and history
6. Página de Minutas: /minutas allows CRUD of minutas

Test Credentials:
- Admin: admin@sistema.pt / admin123
====================================================================
"""
import pytest
import requests
import os
import uuid

# Use environment variable BASE_URL
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://workflow-builder-95.preview.emergentagent.com').rstrip('/')

class TestMinutasAPI:
    """Test CRUD operations for Minutas"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@sistema.pt", "password": "admin123"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, admin_token):
        """Auth headers for admin"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {admin_token}"
        }
    
    def test_create_minuta(self, auth_headers):
        """Test POST /api/minutas creates a new minuta"""
        test_id = str(uuid.uuid4())[:8]
        payload = {
            "titulo": f"Test Contrato {test_id}",
            "categoria": "contrato",
            "descricao": "Test description for contract template",
            "conteudo": "Conteudo do contrato de teste - [NOME_CLIENTE] - [DATA]",
            "tags": ["teste", "contrato", "automacao"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutas",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200, f"Create minuta failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert "minuta" in data
        assert data["minuta"]["titulo"] == payload["titulo"]
        assert data["minuta"]["categoria"] == payload["categoria"]
        assert "id" in data["minuta"]
        
        # Store for later tests
        self.__class__.created_minuta_id = data["minuta"]["id"]
        self.__class__.created_minuta_titulo = data["minuta"]["titulo"]
        print(f"✅ Created minuta with ID: {self.created_minuta_id}")
    
    def test_list_minutas(self, auth_headers):
        """Test GET /api/minutas lists all minutas"""
        response = requests.get(
            f"{BASE_URL}/api/minutas",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"List minutas failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert "minutas" in data
        assert "total" in data
        assert isinstance(data["minutas"], list)
        print(f"✅ Listed {data['total']} minutas")
    
    def test_get_minuta_by_id(self, auth_headers):
        """Test GET /api/minutas/{id} returns specific minuta"""
        # Skip if no minuta was created
        if not hasattr(self.__class__, 'created_minuta_id'):
            pytest.skip("No minuta created in previous test")
        
        response = requests.get(
            f"{BASE_URL}/api/minutas/{self.created_minuta_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Get minuta failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert "minuta" in data
        assert data["minuta"]["id"] == self.created_minuta_id
        print(f"✅ Retrieved minuta: {data['minuta']['titulo']}")
    
    def test_update_minuta(self, auth_headers):
        """Test PUT /api/minutas/{id} updates a minuta"""
        if not hasattr(self.__class__, 'created_minuta_id'):
            pytest.skip("No minuta created in previous test")
        
        update_payload = {
            "titulo": f"Updated Contrato {str(uuid.uuid4())[:8]}",
            "descricao": "Updated description",
            "conteudo": "Updated content - [NOME_CLIENTE] - [VALOR]"
        }
        
        response = requests.put(
            f"{BASE_URL}/api/minutas/{self.created_minuta_id}",
            headers=auth_headers,
            json=update_payload
        )
        
        assert response.status_code == 200, f"Update minuta failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data["minuta"]["titulo"] == update_payload["titulo"]
        print(f"✅ Updated minuta: {data['minuta']['titulo']}")
    
    def test_delete_minuta(self, auth_headers):
        """Test DELETE /api/minutas/{id} deletes a minuta"""
        if not hasattr(self.__class__, 'created_minuta_id'):
            pytest.skip("No minuta created in previous test")
        
        response = requests.delete(
            f"{BASE_URL}/api/minutas/{self.created_minuta_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Delete minuta failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        print(f"✅ Deleted minuta: {self.created_minuta_id}")
        
        # Verify deletion - should return 404
        verify_response = requests.get(
            f"{BASE_URL}/api/minutas/{self.created_minuta_id}",
            headers=auth_headers
        )
        assert verify_response.status_code == 404, "Minuta should not exist after deletion"
        print("✅ Verified minuta was deleted (404 response)")


class TestBackupAPI:
    """Test Backup API endpoints - Admin only"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@sistema.pt", "password": "admin123"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, admin_token):
        """Auth headers for admin"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {admin_token}"
        }
    
    def test_get_backup_statistics(self, auth_headers):
        """Test GET /api/backup/statistics returns backup stats"""
        response = requests.get(
            f"{BASE_URL}/api/backup/statistics",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Get backup statistics failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert "data" in data
        
        stats = data["data"]
        # Verify expected fields exist
        assert "total_backups" in stats
        assert "successful_backups" in stats
        assert "success_rate" in stats
        assert "total_size_bytes" in stats
        print(f"✅ Backup statistics: {stats['total_backups']} total, {stats['successful_backups']} successful")
    
    def test_get_backup_history(self, auth_headers):
        """Test GET /api/backup/history returns backup history"""
        response = requests.get(
            f"{BASE_URL}/api/backup/history?limit=20",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Get backup history failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert "history" in data
        assert isinstance(data["history"], list)
        print(f"✅ Backup history: {len(data['history'])} records")
    
    def test_get_backup_config(self, auth_headers):
        """Test GET /api/backup/config returns backup configuration"""
        response = requests.get(
            f"{BASE_URL}/api/backup/config",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Get backup config failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert "config" in data
        
        config = data["config"]
        assert "backup_dir" in config
        assert "local_retention_days" in config
        print(f"✅ Backup config: retention={config['local_retention_days']} days")
    
    def test_trigger_backup(self, auth_headers):
        """Test POST /api/backup/trigger initiates backup"""
        payload = {
            "upload_to_cloud": False,  # Don't upload to cloud in test
            "cleanup_after": False      # Don't cleanup in test
        }
        
        response = requests.post(
            f"{BASE_URL}/api/backup/trigger",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200, f"Trigger backup failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert "message" in data
        print(f"✅ Backup triggered: {data['message']}")


class TestScraperAPI:
    """Test Scraper API endpoints - friendly error messages"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@sistema.pt", "password": "admin123"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, admin_token):
        """Auth headers for admin"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {admin_token}"
        }
    
    def test_scraper_single_valid_url(self, auth_headers):
        """Test POST /api/scraper/single with a valid URL"""
        payload = {
            "url": "https://www.google.com",  # Simple URL that should work
            "use_cache": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/scraper/single",
            headers=auth_headers,
            json=payload
        )
        
        # Should return 200 with success or friendly error
        assert response.status_code == 200, f"Scraper endpoint failed: {response.text}"
        data = response.json()
        
        # Whether success or error, response should be structured
        assert "success" in data
        print(f"✅ Scraper response: success={data['success']}")
    
    def test_scraper_single_invalid_url_friendly_error(self, auth_headers):
        """Test POST /api/scraper/single returns friendly error for invalid URL"""
        payload = {
            "url": "https://invalid-domain-that-does-not-exist-12345.com/property",
            "use_cache": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/scraper/single",
            headers=auth_headers,
            json=payload
        )
        
        # Should return 200 with friendly error message
        assert response.status_code == 200, f"Scraper endpoint failed: {response.text}"
        data = response.json()
        
        # Should indicate failure with friendly message
        assert "success" in data
        if not data["success"]:
            assert "error" in data
            # Error message should be user-friendly (Portuguese)
            error_msg = data["error"]
            assert len(error_msg) > 0, "Error message should not be empty"
            # Verify it suggests manual entry
            if "data" in data and data["data"]:
                assert "suggest_manual" in data["data"] or "can_retry" in data["data"]
        
        print(f"✅ Scraper friendly error test passed: {data.get('error', 'N/A')[:50]}...")
    
    def test_scraper_supported_sites(self, auth_headers):
        """Test GET /api/scraper/supported-sites returns list of supported sites"""
        response = requests.get(
            f"{BASE_URL}/api/scraper/supported-sites",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Supported sites endpoint failed: {response.text}"
        data = response.json()
        
        assert "supported_sites" in data
        assert isinstance(data["supported_sites"], list)
        assert len(data["supported_sites"]) > 0
        
        # Verify structure of supported sites
        first_site = data["supported_sites"][0]
        assert "name" in first_site
        assert "domain" in first_site
        
        print(f"✅ Supported sites: {len(data['supported_sites'])} sites")


class TestStaffMinutasAccess:
    """Test that staff users can access Minutas"""
    
    def test_consultor_can_access_minutas(self):
        """Test that consultor role can access minutas endpoint"""
        # Login as consultor (if exists)
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "consultor@sistema.pt", "password": "consultor123"}
        )
        
        if login_response.status_code != 200:
            # Try another staff account
            login_response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": "staff@sistema.pt", "password": "staff123"}
            )
        
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            # Try to access minutas
            response = requests.get(
                f"{BASE_URL}/api/minutas",
                headers=headers
            )
            
            assert response.status_code == 200, f"Staff should be able to access minutas: {response.text}"
            print("✅ Staff user can access minutas endpoint")
        else:
            print("⚠️ Skipped staff minutas test - no valid staff credentials")
            pytest.skip("No valid staff credentials available")


class TestBackupAdminOnly:
    """Test that backup endpoints are admin-only"""
    
    def test_non_admin_cannot_access_backup_statistics(self):
        """Test that non-admin users cannot access backup endpoints"""
        # Try to login as a non-admin user
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "consultor@sistema.pt", "password": "consultor123"}
        )
        
        if login_response.status_code == 200:
            user_data = login_response.json()
            if user_data.get("user", {}).get("role") not in ["admin", "ceo"]:
                token = user_data.get("access_token")
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }
                
                # Try to access backup statistics - should be denied
                response = requests.get(
                    f"{BASE_URL}/api/backup/statistics",
                    headers=headers
                )
                
                # Should return 403 Forbidden
                assert response.status_code in [401, 403], f"Non-admin should not access backups: {response.status_code}"
                print("✅ Non-admin correctly denied access to backup endpoints")
            else:
                pytest.skip("User has admin/ceo role")
        else:
            pytest.skip("Could not login as non-admin user")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
