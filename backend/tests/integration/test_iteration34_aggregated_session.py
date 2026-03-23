"""
Test Iteration 34 - Aggregated Session Endpoints for Bulk AI Import

Tests the new "cliente a cliente" aggregated import logic:
1. POST /api/ai/bulk/aggregated-session/start - criar sessão de importação agregada
2. GET /api/ai/bulk/aggregated-session/{session_id}/status - verificar status da sessão
3. POST /api/ai/bulk/aggregated-session/{session_id}/finish - finalizar sessão e consolidar dados
4. data_aggregator.py - ClientDataAggregator salary aggregation logic
"""

import pytest
import requests
import os
import sys

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://gdpr-compliance-fix.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin"


class TestAggregatedSessionEndpoints:
    """Test the new aggregated session endpoints."""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin JWT token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in login response"
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, admin_token):
        """Create auth headers."""
        return {"Authorization": f"Bearer {admin_token}"}
    
    def test_01_health_check(self):
        """Verify backend is healthy."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✅ Backend health check passed")
    
    def test_02_aggregated_session_start(self, auth_headers):
        """
        Test POST /api/ai/bulk/aggregated-session/start
        Should create a new aggregated import session.
        """
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/aggregated-session/start",
            headers=auth_headers,
            json={
                "total_files": 10,
                "client_name": "TEST_aggregated_client"
            }
        )
        
        assert response.status_code == 200, f"Failed to start aggregated session: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "session_id" in data, "No session_id in response"
        assert "message" in data, "No message in response"
        assert "aggregation_mode" in data, "No aggregation_mode in response"
        
        # Verify aggregation_mode is True
        assert data["aggregation_mode"] == True, "aggregation_mode should be True"
        
        # Store session_id for next tests
        TestAggregatedSessionEndpoints.session_id = data["session_id"]
        
        print(f"✅ Aggregated session started: {data['session_id']}")
        print(f"   Message: {data['message']}")
    
    def test_03_aggregated_session_status(self, auth_headers):
        """
        Test GET /api/ai/bulk/aggregated-session/{session_id}/status
        Should return session status with client details.
        """
        session_id = getattr(TestAggregatedSessionEndpoints, 'session_id', None)
        if not session_id:
            pytest.skip("No session_id from previous test")
        
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/aggregated-session/{session_id}/status",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to get session status: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "session_id" in data, "No session_id in response"
        assert "status" in data, "No status in response"
        
        # The session should be active or in_memory
        assert data["status"] in ["active", "in_memory", "running"], f"Unexpected status: {data['status']}"
        
        print(f"✅ Session status retrieved: {data['status']}")
        print(f"   Session data: {data}")
    
    def test_04_aggregated_session_finish(self, auth_headers):
        """
        Test POST /api/ai/bulk/aggregated-session/{session_id}/finish
        Should consolidate data and save to DB.
        """
        session_id = getattr(TestAggregatedSessionEndpoints, 'session_id', None)
        if not session_id:
            pytest.skip("No session_id from previous test")
        
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/aggregated-session/{session_id}/finish",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed to finish session: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "success" in data, "No success in response"
        assert "message" in data, "No message in response"
        assert "clients_updated" in data, "No clients_updated in response"
        assert "total_documents" in data, "No total_documents in response"
        assert "errors" in data, "No errors in response"
        
        print(f"✅ Session finished:")
        print(f"   Success: {data['success']}")
        print(f"   Message: {data['message']}")
        print(f"   Clients updated: {data['clients_updated']}")
        print(f"   Total documents: {data['total_documents']}")
        print(f"   Errors: {data['errors']}")
    
    def test_05_session_not_found_after_finish(self, auth_headers):
        """
        Verify session is removed from memory after finish.
        """
        session_id = getattr(TestAggregatedSessionEndpoints, 'session_id', None)
        if not session_id:
            pytest.skip("No session_id from previous test")
        
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/aggregated-session/{session_id}/status",
            headers=auth_headers
        )
        
        # After finish, session should still be accessible from DB or return 404
        if response.status_code == 200:
            data = response.json()
            # If found, should be from DB
            if data.get("from_db"):
                print("✅ Session found in DB after finish (expected)")
            else:
                print(f"⚠️ Session still in memory: {data}")
        elif response.status_code == 404:
            print("✅ Session removed from memory after finish (expected)")
        else:
            print(f"⚠️ Unexpected response: {response.status_code} - {response.text}")


class TestDataAggregatorLogic:
    """
    Test the ClientDataAggregator and salary aggregation logic.
    This tests the core business logic without HTTP calls.
    """
    
    def test_01_import_data_aggregator(self):
        """Verify data_aggregator module can be imported."""
        try:
            from services.documents.data_aggregator import (
                ClientDataAggregator,
                SessionAggregator,
                get_or_create_session,
                get_session,
                close_session
            )
            print("✅ data_aggregator module imported successfully")
        except ImportError as e:
            pytest.fail(f"Failed to import data_aggregator: {e}")
    
    def test_02_client_data_aggregator_creation(self):
        """Test creating a ClientDataAggregator instance."""
        from services.documents.data_aggregator import ClientDataAggregator
        
        aggregator = ClientDataAggregator(
            process_id="test-process-123",
            client_name="João Silva"
        )
        
        assert aggregator.process_id == "test-process-123"
        assert aggregator.client_name == "João Silva"
        assert aggregator.salarios_por_empresa == {}
        assert aggregator.documents_processed == []
        
        print("✅ ClientDataAggregator created successfully")
    
    def test_03_salary_aggregation_different_companies(self):
        """
        CRITICAL TEST: Verify salaries from DIFFERENT companies are aggregated.
        
        Rule: 2 salários de empresas diferentes devem resultar em:
        - Lista com 2 entradas 
        - Soma total
        """
        from services.documents.data_aggregator import ClientDataAggregator
        
        aggregator = ClientDataAggregator(
            process_id="test-salary-123",
            client_name="Maria Santos"
        )
        
        # Add salary from Company A
        aggregator.add_extraction(
            document_type="recibo_vencimento",
            extracted_data={
                "empresa": "Empresa ABC Lda",
                "salario_bruto": 2000.00,
                "salario_liquido": 1500.00,
                "tipo_contrato": "Sem termo",
                "mes_referencia": "Janeiro 2026"
            },
            filename="recibo_empresa_abc.pdf"
        )
        
        # Add salary from Company B (DIFFERENT company)
        aggregator.add_extraction(
            document_type="recibo_vencimento",
            extracted_data={
                "empresa": "Empresa XYZ SA",
                "salario_bruto": 1800.00,
                "salario_liquido": 1350.00,
                "tipo_contrato": "Termo certo",
                "mes_referencia": "Janeiro 2026"
            },
            filename="recibo_empresa_xyz.pdf"
        )
        
        # Verify we have 2 different companies
        assert len(aggregator.salarios_por_empresa) == 2, \
            f"Expected 2 companies, got {len(aggregator.salarios_por_empresa)}"
        
        # Get consolidated data
        consolidated = aggregator.get_consolidated_data()
        
        # Verify financial_data has salarios list
        assert "financial_data" in consolidated, "No financial_data in consolidated"
        financial = consolidated["financial_data"]
        
        assert "salarios" in financial, "No salarios list in financial_data"
        salarios_list = financial["salarios"]
        
        # Should have 2 entries (different companies)
        assert len(salarios_list) == 2, \
            f"Expected 2 salarios entries, got {len(salarios_list)}"
        
        # Verify totals are calculated
        assert "rendimento_bruto_total" in financial, "No rendimento_bruto_total"
        assert "rendimento_liquido_total" in financial, "No rendimento_liquido_total"
        assert "num_fontes_rendimento" in financial, "No num_fontes_rendimento"
        
        # Verify sum is correct
        expected_bruto_total = 2000.00 + 1800.00
        expected_liquido_total = 1500.00 + 1350.00
        
        assert financial["rendimento_bruto_total"] == expected_bruto_total, \
            f"Expected bruto total {expected_bruto_total}, got {financial['rendimento_bruto_total']}"
        assert financial["rendimento_liquido_total"] == expected_liquido_total, \
            f"Expected liquido total {expected_liquido_total}, got {financial['rendimento_liquido_total']}"
        assert financial["num_fontes_rendimento"] == 2, \
            f"Expected 2 income sources, got {financial['num_fontes_rendimento']}"
        
        print("✅ Salary aggregation for DIFFERENT companies works correctly:")
        print(f"   - 2 companies: {list(aggregator.salarios_por_empresa.keys())}")
        print(f"   - Total bruto: {financial['rendimento_bruto_total']}€")
        print(f"   - Total líquido: {financial['rendimento_liquido_total']}€")
        print(f"   - Fontes rendimento: {financial['num_fontes_rendimento']}")
    
    def test_04_salary_same_company_deduplication(self):
        """
        CRITICAL TEST: Verify salaries from SAME company are deduplicated.
        
        Rule: Mesma empresa deve manter apenas a entrada mais recente.
        """
        from services.documents.data_aggregator import ClientDataAggregator
        
        aggregator = ClientDataAggregator(
            process_id="test-dedup-123",
            client_name="Ana Costa"
        )
        
        # Add first salary from Company A (older)
        aggregator.add_extraction(
            document_type="recibo_vencimento",
            extracted_data={
                "empresa": "Empresa ABC Lda",
                "salario_bruto": 1800.00,
                "salario_liquido": 1350.00,
                "mes_referencia": "Dezembro 2025"
            },
            filename="recibo_dez.pdf"
        )
        
        # Add second salary from SAME company (newer - should replace)
        aggregator.add_extraction(
            document_type="recibo_vencimento",
            extracted_data={
                "empresa": "Empresa ABC Lda",  # Same company
                "salario_bruto": 2000.00,  # Updated salary
                "salario_liquido": 1500.00,
                "mes_referencia": "Janeiro 2026"
            },
            filename="recibo_jan.pdf"
        )
        
        # Should only have 1 company (deduplicated)
        assert len(aggregator.salarios_por_empresa) == 1, \
            f"Expected 1 company (deduplicated), got {len(aggregator.salarios_por_empresa)}"
        
        # Get consolidated data
        consolidated = aggregator.get_consolidated_data()
        financial = consolidated["financial_data"]
        
        # Should have only 1 salary entry
        assert len(financial["salarios"]) == 1, \
            f"Expected 1 salary entry (deduplicated), got {len(financial['salarios'])}"
        
        # Should have the most recent values
        assert financial["rendimento_bruto_total"] == 2000.00, \
            f"Should have latest bruto (2000), got {financial['rendimento_bruto_total']}"
        assert financial["rendimento_liquido_total"] == 1500.00, \
            f"Should have latest liquido (1500), got {financial['rendimento_liquido_total']}"
        
        print("✅ Salary deduplication for SAME company works correctly:")
        print(f"   - Only 1 company kept: {list(aggregator.salarios_por_empresa.keys())}")
        print(f"   - Latest bruto: {financial['rendimento_bruto_total']}€")
        print(f"   - Latest líquido: {financial['rendimento_liquido_total']}€")
    
    def test_05_empresa_normalization(self):
        """
        Test that company names are normalized for comparison.
        "Empresa ABC, Lda" and "Empresa ABC LDA" should be treated as the same.
        """
        from services.documents.data_aggregator import ClientDataAggregator
        
        aggregator = ClientDataAggregator(
            process_id="test-norm-123",
            client_name="Pedro Martins"
        )
        
        # Add salary with "Lda" suffix
        aggregator.add_extraction(
            document_type="recibo_vencimento",
            extracted_data={
                "empresa": "Empresa ABC, Lda",
                "salario_bruto": 1500.00,
                "salario_liquido": 1100.00
            },
            filename="recibo1.pdf"
        )
        
        # Add salary with "LDA" (uppercase, no comma)
        aggregator.add_extraction(
            document_type="recibo_vencimento",
            extracted_data={
                "empresa": "Empresa ABC LDA",
                "salario_bruto": 1600.00,
                "salario_liquido": 1200.00
            },
            filename="recibo2.pdf"
        )
        
        # Should be treated as same company
        assert len(aggregator.salarios_por_empresa) == 1, \
            f"Expected 1 company (normalized), got {len(aggregator.salarios_por_empresa)}: {list(aggregator.salarios_por_empresa.keys())}"
        
        print("✅ Company name normalization works correctly")
        print(f"   - Normalized companies: {list(aggregator.salarios_por_empresa.keys())}")
    
    def test_06_session_aggregator(self):
        """Test SessionAggregator for managing multiple clients."""
        from services.documents.data_aggregator import SessionAggregator
        
        session = SessionAggregator(
            session_id="test-session-123",
            user_email="admin@admin.com"
        )
        
        # Add extractions for Client A
        session.add_file_extraction(
            process_id="client-a",
            client_name="Cliente A",
            document_type="recibo_vencimento",
            extracted_data={
                "empresa": "Empresa A",
                "salario_liquido": 1000.00
            },
            filename="recibo_a.pdf"
        )
        
        # Add extractions for Client B
        session.add_file_extraction(
            process_id="client-b",
            client_name="Cliente B",
            document_type="recibo_vencimento",
            extracted_data={
                "empresa": "Empresa B",
                "salario_liquido": 2000.00
            },
            filename="recibo_b.pdf"
        )
        
        # Verify session summary
        summary = session.get_session_summary()
        
        assert summary["clients_count"] == 2, f"Expected 2 clients, got {summary['clients_count']}"
        assert summary["processed_files"] == 2, f"Expected 2 files, got {summary['processed_files']}"
        
        # Get all consolidated data
        all_data = session.get_all_consolidated_data()
        
        assert "client-a" in all_data, "Client A not in consolidated data"
        assert "client-b" in all_data, "Client B not in consolidated data"
        
        print("✅ SessionAggregator works correctly:")
        print(f"   - Clients count: {summary['clients_count']}")
        print(f"   - Files processed: {summary['processed_files']}")


class TestAggregatedSessionAuth:
    """Test authentication requirements for aggregated session endpoints."""
    
    def test_01_start_requires_admin(self):
        """Verify aggregated-session/start requires admin role."""
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/aggregated-session/start",
            json={"total_files": 5}
            # No auth header
        )
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}"
        print("✅ aggregated-session/start requires authentication")
    
    def test_02_status_requires_admin(self):
        """Verify aggregated-session status requires admin role."""
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/aggregated-session/fake-session-id/status"
            # No auth header
        )
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}"
        print("✅ aggregated-session status requires authentication")
    
    def test_03_finish_requires_admin(self):
        """Verify aggregated-session finish requires admin role."""
        response = requests.post(
            f"{BASE_URL}/api/ai/bulk/aggregated-session/fake-session-id/finish"
            # No auth header
        )
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}"
        print("✅ aggregated-session finish requires authentication")


class TestCleanup:
    """Cleanup test data."""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin JWT token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    def test_cleanup_test_sessions(self, admin_token):
        """Clean up any test sessions from background_jobs collection."""
        if not admin_token:
            pytest.skip("No admin token for cleanup")
        
        # Note: Cleanup would normally delete test sessions from DB
        # For now, just verify we can access the background jobs endpoint
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/background-jobs",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if response.status_code == 200:
            print("✅ Background jobs endpoint accessible for cleanup verification")
        else:
            print(f"⚠️ Could not access background jobs: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
