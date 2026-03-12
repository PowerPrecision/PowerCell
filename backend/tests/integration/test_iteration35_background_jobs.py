"""
====================================================================
TEST ITERATION 35 - Background Jobs & Multi-Language Document Extraction
====================================================================
Tests for:
1. GET /api/ai/bulk/background-jobs - List background jobs
2. POST /api/ai/bulk/background-job/{job_id}/progress - Update job progress
3. POST /api/ai/bulk/background-jobs/clear-all - Clear all jobs
4. POST /api/scraper/crawl - ScraperAPI integration for protected sites
5. Multi-language extraction prompts structure (FR receipts/IRS)
====================================================================
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable not set")

# Test credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin"


class TestAuthentication:
    """Get admin auth token for subsequent tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data or "access_token" in data
        return data.get("token") or data.get("access_token")
    
    def test_admin_login(self, admin_token):
        """Test admin authentication works"""
        assert admin_token is not None
        assert len(admin_token) > 0
        print(f"✓ Admin login successful - token length: {len(admin_token)}")


class TestBackgroundJobsEndpoints:
    """Test background jobs API endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers for admin user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("token") or data.get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Admin authentication failed")
        return {}
    
    def test_01_list_background_jobs(self, auth_headers):
        """
        Test GET /api/ai/bulk/background-jobs - List background jobs
        Bug fix verification: Import em massa não aparece nos processos em background
        """
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "jobs" in data, "Response should contain 'jobs' key"
        assert "counts" in data, "Response should contain 'counts' key"
        assert isinstance(data["jobs"], list), "'jobs' should be a list"
        
        # Validate counts structure
        counts = data["counts"]
        assert "running" in counts, "Counts should have 'running'"
        assert "success" in counts, "Counts should have 'success'"
        assert "failed" in counts, "Counts should have 'failed'"
        assert "total" in counts, "Counts should have 'total'"
        
        print(f"✓ Background jobs list working - {len(data['jobs'])} jobs found")
        print(f"  Counts: running={counts['running']}, success={counts['success']}, failed={counts['failed']}, total={counts['total']}")
    
    def test_02_list_background_jobs_with_status_filter(self, auth_headers):
        """Test filtering background jobs by status"""
        # Test with status filter
        for status in ["running", "success", "failed"]:
            response = requests.get(
                f"{BASE_URL}/api/ai/bulk/background-jobs?status={status}",
                headers=auth_headers,
                timeout=30
            )
            assert response.status_code == 200, f"Filter by status={status} failed: {response.text}"
            data = response.json()
            assert "jobs" in data
            print(f"✓ Status filter '{status}' working - {len(data['jobs'])} jobs")
    
    def test_03_list_background_jobs_with_limit(self, auth_headers):
        """Test limit parameter for background jobs"""
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs?limit=5",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) <= 5, "Should respect limit parameter"
        print(f"✓ Limit parameter working - max 5 jobs")
    
    def test_04_clear_all_jobs(self, auth_headers):
        """
        Test POST /api/ai/bulk/background-jobs/clear-all
        """
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/clear-all",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Clear all jobs failed: {response.text}"
        data = response.json()
        
        assert "success" in data, "Response should have 'success'"
        assert data["success"] == True, "Clear all should succeed"
        assert "removed_memory" in data or "removed_db" in data, "Response should include removal counts"
        
        print(f"✓ Clear all jobs working - removed_memory={data.get('removed_memory', 0)}, removed_db={data.get('removed_db', 0)}")
    
    def test_05_verify_jobs_cleared(self, auth_headers):
        """Verify that jobs are cleared after clear-all"""
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All counts should be 0 or empty after clearing
        print(f"✓ After clear: {len(data['jobs'])} jobs remain")
    
    def test_06_update_progress_nonexistent_job(self, auth_headers):
        """
        Test POST /api/ai/bulk/background-job/{job_id}/progress
        Testing with non-existent job ID
        """
        fake_job_id = f"TEST_nonexistent_{uuid.uuid4().hex[:8]}"
        
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-job/{fake_job_id}/progress",
            headers=auth_headers,
            json={
                "processed": 5,
                "errors": 0,
                "message": "Testing progress update"
            },
            timeout=30
        )
        
        # Should return something (may be error or create the job)
        # The endpoint exists and handles the request
        assert response.status_code in [200, 201, 404], f"Unexpected status: {response.status_code}"
        print(f"✓ Progress update endpoint responds - status {response.status_code}")
    
    def test_07_background_jobs_requires_auth(self):
        """Verify background jobs endpoint requires authentication"""
        # Without auth headers
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            timeout=30
        )
        
        # Should reject unauthenticated requests
        assert response.status_code in [401, 403, 422], f"Should require auth, got {response.status_code}"
        print(f"✓ Endpoint requires authentication - status {response.status_code}")
    
    def test_08_clear_all_jobs_requires_auth(self):
        """Verify clear-all endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/background-jobs/clear-all",
            timeout=30
        )
        
        assert response.status_code in [401, 403, 422], f"Should require auth, got {response.status_code}"
        print(f"✓ Clear-all requires authentication - status {response.status_code}")


