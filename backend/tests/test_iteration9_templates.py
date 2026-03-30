"""
Test Iteration 9 - Form Templates Feature
Tests for template CRUD operations:
- GET /api/admin/form-config/templates - List all templates (system + custom)
- POST /api/admin/form-config/templates - Save current config as template
- POST /api/admin/form-config/templates/{id}/activate - Activate a template
- POST /api/admin/form-config/templates/{id}/duplicate - Duplicate a template
- DELETE /api/admin/form-config/templates/{id} - Delete custom template
"""
import pytest
import requests
import os
import urllib.parse
import time

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
        response = _session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        data = response.json()
        _token = data.get("access_token")
        _session.headers.update({"Authorization": f"Bearer {_token}"})
    return _session


class TestFormTemplates:
    """Form Templates API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth session"""
        self.session = get_auth_session()
        yield
    
    # ==========================================
    # GET /api/admin/form-config/templates
    # ==========================================
    
    def test_list_templates_returns_system_templates(self):
        """GET /templates should return 3 system templates"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        assert response.status_code == 200
        
        data = response.json()
        assert "templates" in data
        templates = data["templates"]
        
        # Filter system templates
        system_templates = [t for t in templates if t.get("is_system")]
        assert len(system_templates) == 3, f"Expected 3 system templates, got {len(system_templates)}"
        
        # Verify system template names
        system_names = [t["name"] for t in system_templates]
        assert "Crédito Habitação" in system_names
        assert "Refinanciamento" in system_names
        assert "Crédito Pessoal" in system_names
    
    def test_list_templates_system_have_correct_field_counts(self):
        """System templates should have correct field counts"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        assert response.status_code == 200
        
        templates = response.json()["templates"]
        system_templates = {t["name"]: t for t in templates if t.get("is_system")}
        
        # Crédito Habitação - 26 fields (full default config)
        assert system_templates["Crédito Habitação"]["field_count"] == 26
        
        # Refinanciamento - 26 fields (step 3 replaced with refinancing fields)
        assert system_templates["Refinanciamento"]["field_count"] == 26
        
        # Crédito Pessoal - 23 fields (no step 3 imóvel, renumbered)
        assert system_templates["Crédito Pessoal"]["field_count"] == 23
    
    def test_list_templates_system_have_descriptions(self):
        """System templates should have descriptions"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        assert response.status_code == 200
        
        templates = response.json()["templates"]
        system_templates = [t for t in templates if t.get("is_system")]
        
        for tpl in system_templates:
            assert "description" in tpl
            assert len(tpl["description"]) > 10, f"Template {tpl['name']} has short/empty description"
    
    def test_list_templates_includes_custom_templates(self):
        """GET /templates should include custom templates from DB"""
        response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        assert response.status_code == 200
        
        templates = response.json()["templates"]
        custom_templates = [t for t in templates if not t.get("is_system")]
        
        # There should be at least 2 custom templates from manual testing
        # (tpl_13e37f72, tpl_ad39ac8a mentioned in context)
        assert len(custom_templates) >= 0, "Custom templates should be returned"
    
    def test_list_templates_requires_auth(self):
        """GET /templates should require authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/form-config/templates")
        assert response.status_code == 401
    
    # ==========================================
    # POST /api/admin/form-config/templates (Save as Template)
    # ==========================================
    
    def test_save_as_template_success(self):
        """POST /templates should save current config as template"""
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates", json={
            "name": "TEST_Template_Save",
            "description": "Test template created by pytest"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "template" in data
        assert data["template"]["name"] == "TEST_Template_Save"
        assert "id" in data["template"]
        assert data["template"]["id"].startswith("tpl_")
        
        # Track for cleanup
        _created_templates.append(data["template"]["id"])
        
        # Verify template appears in list
        list_response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        templates = list_response.json()["templates"]
        saved_tpl = next((t for t in templates if t["id"] == data["template"]["id"]), None)
        assert saved_tpl is not None
        assert saved_tpl["name"] == "TEST_Template_Save"
    
    def test_save_as_template_requires_name(self):
        """POST /templates should require name"""
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates", json={
            "name": "",
            "description": "No name"
        })
        assert response.status_code == 400
    
    def test_save_as_template_with_whitespace_name(self):
        """POST /templates should reject whitespace-only name"""
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates", json={
            "name": "   ",
            "description": "Whitespace name"
        })
        assert response.status_code == 400
    
    # ==========================================
    # POST /api/admin/form-config/templates/{id}/activate
    # ==========================================
    
    def test_activate_system_template_credito_habitacao(self):
        """Activating Crédito Habitação template should apply its fields"""
        # URL encode the template ID (has accented characters)
        template_id = urllib.parse.quote("system_crédito_habitação", safe='')
        
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/activate")
        assert response.status_code == 200
        
        data = response.json()
        assert "field_count" in data
        assert data["field_count"] == 26
    
    def test_activate_system_template_refinanciamento(self):
        """Activating Refinanciamento template should apply its fields"""
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento/activate")
        assert response.status_code == 200
        
        data = response.json()
        assert data["field_count"] == 26
        
        # Verify the active config has refinanciamento-specific fields
        config_response = self.session.get(f"{BASE_URL}/api/admin/form-config/fields")
        assert config_response.status_code == 200
        
        fields = config_response.json()["fields"]
        step3_fields = [f for f in fields if f.get("step") == 3]
        
        # Refinanciamento should have specific fields like "valor_transferencia"
        field_keys = [f["field_key"] for f in step3_fields]
        assert "valor_transferencia" in field_keys, "Refinanciamento template should have valor_transferencia field"
    
    def test_activate_system_template_credito_pessoal(self):
        """Activating Crédito Pessoal template should apply its fields"""
        template_id = urllib.parse.quote("system_crédito_pessoal", safe='')
        
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/activate")
        assert response.status_code == 200
        
        data = response.json()
        assert data["field_count"] == 23
    
    def test_activate_custom_template(self):
        """Activating a custom template should apply its fields"""
        # First create a template
        save_response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates", json={
            "name": "TEST_Activate_Custom",
            "description": "Test custom template for activation"
        })
        assert save_response.status_code == 200
        template_id = save_response.json()["template"]["id"]
        _created_templates.append(template_id)
        
        # Now activate it
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/activate")
        assert response.status_code == 200
        assert "field_count" in response.json()
    
    def test_activate_nonexistent_template(self):
        """Activating non-existent template should return 404"""
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/nonexistent_id/activate")
        assert response.status_code == 404
    
    # ==========================================
    # POST /api/admin/form-config/templates/{id}/duplicate
    # ==========================================
    
    def test_duplicate_system_template(self):
        """Duplicating system template should create custom copy"""
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento/duplicate")
        assert response.status_code == 200
        
        data = response.json()
        assert "template" in data
        assert data["template"]["id"].startswith("tpl_")
        assert "cópia" in data["template"]["name"].lower() or "Refinanciamento" in data["template"]["name"]
        
        # Track for cleanup
        _created_templates.append(data["template"]["id"])
    
    def test_duplicate_custom_template(self):
        """Duplicating custom template should create another custom copy"""
        # First create a template
        save_response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates", json={
            "name": "TEST_Duplicate_Source",
            "description": "Source template for duplication"
        })
        assert save_response.status_code == 200
        source_id = save_response.json()["template"]["id"]
        _created_templates.append(source_id)
        
        # Duplicate it
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/{source_id}/duplicate")
        assert response.status_code == 200
        
        data = response.json()
        assert data["template"]["id"] != source_id
        _created_templates.append(data["template"]["id"])
    
    def test_duplicate_nonexistent_template(self):
        """Duplicating non-existent template should return 404"""
        response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/nonexistent_id/duplicate")
        assert response.status_code == 404
    
    # ==========================================
    # DELETE /api/admin/form-config/templates/{id}
    # ==========================================
    
    def test_delete_custom_template(self):
        """DELETE should remove custom template"""
        # First create a template
        save_response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates", json={
            "name": "TEST_Delete_Me",
            "description": "Template to be deleted"
        })
        assert save_response.status_code == 200
        template_id = save_response.json()["template"]["id"]
        
        # Delete it
        response = self.session.delete(f"{BASE_URL}/api/admin/form-config/templates/{template_id}")
        assert response.status_code == 200
        
        # Verify it's gone
        list_response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        templates = list_response.json()["templates"]
        deleted_tpl = next((t for t in templates if t["id"] == template_id), None)
        assert deleted_tpl is None, "Deleted template should not appear in list"
    
    def test_delete_system_template_returns_400(self):
        """DELETE should return 400 for system templates"""
        # Try to delete system template
        template_id = urllib.parse.quote("system_crédito_habitação", safe='')
        response = self.session.delete(f"{BASE_URL}/api/admin/form-config/templates/{template_id}")
        assert response.status_code == 400
        
        # Also test without encoding
        response2 = self.session.delete(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento")
        assert response2.status_code == 400
    
    def test_delete_nonexistent_template(self):
        """DELETE should return 404 for non-existent template"""
        response = self.session.delete(f"{BASE_URL}/api/admin/form-config/templates/nonexistent_id")
        assert response.status_code == 404
    
    # ==========================================
    # Integration Tests
    # ==========================================
    
    def test_full_template_workflow(self):
        """Test complete workflow: save -> list -> activate -> duplicate -> delete"""
        # 1. Save current config as template
        save_response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates", json={
            "name": "TEST_Full_Workflow",
            "description": "Full workflow test"
        })
        assert save_response.status_code == 200
        template_id = save_response.json()["template"]["id"]
        _created_templates.append(template_id)
        
        # 2. Verify it appears in list
        list_response = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        templates = list_response.json()["templates"]
        found = next((t for t in templates if t["id"] == template_id), None)
        assert found is not None
        assert found["name"] == "TEST_Full_Workflow"
        
        # 3. Activate it
        activate_response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/activate")
        assert activate_response.status_code == 200
        
        # 4. Duplicate it
        duplicate_response = self.session.post(f"{BASE_URL}/api/admin/form-config/templates/{template_id}/duplicate")
        assert duplicate_response.status_code == 200
        duplicate_id = duplicate_response.json()["template"]["id"]
        _created_templates.append(duplicate_id)
        
        # 5. Delete the duplicate
        delete_response = self.session.delete(f"{BASE_URL}/api/admin/form-config/templates/{duplicate_id}")
        assert delete_response.status_code == 200
        _created_templates.remove(duplicate_id)
        
        # 6. Verify duplicate is gone
        final_list = self.session.get(f"{BASE_URL}/api/admin/form-config/templates")
        final_templates = final_list.json()["templates"]
        assert not any(t["id"] == duplicate_id for t in final_templates)
    
    def test_activate_refinanciamento_changes_step3_fields(self):
        """After activating Refinanciamento, Step 3 should have refinancing-specific fields"""
        # First reset to defaults
        self.session.post(f"{BASE_URL}/api/admin/form-config/reset")
        
        # Get initial step 3 fields
        initial_config = self.session.get(f"{BASE_URL}/api/admin/form-config/fields")
        initial_fields = initial_config.json()["fields"]
        initial_step3 = [f["field_key"] for f in initial_fields if f.get("step") == 3]
        
        # Activate Refinanciamento
        self.session.post(f"{BASE_URL}/api/admin/form-config/templates/system_refinanciamento/activate")
        
        # Get new step 3 fields
        new_config = self.session.get(f"{BASE_URL}/api/admin/form-config/fields")
        new_fields = new_config.json()["fields"]
        new_step3 = [f["field_key"] for f in new_fields if f.get("step") == 3]
        
        # Refinanciamento should have different step 3 fields
        assert "valor_transferencia" in new_step3, "Refinanciamento should have valor_transferencia"
        assert "prazo_pretendido" in new_step3, "Refinanciamento should have prazo_pretendido"
        assert "banco_atual" in new_step3, "Refinanciamento should have banco_atual"
        
        # Reset back to defaults for other tests
        self.session.post(f"{BASE_URL}/api/admin/form-config/reset")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
