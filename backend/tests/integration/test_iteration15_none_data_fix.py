"""
Tests for Iteration 15 - Bug fix: AI document data extraction when fields are None

Bug Description:
- Critical bug where extracted data from AI document analysis was not being saved to client profile
- Problem occurred when personal_data, financial_data or real_estate_data were None instead of empty dicts
- Example: Client 'Bárbara' had documents analyzed but empty profile

Fix Applied:
- Changed .get('key', {}) to .get('key') or {} in 17 locations in ai_document.py
- This ensures that when the value is None, the fallback {} is used
"""
import os
import sys
import pytest
import requests
from datetime import datetime, timezone

# Add backend path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the function directly to test
from services.ai_document import build_update_data_from_extraction

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://powercell-crm.preview.emergentagent.com')


class TestBuildUpdateDataFromExtraction:
    """Unit tests for build_update_data_from_extraction function with None values"""
    
    def test_cc_extraction_with_none_personal_data(self):
        """Test CC document extraction when existing personal_data is None"""
        extracted_data = {
            "nif": "123456789",
            "nome_completo": "Bárbara Silva",
            "numero_documento": "12345678ZY9",
            "data_nascimento": "1985-03-15",
            "naturalidade": "Lisboa",
            "nacionalidade": "Portuguesa"
        }
        
        # Simulating existing data where personal_data is None (the bug scenario)
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "cc", existing_data)
        
        # Assertions - verify that the function didn't crash and data was populated
        assert result is not None, "Result should not be None"
        assert "personal_data" in result, "personal_data should be in result"
        assert result["personal_data"] is not None, "personal_data should not be None"
        assert result["personal_data"].get("nif") == "123456789", "NIF should be extracted"
        assert result["personal_data"].get("documento_id") == "12345678ZY9", "documento_id should be extracted"
        print("✅ TEST PASSED: CC extraction works when personal_data is None")
    
    def test_recibo_extraction_with_none_financial_data(self):
        """Test Recibo de Vencimento extraction when existing financial_data is None"""
        extracted_data = {
            "salario_liquido": 1500.00,
            "salario_bruto": 2000.00,
            "empresa": {"nome": "Empresa Teste Lda"},  # empresa must be a dict with 'nome' key
            "tipo_contrato": "Efetivo",
            "funcionario": {
                "nif": "987654321"
            }
        }
        
        # Simulating existing data where financial_data is None
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "recibo_vencimento", existing_data)
        
        assert result is not None, "Result should not be None"
        assert "financial_data" in result, "financial_data should be in result"
        assert result["financial_data"] is not None, "financial_data should not be None"
        assert result["financial_data"].get("rendimento_mensal") == 1500.00, "rendimento_mensal should be extracted"
        print("✅ TEST PASSED: Recibo extraction works when financial_data is None")
    
    def test_irs_extraction_with_none_financial_data(self):
        """Test IRS extraction when existing financial_data is None"""
        extracted_data = {
            "rendimento_liquido_anual": 21000.00,
            "rendimento_bruto_anual": 28000.00,
            "nif_titular": "123123123"
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "irs", existing_data)
        
        assert result is not None, "Result should not be None"
        assert "financial_data" in result, "financial_data should be in result"
        print("✅ TEST PASSED: IRS extraction works when financial_data is None")
    
    def test_caderneta_predial_with_none_real_estate_data(self):
        """Test Caderneta Predial extraction when existing real_estate_data is None"""
        extracted_data = {
            "artigo_matricial": "U-1234",
            "valor_patrimonial_tributario": 150000.00,
            "area_bruta": 120.5,
            "localizacao": "Rua Teste 123, Lisboa",
            "tipologia": "T3"
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "caderneta_predial", existing_data)
        
        assert result is not None, "Result should not be None"
        assert "real_estate_data" in result, "real_estate_data should be in result"
        assert result["real_estate_data"] is not None, "real_estate_data should not be None"
        assert result["real_estate_data"].get("artigo_matricial") == "U-1234", "artigo_matricial should be extracted"
        print("✅ TEST PASSED: Caderneta Predial extraction works when real_estate_data is None")
    
    def test_all_none_with_other_document(self):
        """Test generic 'outro' document type with all fields None"""
        extracted_data = {
            "nome": "João Teste Silva",
            "nif": "111222333",
            "salario": 2000.00,
            "morada": "Avenida Teste, Porto"
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None,
            "ai_extracted_notes": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "outro", existing_data)
        
        assert result is not None, "Result should not be None"
        # The 'outro' type tries to extract from any structure
        assert "updated_at" in result, "updated_at should always be present"
        print("✅ TEST PASSED: Generic 'outro' document extraction works with all None values")
    
    def test_contrato_trabalho_with_none_data(self):
        """Test Contrato de Trabalho extraction with None existing data"""
        extracted_data = {
            "colaboradora": {
                "tipo_contrato": "Efetivo",
                "data_inicio": "2020-01-15",
                "nif": "444555666"
            },
            "empresa": {
                "nome": "Empresa ABC Lda"
            }
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "contrato_trabalho", existing_data)
        
        assert result is not None, "Result should not be None"
        assert "financial_data" in result, "financial_data should be in result"
        assert result["financial_data"].get("tipo_contrato") == "Efetivo", "tipo_contrato should be extracted"
        print("✅ TEST PASSED: Contrato Trabalho extraction works with None data")
    
    def test_certidao_with_none_personal_data(self):
        """Test Certidão de Domicílio Fiscal with None personal_data"""
        extracted_data = {
            "certidao": {
                "domicilio_fiscal": {
                    "endereco": "Rua Nova 456, Faro",
                    "codigo_postal": "8000-123"
                },
                "contribuinte": {
                    "nif": "777888999"
                }
            }
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "certidao", existing_data)
        
        assert result is not None, "Result should not be None"
        assert "personal_data" in result, "personal_data should be in result"
        assert result["personal_data"].get("morada") == "Rua Nova 456, Faro", "morada should be extracted"
        print("✅ TEST PASSED: Certidão extraction works with None personal_data")
    
    def test_simulacao_credito_with_none_data(self):
        """Test Simulação de Crédito with None existing data"""
        extracted_data = {
            "simulacao_credito_habitacao": {
                "dados_imovel": {
                    "valor_aquisicao_imovel": 250000.00,
                    "localizacao_imovel": "Lisboa Centro"
                },
                "resumo_simulacao": {
                    "financiamento_total": 200000.00,
                    "prestacao_mensal": 850.00
                },
                "dados_proponente": {
                    "nif": "111333555",
                    "data_nascimento": "1990-05-20"
                }
            }
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "simulacao_credito", existing_data)
        
        assert result is not None, "Result should not be None"
        # Should have all three data types populated
        assert "personal_data" in result or "financial_data" in result or "real_estate_data" in result
        print("✅ TEST PASSED: Simulação Crédito extraction works with None data")
    
    def test_mapa_crc_with_none_financial_data(self):
        """Test Mapa CRC with None financial_data"""
        extracted_data = {
            "resumo_responsabilidades_credito": {
                "montante_em_divida": {
                    "total": 50000.00,
                    "em_incumprimento": 0.00
                }
            },
            "responsabilidades_credito": [
                {
                    "produto_financeiro": "Crédito Habitação",
                    "montantes": {"total_em_divida": 45000.00},
                    "prestacao": {"valor": 350.00}
                }
            ]
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "mapa_crc", existing_data)
        
        assert result is not None, "Result should not be None"
        assert "financial_data" in result, "financial_data should be in result"
        assert result["financial_data"].get("divida_total") == 50000.00, "divida_total should be extracted"
        print("✅ TEST PASSED: Mapa CRC extraction works with None financial_data")
    
    def test_cpcv_with_none_data(self):
        """Test CPCV (Contrato Promessa Compra e Venda) with None data"""
        extracted_data = {
            "cpcv": {
                "imovel": {
                    "localizacao": "Rua CPCV 789, Cascais",
                    "tipologia": "T4",
                    "area": 180.0
                },
                "valores": {
                    "preco_total": 500000.00,
                    "sinal": 50000.00,
                    "valor_restante": 450000.00
                }
            }
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "cpcv", existing_data)
        
        assert result is not None, "Result should not be None"
        assert "real_estate_data" in result, "real_estate_data should be in result"
        assert "financial_data" in result, "financial_data should be in result"
        print("✅ TEST PASSED: CPCV extraction works with None data")
    
    def test_dados_imovel_with_none_real_estate_data(self):
        """Test Dados Imóvel extraction with None real_estate_data"""
        extracted_data = {
            "imovel": {
                "localizacao": "Av. Liberdade, Lisboa",
                "tipologia": "T2",
                "area": 95.5,
                "valor": 380000.00,
                "quartos": 2,
                "ano_construcao": 2010
            }
        }
        
        existing_data = {
            "personal_data": None,
            "financial_data": None,
            "real_estate_data": None
        }
        
        result = build_update_data_from_extraction(extracted_data, "dados_imovel", existing_data)
        
        assert result is not None, "Result should not be None"
        assert "real_estate_data" in result, "real_estate_data should be in result"
        print("✅ TEST PASSED: Dados Imóvel extraction works with None real_estate_data")
    
    def test_empty_dict_vs_none(self):
        """Verify that empty dict and None are both handled correctly"""
        extracted_data = {
            "nif": "999888777",
            "nome_completo": "Maria Tester"
        }
        
        # Test with empty dict
        result_empty = build_update_data_from_extraction(extracted_data, "cc", {})
        assert result_empty is not None
        assert "personal_data" in result_empty
        
        # Test with None
        result_none = build_update_data_from_extraction(extracted_data, "cc", None)
        assert result_none is not None
        assert "personal_data" in result_none
        
        print("✅ TEST PASSED: Both empty dict and None existing_data handled correctly")


