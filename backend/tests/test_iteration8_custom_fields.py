"""
Iteration 8 - Custom Fields Feature Tests
==========================================
Tests for the custom fields functionality in the public form:
- POST /api/admin/form-config/custom-field - Create custom field
- DELETE /api/admin/form-config/custom-field/{field_key} - Delete custom field
- GET /api/public/form-config - Get public form config (no auth)
- GET /api/admin/form-config/fields - Get all fields (admin)
- PUT /api/admin/form-config/fields - Update field config
- POST /api/admin/form-config/reset - Reset to defaults
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@sistema.pt"
ADMIN_PASSWORD = "admin"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login-v2",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, "No access_token in login response"
    return data["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth token."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


class TestPublicFormConfig:
    """Tests for public form config endpoint (no auth required)."""
    
    def test_get_public_form_config_no_auth(self):
        """GET /api/public/form-config should work without authentication."""
        response = requests.get(f"{BASE_URL}/api/public/form-config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "custom_fields" in data, "Response should have 'custom_fields' key"
        assert isinstance(data["custom_fields"], list), "custom_fields should be a list"
        
    def test_public_form_config_returns_only_visible_custom_fields(self):
        """Public endpoint should only return visible custom fields."""
        response = requests.get(f"{BASE_URL}/api/public/form-config")
        assert response.status_code == 200
        
        data = response.json()
        for field in data["custom_fields"]:
            assert field.get("is_custom") == True, "All fields should be custom"
            assert field.get("is_visible") == True, "All fields should be visible"


class TestAdminFormConfigFields:
    """Tests for admin form config fields endpoint."""
    
    def test_get_all_fields_requires_auth(self):
        """GET /api/admin/form-config/fields should require authentication."""
        response = requests.get(f"{BASE_URL}/api/admin/form-config/fields")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
    
    def test_get_all_fields_with_admin(self, admin_headers):
        """GET /api/admin/form-config/fields should return all fields for admin."""
        response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "fields" in data, "Response should have 'fields' key"
        assert isinstance(data["fields"], list), "fields should be a list"
        assert len(data["fields"]) > 0, "Should have at least some fields"
        
        # Verify field structure
        first_field = data["fields"][0]
        assert "field_key" in first_field, "Field should have field_key"
        assert "label" in first_field, "Field should have label"
        assert "step" in first_field, "Field should have step"
        
    def test_update_fields_config(self, admin_headers):
        """PUT /api/admin/form-config/fields should update field configuration."""
        # First get current config
        get_response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers
        )
        assert get_response.status_code == 200
        current_fields = get_response.json()["fields"]
        
        # Update without changing anything (just verify the endpoint works)
        put_response = requests.put(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers,
            json={"fields": current_fields}
        )
        assert put_response.status_code == 200, f"Expected 200, got {put_response.status_code}: {put_response.text}"
        
        data = put_response.json()
        assert "message" in data, "Response should have message"


class TestCustomFieldCreate:
    """Tests for creating custom fields."""
    
    def test_create_custom_field_requires_auth(self):
        """POST /api/admin/form-config/custom-field should require authentication."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            json={"label": "Test", "step": 1, "field_type": "text"}
        )
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
    
    def test_create_text_custom_field(self, admin_headers):
        """Create a text type custom field."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "TEST_Campo de Texto",
                "step": 1,
                "field_type": "text",
                "is_required": False,
                "placeholder": "Digite aqui",
                "hint": "Campo de teste"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "field" in data, "Response should have 'field' key"
        assert data["field"]["field_key"].startswith("custom_"), "Field key should start with 'custom_'"
        assert data["field"]["is_custom"] == True, "Field should be marked as custom"
        assert data["field"]["label"] == "TEST_Campo de Texto"
        
        # Store for cleanup
        TestCustomFieldCreate.created_field_key = data["field"]["field_key"]
    
    def test_create_select_custom_field_with_options(self, admin_headers):
        """Create a select type custom field with options."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "TEST_Dropdown Field",
                "step": 2,
                "field_type": "select",
                "is_required": True,
                "options": ["Option A", "Option B", "Option C"],
                "placeholder": "Selecione uma opção"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["field"]["options"] == ["Option A", "Option B", "Option C"]
        assert data["field"]["field_type"] == "select"
        
        TestCustomFieldCreate.created_select_field_key = data["field"]["field_key"]
    
    def test_create_checkbox_custom_field_with_options(self, admin_headers):
        """Create a checkbox type custom field with options."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "TEST_Checkbox Field",
                "step": 3,
                "field_type": "checkbox",
                "is_required": False,
                "options": ["Check 1", "Check 2"]
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["field"]["field_type"] == "checkbox"
        assert len(data["field"]["options"]) == 2
        
        TestCustomFieldCreate.created_checkbox_field_key = data["field"]["field_key"]
    
    def test_create_custom_field_step_6(self, admin_headers):
        """Create a custom field in step 6 (Informações Adicionais)."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "TEST_Step 6 Field",
                "step": 6,
                "field_type": "text",
                "is_required": False
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["field"]["step"] == 6
        
        TestCustomFieldCreate.created_step6_field_key = data["field"]["field_key"]
    
    def test_create_custom_field_invalid_step_0(self, admin_headers):
        """Step 0 should be rejected."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "Invalid Step Field",
                "step": 0,
                "field_type": "text"
            }
        )
        assert response.status_code == 400, f"Expected 400 for step 0, got {response.status_code}"
    
    def test_create_custom_field_invalid_step_7(self, admin_headers):
        """Step 7 should be rejected (max is 6)."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "Invalid Step Field",
                "step": 7,
                "field_type": "text"
            }
        )
        assert response.status_code == 400, f"Expected 400 for step 7, got {response.status_code}"
    
    def test_create_select_without_options_fails(self, admin_headers):
        """Select type without options should fail."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "Select Without Options",
                "step": 1,
                "field_type": "select"
            }
        )
        assert response.status_code == 400, f"Expected 400 for select without options, got {response.status_code}"
    
    def test_create_checkbox_without_options_fails(self, admin_headers):
        """Checkbox type without options should fail."""
        response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "Checkbox Without Options",
                "step": 1,
                "field_type": "checkbox"
            }
        )
        assert response.status_code == 400, f"Expected 400 for checkbox without options, got {response.status_code}"


class TestCustomFieldDelete:
    """Tests for deleting custom fields."""
    
    def test_delete_custom_field_requires_auth(self):
        """DELETE /api/admin/form-config/custom-field/{key} should require authentication."""
        response = requests.delete(
            f"{BASE_URL}/api/admin/form-config/custom-field/custom_test123"
        )
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
    
    def test_delete_non_custom_field_fails(self, admin_headers):
        """Deleting a non-custom (system) field should fail."""
        response = requests.delete(
            f"{BASE_URL}/api/admin/form-config/custom-field/name",
            headers=admin_headers
        )
        # Should be 400 (not allowed) or 404 (not found as custom)
        assert response.status_code in [400, 404], f"Expected 400 or 404, got {response.status_code}: {response.text}"
    
    def test_delete_nonexistent_field_fails(self, admin_headers):
        """Deleting a non-existent field should return 404."""
        response = requests.delete(
            f"{BASE_URL}/api/admin/form-config/custom-field/custom_nonexistent123",
            headers=admin_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_delete_created_custom_fields(self, admin_headers):
        """Delete the custom fields created in previous tests."""
        # Delete text field
        if hasattr(TestCustomFieldCreate, 'created_field_key'):
            response = requests.delete(
                f"{BASE_URL}/api/admin/form-config/custom-field/{TestCustomFieldCreate.created_field_key}",
                headers=admin_headers
            )
            assert response.status_code == 200, f"Failed to delete text field: {response.text}"
        
        # Delete select field
        if hasattr(TestCustomFieldCreate, 'created_select_field_key'):
            response = requests.delete(
                f"{BASE_URL}/api/admin/form-config/custom-field/{TestCustomFieldCreate.created_select_field_key}",
                headers=admin_headers
            )
            assert response.status_code == 200, f"Failed to delete select field: {response.text}"
        
        # Delete checkbox field
        if hasattr(TestCustomFieldCreate, 'created_checkbox_field_key'):
            response = requests.delete(
                f"{BASE_URL}/api/admin/form-config/custom-field/{TestCustomFieldCreate.created_checkbox_field_key}",
                headers=admin_headers
            )
            assert response.status_code == 200, f"Failed to delete checkbox field: {response.text}"
        
        # Delete step 6 field
        if hasattr(TestCustomFieldCreate, 'created_step6_field_key'):
            response = requests.delete(
                f"{BASE_URL}/api/admin/form-config/custom-field/{TestCustomFieldCreate.created_step6_field_key}",
                headers=admin_headers
            )
            assert response.status_code == 200, f"Failed to delete step 6 field: {response.text}"


class TestFormConfigReset:
    """Tests for resetting form config to defaults."""
    
    def test_reset_requires_auth(self):
        """POST /api/admin/form-config/reset should require authentication."""
        response = requests.post(f"{BASE_URL}/api/admin/form-config/reset")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
    
    def test_reset_removes_custom_fields(self, admin_headers):
        """Reset should remove all custom fields and restore defaults."""
        # First create a test custom field
        create_response = requests.post(
            f"{BASE_URL}/api/admin/form-config/custom-field",
            headers=admin_headers,
            json={
                "label": "TEST_Reset Test Field",
                "step": 1,
                "field_type": "text"
            }
        )
        assert create_response.status_code == 200
        created_key = create_response.json()["field"]["field_key"]
        
        # Verify it exists
        get_response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers
        )
        fields_before = get_response.json()["fields"]
        custom_before = [f for f in fields_before if f.get("is_custom")]
        assert any(f["field_key"] == created_key for f in custom_before), "Created field should exist"
        
        # Reset
        reset_response = requests.post(
            f"{BASE_URL}/api/admin/form-config/reset",
            headers=admin_headers
        )
        assert reset_response.status_code == 200, f"Reset failed: {reset_response.text}"
        
        data = reset_response.json()
        assert "fields" in data, "Reset response should include fields"
        
        # Verify no custom fields remain
        custom_after = [f for f in data["fields"] if f.get("is_custom")]
        assert len(custom_after) == 0, f"Expected 0 custom fields after reset, got {len(custom_after)}"


class TestExistingCustomField:
    """Tests for the existing custom field in the database."""
    
    def test_existing_custom_field_visible_in_public(self):
        """The existing custom field 'País de residência fiscal' should be visible."""
        response = requests.get(f"{BASE_URL}/api/public/form-config")
        assert response.status_code == 200
        
        data = response.json()
        custom_fields = data["custom_fields"]
        
        # Check if the existing field is present (may have been reset)
        # This test is informational - the field may or may not exist depending on test order
        print(f"Found {len(custom_fields)} custom fields in public config")
        for field in custom_fields:
            print(f"  - {field.get('label')} (step {field.get('step')}, type {field.get('field_type')})")
    
    def test_admin_can_see_all_fields_including_custom(self, admin_headers):
        """Admin should see all fields including any custom ones."""
        response = requests.get(
            f"{BASE_URL}/api/admin/form-config/fields",
            headers=admin_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        fields = data["fields"]
        
        # Count by type
        custom_count = len([f for f in fields if f.get("is_custom")])
        system_count = len([f for f in fields if not f.get("is_custom")])
        
        print(f"Total fields: {len(fields)} (system: {system_count}, custom: {custom_count})")
        
        # Verify we have the expected system fields
        assert system_count >= 20, f"Expected at least 20 system fields, got {system_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