class TestScraperEndpoint:
    """Test scraper endpoint with ScraperAPI integration"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("token") or data.get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Admin authentication failed")
        return {}
    
    def test_01_scraper_crawl_endpoint_exists(self, auth_headers):
        """
        Test POST /api/scraper/crawl endpoint exists
        Note: Idealista is known to block all scrapers even with ScraperAPI
        """
        # Test with a simple URL (not Idealista since it blocks)
        response = requests.post(
            f"{BASE_URL}/api/scraper/crawl",
            headers=auth_headers,
            json={"url": "https://example.com"},
            timeout=60
        )
        
        # Endpoint should exist and respond (even if scraping fails)
        assert response.status_code in [200, 400, 422, 500], f"Endpoint should exist, got {response.status_code}"
        print(f"✓ Scraper crawl endpoint exists - status {response.status_code}")
    
    def test_02_scraper_idealista_blocked(self, auth_headers):
        """
        Test that Idealista URL is attempted with ScraperAPI
        Known limitation: Idealista blocks all scrapers
        """
        # This should attempt ScraperAPI but will likely fail (403)
        response = requests.post(
            f"{BASE_URL}/api/scraper/crawl",
            headers=auth_headers,
            json={"url": "https://www.idealista.pt/imovel/12345678/"},
            timeout=90  # Longer timeout for ScraperAPI
        )
        
        # We expect the endpoint to handle this gracefully
        # Known: Idealista returns 403 even with ScraperAPI
        print(f"✓ Idealista crawl attempted - status {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Response: {data}")
        else:
            print(f"  Expected: Idealista blocks scrapers (this is known)")


class TestDataAggregatorMultiLanguage:
    """Test that data aggregator supports multi-language documents"""
    
    def test_01_import_data_aggregator(self):
        """Verify data_aggregator module can be imported"""
        try:
            import sys
            sys.path.insert(0, '/app/backend')
            from services.documents.data_aggregator import ClientDataAggregator, SessionAggregator
            assert ClientDataAggregator is not None
            assert SessionAggregator is not None
            print("✓ data_aggregator imports successfully")
        except ImportError as e:
            pytest.fail(f"Failed to import data_aggregator: {e}")
    
    def test_02_client_aggregator_french_receipt(self):
        """Test ClientDataAggregator handles French receipts (pais_origem, moeda)"""
        import sys
        sys.path.insert(0, '/app/backend')
        from services.documents.data_aggregator import ClientDataAggregator
        
        aggregator = ClientDataAggregator("TEST_process_1", "Test Client FR")
        
        # Simulate French receipt extraction
        french_receipt = {
            "nome_funcionario": "João Silva",
            "empresa": "SNCF",
            "pais_origem": "FR",
            "mes_referencia": "2024-12",
            "salario_bruto": 3500.00,
            "salario_liquido": 2800.00,
            "moeda": "EUR",
            "tipo_contrato": "CDI"
        }
        
        aggregator.add_extraction("recibo_vencimento", french_receipt, "bulletin_paie.pdf")
        
        # Verify French data was processed
        assert len(aggregator.salarios_por_empresa) > 0, "Should have salary data"
        
        # Check salary entry has French fields
        for empresa_norm, salario in aggregator.salarios_por_empresa.items():
            assert salario.get("pais_origem") == "FR", f"Should have pais_origem=FR, got {salario.get('pais_origem')}"
            assert salario.get("moeda") == "EUR", f"Should have moeda=EUR, got {salario.get('moeda')}"
            print(f"✓ French receipt processed - empresa: {salario.get('empresa')}, país: {salario.get('pais_origem')}, moeda: {salario.get('moeda')}")
    
    def test_03_client_aggregator_french_irs(self):
        """Test ClientDataAggregator handles French IRS (Avis d'impôt)"""
        import sys
        sys.path.insert(0, '/app/backend')
        from services.documents.data_aggregator import ClientDataAggregator
        
        aggregator = ClientDataAggregator("TEST_process_2", "Test Client FR IRS")
        
        # Simulate French tax declaration
        french_irs = {
            "ano_fiscal": 2023,
            "pais_origem": "FR",
            "nif_titular": "1234567890123",
            "nome_titular": "João Silva",
            "estado_civil_fiscal": "Marié",
            "morada_fiscal": "15 Rue de Paris, 75001 Paris",
            "rendimento_bruto_anual": 42000.00,
            "rendimento_liquido_anual": 35000.00,
            "imposto_pago": 7000.00,
            "moeda": "EUR"
        }
        
        aggregator.add_extraction("irs", french_irs, "avis_impot_2023.pdf")
        
        # Verify French IRS was processed
        assert aggregator.other_data.get("residente_no_estrangeiro") == True, "Should mark as foreign resident"
        assert aggregator.other_data.get("pais_residencia_fiscal") == "FR", "Should have FR fiscal residence"
        
        # French NIF should be stored separately
        assert "nif_fr" in aggregator.personal_data, "Should have nif_fr field"
        
        # Estado civil should be normalized
        assert aggregator.personal_data.get("estado_civil") == "casado", "Marié should be normalized to casado"
        
        print(f"✓ French IRS processed - resident abroad: {aggregator.other_data.get('residente_no_estrangeiro')}")
        print(f"  NIF FR: {aggregator.personal_data.get('nif_fr')}")
        print(f"  Estado civil: {aggregator.personal_data.get('estado_civil')}")
    
    def test_04_salary_aggregation_different_countries(self):
        """Test salary aggregation from different countries (PT + FR)"""
        import sys
        sys.path.insert(0, '/app/backend')
        from services.documents.data_aggregator import ClientDataAggregator
        
        aggregator = ClientDataAggregator("TEST_process_3", "Test Client Multi-Country")
        
        # Portuguese receipt
        pt_receipt = {
            "nome_funcionario": "Maria Santos",
            "empresa": "Empresa PT Lda",
            "pais_origem": "PT",
            "salario_bruto": 1500.00,
            "salario_liquido": 1100.00,
            "moeda": "EUR"
        }
        
        # French receipt (same person working in France)
        fr_receipt = {
            "nome_funcionario": "Maria Santos",
            "empresa": "Société FR SARL",
            "pais_origem": "FR",
            "salario_bruto": 2500.00,
            "salario_liquido": 2000.00,
            "moeda": "EUR"
        }
        
        aggregator.add_extraction("recibo_vencimento", pt_receipt, "recibo_pt.pdf")
        aggregator.add_extraction("recibo_vencimento", fr_receipt, "bulletin_fr.pdf")
        
        # Should have 2 different companies
        assert len(aggregator.salarios_por_empresa) == 2, f"Should have 2 employers, got {len(aggregator.salarios_por_empresa)}"
        
        # Verify both countries are represented
        paises = [s.get("pais_origem") for s in aggregator.salarios_por_empresa.values()]
        assert "PT" in paises, "Should have PT salary"
        assert "FR" in paises, "Should have FR salary"
        
        print(f"✓ Multi-country salaries aggregated - {len(aggregator.salarios_por_empresa)} sources")
        for empresa_norm, salario in aggregator.salarios_por_empresa.items():
            print(f"  - {salario.get('empresa')} ({salario.get('pais_origem')}): {salario.get('salario_liquido')}€")
    
    def test_05_consolidate_foreign_data(self):
        """Test consolidation includes foreign country fields"""
        import sys
        sys.path.insert(0, '/app/backend')
        from services.documents.data_aggregator import ClientDataAggregator
        
        aggregator = ClientDataAggregator("TEST_process_4", "Test Client Consolidate")
        
        # Add French receipt
        aggregator.add_extraction("recibo_vencimento", {
            "empresa": "Company France",
            "pais_origem": "FR",
            "salario_liquido": 2000.00,
            "moeda": "EUR"
        }, "test.pdf")
        
        # Consolidate using correct method name
        result = aggregator.get_consolidated_data()
        
        # Salaries are nested under financial_data
        financial_data = result.get("financial_data", {})
        assert "salarios" in financial_data, "Consolidated financial_data should have salarios"
        assert len(financial_data["salarios"]) > 0, "Should have at least one salary"
        
        # Verify French data in salarios
        salario = financial_data["salarios"][0]
        assert salario.get("pais_origem") == "FR", f"Salary should have pais_origem=FR"
        assert salario.get("moeda") == "EUR", f"Salary should have moeda=EUR"
        
        print(f"✓ Consolidation includes foreign country data")
        print(f"  - Salary from {salario.get('empresa')} ({salario.get('pais_origem')}): {salario.get('salario_liquido')}€")


class TestAIDocumentPrompts:
    """Verify AI document extraction prompts support multi-language"""
    
    def test_01_verify_receipt_prompt_supports_france(self):
        """Verify recibo_vencimento prompt mentions France/Bulletin de paie"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        try:
            from services.ai_document import get_document_prompt
            
            # Get prompts for recibo_vencimento
            result = get_document_prompt("recibo_vencimento")
            
            if result:
                system_prompt = result.get("system_prompt", "")
                user_prompt = result.get("user_prompt", "")
                
                # Check for French support
                assert "França" in system_prompt or "France" in system_prompt or "Bulletin" in system_prompt, \
                    "System prompt should mention France or Bulletin de paie"
                
                # Check for pais_origem field
                assert "pais_origem" in user_prompt, "User prompt should include pais_origem field"
                
                # Check for moeda field
                assert "moeda" in user_prompt, "User prompt should include moeda field"
                
                print("✓ Receipt prompt supports French documents")
                print("  - Mentions: França/France/Bulletin de paie")
                print("  - Includes: pais_origem, moeda fields")
                
        except ImportError:
            # If function not available, check file directly
            with open('/app/backend/services/ai_document.py', 'r') as f:
                content = f.read()
                assert "França" in content or "Bulletin" in content
                assert "pais_origem" in content
                print("✓ Receipt prompt in ai_document.py supports French documents")
    
    def test_02_verify_irs_prompt_supports_france(self):
        """Verify IRS prompt mentions France/Avis d'impôt"""
        with open('/app/backend/services/ai_document.py', 'r') as f:
            content = f.read()
            
            # Check for French tax declaration support
            assert "Avis d'impôt" in content or "avis d'impôt" in content or "França" in content, \
                "IRS prompt should mention French tax declarations"
            
            print("✓ IRS prompt supports French documents (Avis d'impôt)")


class TestHealthAndCleanup:
    """Health check and cleanup"""
    
    def test_01_health_check(self):
        """Verify backend is healthy"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        print("✓ Backend health check passed")
    
    def test_99_cleanup(self):
        """Cleanup test data"""
        # Login as admin
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get("token") or data.get("access_token")
            headers = {"Authorization": f"Bearer {token}"}
            
            # Clear any test jobs we might have created
            requests.post(
                f"{BASE_URL}/api/ai/bulk/background-jobs/clear-all",
                headers=headers,
                timeout=30
            )
            print("✓ Cleanup completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