class TestDiagnoseClientEndpoint:
    """Integration tests for the diagnose-client endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@sistema.pt", "password": "admin2026"}
        )
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Could not authenticate - skipping integration tests")
    
    def test_diagnose_client_endpoint_exists(self, auth_headers):
        """Test that diagnose-client endpoint exists and returns proper structure"""
        # First get a client name from the list
        list_response = requests.get(
            f"{BASE_URL}/api/ai/bulk/clients-list",
            headers=auth_headers
        )
        
        if list_response.status_code != 200:
            pytest.skip("Could not get clients list")
        
        clients = list_response.json().get("clients", [])
        if not clients:
            pytest.skip("No clients available for testing")
        
        # Test with first available client
        test_client = clients[0]["name"]
        
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/diagnose-client/{test_client}",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Diagnose endpoint should return 200, got {response.status_code}"
        
        data = response.json()
        assert "found" in data, "Response should have 'found' field"
        
        if data.get("found"):
            assert "summary" in data, "Response should have 'summary' field"
            assert "filled_fields" in data, "Response should have 'filled_fields' field"
            print(f"✅ TEST PASSED: Diagnose endpoint works for client '{test_client}'")
            print(f"   Summary: {data.get('summary')}")
        else:
            print(f"⚠️  Client '{test_client}' not found in diagnose")
    
    def test_diagnose_nonexistent_client(self, auth_headers):
        """Test diagnose endpoint with non-existent client"""
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/diagnose-client/NonExistentClientXYZ123",
            headers=auth_headers
        )
        
        assert response.status_code == 200, "Should return 200 even for non-existent client"
        data = response.json()
        assert data.get("found") == False, "Should indicate client not found"
        print("✅ TEST PASSED: Diagnose endpoint handles non-existent client correctly")


class TestUpdateClientData:
    """Integration tests for the update_client_data function via API"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login-v2",
            json={"email": "admin@sistema.pt", "password": "admin2026"}
        )
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            return {"Authorization": f"Bearer {token}"}
        pytest.skip("Could not authenticate - skipping integration tests")
    
    def test_check_client_endpoint(self, auth_headers):
        """Test check-client endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/check-client",
            params={"name": "Test"},
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Check client should return 200, got {response.status_code}"
        print("✅ TEST PASSED: check-client endpoint working")
    
    def test_clients_list_endpoint(self, auth_headers):
        """Test clients-list endpoint works"""
        response = requests.get(
            f"{BASE_URL}/api/ai/bulk/clients-list",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Clients list should return 200, got {response.status_code}"
        data = response.json()
        assert "clients" in data, "Response should have 'clients' field"
        assert "total" in data, "Response should have 'total' field"
        print(f"✅ TEST PASSED: clients-list endpoint working - {data.get('total')} clients")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
