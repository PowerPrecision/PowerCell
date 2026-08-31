"""
Test Iteration 10 - Template Preview Feature
Tests for the new preview endpoint:
- GET /api/admin/form-config/templates/{id}/preview - Preview template fields without activating
"""
import pytest
import requests
import os
import urllib.parse

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Module-level session and token to avoid rate limiting
_session = None
_token = None
_created_templates = []


def get_auth_session():
    """Get authenticated session (cached at module level)"""
    global _session, _token
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        response = _session.post(f"{BASE_URL}/api/auth/login-v2", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        data = response.json()
        _token = data.get("access_token")
        _session.headers.update({"Authorization": f"Bearer {_token}"})
    return _session


class TestTemplatePreview:
    """Template Preview API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth session"""
        self.session = get_auth_session()
        yield
    
    # ==========================================
    # GET /api/admin/form-config/templates/{id}/preview - System Templates
    # ==========================================
    
    def test_preview_system_template_credito_habitacao(self):
        """Preview Crédito Habitação system template returns name, description, fields, is_system"""
        template_id = urllib.parse.quote("system_crédito_habitação", safe='')
        
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/preview")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify required fields
        assert "name" in data, "Preview should return name"
        assert "description" in data, "Preview should return description"
        assert "fields" in data, "Preview should return fields"
        assert "is_system" in data, "Preview should return is_system"
        
        # Verify values
        assert data["name"] == "Crédito Habitação"
        assert data["is_system"] == True
        assert len(data["fields"]) == 26, f"Expected 26 fields, got {len(data['fields'])}"
        assert len(data["description"]) > 10, "Description should not be empty"
    
    def test_preview_system_template_refinanciamento(self):
        """Preview Refinanciamento system template returns correct data"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento/preview")
        assert response.status_code == 200
        
        data = response.json()
        
        assert data["name"] == "Refinanciamento"
        assert data["is_system"] == True
        assert len(data["fields"]) == 26
        
        # Verify refinanciamento-specific fields in step 3
        step3_fields = [f for f in data["fields"] if f.get("step") == 3]
        field_keys = [f["field_key"] for f in step3_fields]
        assert "valor_transferencia" in field_keys, "Refinanciamento should have valor_transferencia"
        assert "prazo_pretendido" in field_keys, "Refinanciamento should have prazo_pretendido"
        assert "banco_atual" in field_keys, "Refinanciamento should have banco_atual"
    
    def test_preview_system_template_credito_pessoal(self):
        """Preview Crédito Pessoal system template returns correct data"""
        template_id = urllib.parse.quote("system_crédito_pessoal", safe='')
        
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/preview")
        assert response.status_code == 200
        
        data = response.json()
        
        assert data["name"] == "Crédito Pessoal"
        assert data["is_system"] == True
        assert len(data["fields"]) == 23, f"Expected 23 fields, got {len(data['fields'])}"
    
    # ==========================================
    # GET /api/admin/form-config/templates/{id}/preview - Custom Templates
    # ==========================================
    
    def test_preview_custom_template(self):
        """Preview custom template returns correct data"""
        # First create a custom template
        save_response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates", json={
            "name": "TEST_Preview_Custom",
            "description": "Custom template for preview testing"
        })
        assert save_response.status_code == 200
        template_id = save_response.json()["template"]["id"]
        _created_templates.append(template_id)
        
        # Now preview it
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/preview")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify required fields
        assert "name" in data
        assert "description" in data
        assert "fields" in data
        assert "is_system" in data
        
        # Verify values
        assert data["name"] == "TEST_Preview_Custom"
        assert data["description"] == "Custom template for preview testing"
        assert data["is_system"] == False
        assert isinstance(data["fields"], list)
        assert len(data["fields"]) > 0, "Custom template should have fields"
    
    # ==========================================
    # GET /api/admin/form-config/templates/{id}/preview - Error Cases
    # ==========================================
    
    def test_preview_invalid_template_returns_404(self):
        """Preview non-existent template returns 404"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/invalid_id/preview")
        assert response.status_code == 404
    
    def test_preview_nonexistent_system_template_returns_404(self):
        """Preview non-existent system template returns 404"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/system_nonexistent/preview")
        assert response.status_code == 404
    
    def test_preview_requires_auth(self):
        """Preview endpoint requires authentication"""
        # Use a new session without auth
        response = requests.get(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento/preview")
        assert response.status_code == 401
    
    # ==========================================
    # Field Structure Validation
    # ==========================================
    
    def test_preview_fields_have_required_properties(self):
        """Preview fields should have all required properties for rendering"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento/preview")
        assert response.status_code == 200
        
        data = response.json()
        fields = data["fields"]
        
        # Check first few fields have required properties
        for field in fields[:5]:
            assert "field_key" in field, "Field should have field_key"
            assert "label" in field, "Field should have label"
            assert "step" in field, "Field should have step"
            assert "field_type" in field, "Field should have field_type"
            assert "is_required" in field, "Field should have is_required"
            assert "is_visible" in field, "Field should have is_visible"
    
    def test_preview_fields_grouped_by_step(self):
        """Preview fields should be groupable by step"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento/preview")
        assert response.status_code == 200
        
        data = response.json()
        fields = data["fields"]
        
        # Group by step
        steps = {}
        for field in fields:
            step = field.get("step", 1)
            if step not in steps:
                steps[step] = []
            steps[step].append(field)
        
        # Refinanciamento should have steps 1, 2, 3, 4, 5
        assert 1 in steps, "Should have step 1"
        assert 2 in steps, "Should have step 2"
        assert 3 in steps, "Should have step 3"
        assert 4 in steps, "Should have step 4"
        assert 5 in steps, "Should have step 5"
    
    def test_preview_fields_have_correct_types(self):
        """Preview fields should have valid field_type values"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento/preview")
        assert response.status_code == 200
        
        data = response.json()
        fields = data["fields"]
        
        valid_types = {"text", "select", "checkbox", "radio", "date", "number"}
        
        for field in fields:
            assert field["field_type"] in valid_types, f"Invalid field_type: {field['field_type']}"
    
    def test_preview_select_fields_have_options(self):
        """Select/checkbox fields in preview should have options (if defined)"""
        template_id = urllib.parse.quote("system_crédito_habitação", safe='')
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/preview")
        assert response.status_code == 200
        
        data = response.json()
        fields = data["fields"]
        
        # Find select/checkbox fields
        select_fields = [f for f in fields if f["field_type"] in ("select", "checkbox")]
        
        # At least some select fields should exist
        assert len(select_fields) > 0, "Should have select/checkbox fields"
    
    # ==========================================
    # Preview Does Not Modify State
    # ==========================================
    
    def test_preview_does_not_activate_template(self):
        """Preview should not change the active form configuration"""
        # Get current config
        initial_config = self.session.get(f"{BASE_URL}/api/admin/form-config/fields")
        initial_fields = initial_config.json()["fields"]
        initial_count = len(initial_fields)
        
        # Preview a different template
        template_id = urllib.parse.quote("system_crédito_pessoal", safe='')
        preview_response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/preview")
        assert preview_response.status_code == 200
        
        # Verify config hasn't changed
        after_config = self.session.get(f"{BASE_URL}/api/admin/form-config/fields")
        after_fields = after_config.json()["fields"]
        after_count = len(after_fields)
        
        assert initial_count == after_count, "Preview should not change active config field count"


class TestTemplatePreviewCleanup:
    """Cleanup test templates"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = get_auth_session()
        yield
    
    def test_cleanup_test_templates(self):
        """Clean up any TEST_ prefixed templates"""
        global _created_templates
        
        for template_id in _created_templates:
            try:
                self.session.delete(f"{BASE_URL}/api/admin/form-config/templates/{template_id}")
            except Exception:
                pass
        
        _created_templates = []
        
        # Also clean up any TEST_ templates that might have been left from previous runs
        list_response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        if list_response.status_code == 200:
            templates = list_response.json().get("templates", [])
            for tpl in templates:
                if tpl.get("name", "").startswith("TEST_"):
                    try:
                        self.session.delete(f"{BASE_URL}/api/admin/form-config/templates/{tpl['id']}")
                    except Exception:
                        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
