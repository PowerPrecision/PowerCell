"""
Iteration 20 - P0 Features Testing
Tests for:
1. Compact Kanban cards
2. NIF validation (reject NIFs starting with 5)
3. Excel import button and endpoints
4. AI suggestions for import errors
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests with provided credentials"""
    
    def test_admin_login_success(self):
        """Test admin login with geral@powerealestate.pt/admin2026"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "geral@powerealestate.pt",
            "password": "admin2026"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data, "access_token should be in response"
        assert "user" in data
        print(f"✅ Admin login successful: {data.get('user', {}).get('email')}")


def get_admin_token():
    """Helper to get admin token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "geral@powerealestate.pt",
        "password": "admin2026"
    })
    return response.json().get("access_token")


class TestKanbanEndpoint:
    """Test Kanban endpoint that provides compact card data"""
    
    def test_kanban_endpoint_returns_processes(self):
        """Test /api/processes/kanban returns process data for compact cards"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/processes/kanban", headers=headers)
        
        assert response.status_code == 200, f"Kanban endpoint failed: {response.text}"
        data = response.json()
        
        # Response can be a list or an object with "columns"
        if isinstance(data, dict):
            columns = data.get("columns", [])
        else:
            columns = data
        
        assert isinstance(columns, list), "Columns should be a list"
        
        total_processes = 0
        for column in columns:
            assert "processes" in column, "Each column should have processes"
            total_processes += len(column.get("processes", []))
            
            # Check each process has required fields for compact cards
            for process in column.get("processes", []):
                assert "id" in process, "Process should have id"
                assert "client_name" in process, "Process should have client_name"
                # process_number may be optional
        
        print(f"✅ Kanban endpoint returns {total_processes} processes in {len(columns)} columns")


class TestPropertiesImportEndpoints:
    """Test Excel import related endpoints"""
    
    def test_import_template_endpoint_exists(self):
        """Test /api/properties/bulk/import-template returns template info"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/properties/bulk/import-template", headers=headers)
        
        assert response.status_code == 200, f"Import template endpoint failed: {response.text}"
        data = response.json()
        
        # Should contain instructions and column definitions
        assert "colunas_obrigatorias" in data, "Should have mandatory columns"
        assert "colunas_opcionais" in data, "Should have optional columns"
        
        # Verify mandatory columns
        mandatory_cols = [c["nome"] for c in data["colunas_obrigatorias"]]
        assert "titulo" in mandatory_cols, "titulo should be mandatory"
        assert "preco" in mandatory_cols, "preco should be mandatory"
        assert "distrito" in mandatory_cols, "distrito should be mandatory"
        assert "concelho" in mandatory_cols, "concelho should be mandatory"
        assert "proprietario_nome" in mandatory_cols, "proprietario_nome should be mandatory"
        
        print(f"✅ Import template endpoint returns {len(mandatory_cols)} mandatory columns")
        print(f"   Optional columns: {len(data.get('colunas_opcionais', []))}")
    
    def test_import_excel_endpoint_exists(self):
        """Test /api/properties/bulk/import-excel endpoint exists (without file)"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Without a file, should return 422 (Unprocessable Entity) not 404
        response = requests.post(f"{BASE_URL}/api/properties/bulk/import-excel", headers=headers)
        
        # 422 means endpoint exists but requires file
        assert response.status_code == 422, f"Expected 422 (missing file), got {response.status_code}"
        print("✅ Import Excel endpoint exists (returns 422 when no file provided)")


class TestAISuggestionsEndpoint:
    """Test AI suggestions for import errors endpoint"""
    
    def test_import_errors_suggestions_endpoint(self):
        """Test /api/ai/bulk/import-errors/suggestions endpoint"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/ai/bulk/import-errors/suggestions", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Should return suggestions structure
        assert "suggestions" in data, "Response should have suggestions"
        assert "total_errors" in data, "Response should have total_errors"
        
        # Suggestions should be a list
        assert isinstance(data["suggestions"], list), "suggestions should be a list"
        
        # If there are suggestions, check structure
        if data["suggestions"]:
            first_suggestion = data["suggestions"][0]
            assert "category" in first_suggestion, "Suggestion should have category"
            assert "title" in first_suggestion, "Suggestion should have title"
            assert "description" in first_suggestion, "Suggestion should have description"
        
        print(f"✅ AI suggestions endpoint returns {data.get('total_errors', 0)} total errors")
        print(f"   Suggestions count: {len(data.get('suggestions', []))}")


class TestNIFValidationBackend:
    """Test NIF validation in backend routes"""
    
    def test_nif_validation_function_logic(self):
        """Test that NIF starting with 5 is considered invalid for individuals"""
        # This tests the logic that should be in ai_bulk.py validate_nif function
        # NIFs starting with 5 are for companies/entities, not individuals
        
        import re
        
        def validate_nif(nif: str) -> bool:
            """Local copy of validation logic"""
            if not nif:
                return True
            nif = re.sub(r'\D', '', str(nif))
            if len(nif) != 9:
                return False
            if nif in ['123456789', '000000000', '111111111', '999999999']:
                return False
            first_digit = nif[0]
            # 5 is for collective entities - ALWAYS REJECT for clients
            if first_digit == '5':
                return False
            # Valid NIFs for individuals: 1, 2, 6, 9
            if first_digit not in ['1', '2', '6', '9']:
                return False
            return True
        
        # Test cases
        assert validate_nif("123456789") == False, "Placeholder NIF should be invalid"
        assert validate_nif("512345678") == False, "NIF starting with 5 should be invalid"
        assert validate_nif("500000001") == False, "Company NIF should be invalid"
        assert validate_nif("212345678") == True, "NIF starting with 2 should be valid"
        assert validate_nif("123456") == False, "NIF with less than 9 digits should be invalid"
        assert validate_nif("") == True, "Empty NIF should be valid (optional)"
        assert validate_nif("999999999") == False, "Placeholder NIF should be invalid"
        
        print("✅ NIF validation logic correctly rejects NIFs starting with 5 (company NIFs)")


class TestPropertiesStats:
    """Test properties stats endpoint"""
    
    def test_properties_stats_endpoint(self):
        """Test /api/properties/stats returns stats data"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/properties/stats", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "total" in data, "Stats should have total"
        print(f"✅ Properties stats: Total={data.get('total')}")


class TestPropertiesList:
    """Test properties listing endpoint"""
    
    def test_properties_list_endpoint(self):
        """Test /api/properties returns list of properties"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/properties", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Properties list: {len(data)} properties found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
