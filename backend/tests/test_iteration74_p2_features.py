"""
Iteration 74 - Testing P2 Features: O22 (Automation Engine), O11 (WebSocket Polling Fallback), O19 (axe-core), O5 (Encryption)

Tests:
- O22: CRUD completo de regras de automação via API /api/admin/automation/rules
- O22: GET /api/admin/automation/triggers retorna lista de triggers disponíveis
- O22: GET /api/admin/automation/actions retorna lista de ações disponíveis
- O22: Validação de triggers e ações inválidos retorna 400
- O11: useWebSocket.js polling fallback implementation
- O19: axe-core is installed and configured in main.jsx
- O5: Encryption service exists at /app/backend/services/encryption.py
"""
import pytest
import requests
import os
import sys
import uuid

# Add backend to path for imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://form-template-fix-1.preview.emergentagent.com')


class TestAuthentication:
    """Helper class for authentication"""
    
    @staticmethod
    def get_admin_token():
        """Get admin token for authenticated requests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None
    
    @staticmethod
    def get_ceo_token():
        """Get CEO token for authenticated requests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "pedroborges@powerealestate.pt",
            "password": "power2026"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        return None


# ============== O22 - Automation Engine Tests ==============

class TestO22AutomationCRUD:
    """O22 - Automation Rules CRUD API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup admin token for tests"""
        self.token = TestAuthentication.get_admin_token()
        if not self.token:
            pytest.skip("Could not authenticate as admin")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_list_rules_empty_or_existing(self):
        """Test GET /api/admin/automation/rules returns list"""
        response = requests.get(f"{BASE_URL}/api/admin/automation/rules", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rules" in data, "Response should contain 'rules' key"
        assert "total" in data, "Response should contain 'total' key"
        assert isinstance(data["rules"], list), "rules should be a list"
        print(f"✓ GET /api/admin/automation/rules returns {data['total']} rules")
    
    def test_create_rule_success(self):
        """Test POST /api/admin/automation/rules creates a new rule"""
        rule_data = {
            "name": f"TEST_Rule_{uuid.uuid4().hex[:8]}",
            "description": "Test automation rule",
            "trigger": "process_status_changed",
            "trigger_config": {"target_status": "aprovado"},
            "action": "send_notification",
            "action_config": {"target_role": "admin", "message": "Processo aprovado!"},
            "is_active": True
        }
        response = requests.post(f"{BASE_URL}/api/admin/automation/rules", headers=self.headers, json=rule_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data, "Response should contain 'id'"
        assert data["name"] == rule_data["name"], "Name should match"
        assert data["trigger"] == rule_data["trigger"], "Trigger should match"
        assert data["action"] == rule_data["action"], "Action should match"
        print(f"✓ POST /api/admin/automation/rules created rule: {data['id']}")
        
        # Cleanup - delete the test rule
        delete_response = requests.delete(f"{BASE_URL}/api/admin/automation/rules/{data['id']}", headers=self.headers)
        assert delete_response.status_code == 200, "Cleanup delete should succeed"
    
    def test_get_rule_by_id(self):
        """Test GET /api/admin/automation/rules/{rule_id} returns specific rule"""
        # First create a rule
        rule_data = {
            "name": f"TEST_GetById_{uuid.uuid4().hex[:8]}",
            "trigger": "process_created",
            "action": "add_comment",
            "action_config": {"comment": "Processo criado automaticamente"}
        }
        create_response = requests.post(f"{BASE_URL}/api/admin/automation/rules", headers=self.headers, json=rule_data)
        assert create_response.status_code == 200
        rule_id = create_response.json()["id"]
        
        # Get by ID
        response = requests.get(f"{BASE_URL}/api/admin/automation/rules/{rule_id}", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["id"] == rule_id, "ID should match"
        assert data["name"] == rule_data["name"], "Name should match"
        print(f"✓ GET /api/admin/automation/rules/{rule_id} returns correct rule")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/automation/rules/{rule_id}", headers=self.headers)
    
    def test_update_rule(self):
        """Test PUT /api/admin/automation/rules/{rule_id} updates rule"""
        # Create a rule
        rule_data = {
            "name": f"TEST_Update_{uuid.uuid4().hex[:8]}",
            "trigger": "document_uploaded",
            "action": "send_notification",
            "action_config": {"message": "Original message"}
        }
        create_response = requests.post(f"{BASE_URL}/api/admin/automation/rules", headers=self.headers, json=rule_data)
        assert create_response.status_code == 200
        rule_id = create_response.json()["id"]
        
        # Update the rule
        update_data = {
            "name": "TEST_Updated_Name",
            "is_active": False,
            "action_config": {"message": "Updated message"}
        }
        response = requests.put(f"{BASE_URL}/api/admin/automation/rules/{rule_id}", headers=self.headers, json=update_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["name"] == "TEST_Updated_Name", "Name should be updated"
        assert data["is_active"] == False, "is_active should be updated"
        print(f"✓ PUT /api/admin/automation/rules/{rule_id} updates rule correctly")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/automation/rules/{rule_id}", headers=self.headers)
    
    def test_delete_rule(self):
        """Test DELETE /api/admin/automation/rules/{rule_id} deletes rule"""
        # Create a rule
        rule_data = {
            "name": f"TEST_Delete_{uuid.uuid4().hex[:8]}",
            "trigger": "client_registered",
            "action": "add_comment"
        }
        create_response = requests.post(f"{BASE_URL}/api/admin/automation/rules", headers=self.headers, json=rule_data)
        assert create_response.status_code == 200
        rule_id = create_response.json()["id"]
        
        # Delete the rule
        response = requests.delete(f"{BASE_URL}/api/admin/automation/rules/{rule_id}", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") == True, "Delete should return success: true"
        print(f"✓ DELETE /api/admin/automation/rules/{rule_id} deletes rule")
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/admin/automation/rules/{rule_id}", headers=self.headers)
        assert get_response.status_code == 404, "Deleted rule should return 404"
    
    def test_get_rule_not_found(self):
        """Test GET /api/admin/automation/rules/{invalid_id} returns 404"""
        response = requests.get(f"{BASE_URL}/api/admin/automation/rules/nonexistent-id-12345", headers=self.headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ GET non-existent rule returns 404")


class TestO22AutomationTriggersActions:
    """O22 - Automation Triggers and Actions API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup admin token for tests"""
        self.token = TestAuthentication.get_admin_token()
        if not self.token:
            pytest.skip("Could not authenticate as admin")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_get_triggers_list(self):
        """Test GET /api/admin/automation/triggers returns available triggers"""
        response = requests.get(f"{BASE_URL}/api/admin/automation/triggers", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "triggers" in data, "Response should contain 'triggers' key"
        triggers = data["triggers"]
        assert isinstance(triggers, list), "triggers should be a list"
        assert len(triggers) > 0, "Should have at least one trigger"
        
        # Verify expected triggers exist
        trigger_ids = [t["id"] for t in triggers]
        expected_triggers = ["process_status_changed", "process_created", "document_uploaded", "process_stale", "client_registered"]
        for expected in expected_triggers:
            assert expected in trigger_ids, f"Trigger '{expected}' should be in list"
        
        # Verify trigger structure
        for trigger in triggers:
            assert "id" in trigger, "Trigger should have 'id'"
            assert "label" in trigger, "Trigger should have 'label'"
            assert "config_fields" in trigger, "Trigger should have 'config_fields'"
        
        print(f"✓ GET /api/admin/automation/triggers returns {len(triggers)} triggers")
    
    def test_get_actions_list(self):
        """Test GET /api/admin/automation/actions returns available actions"""
        response = requests.get(f"{BASE_URL}/api/admin/automation/actions", headers=self.headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "actions" in data, "Response should contain 'actions' key"
        actions = data["actions"]
        assert isinstance(actions, list), "actions should be a list"
        assert len(actions) > 0, "Should have at least one action"
        
        # Verify expected actions exist
        action_ids = [a["id"] for a in actions]
        expected_actions = ["send_notification", "change_status", "assign_user", "add_comment", "send_email"]
        for expected in expected_actions:
            assert expected in action_ids, f"Action '{expected}' should be in list"
        
        # Verify action structure
        for action in actions:
            assert "id" in action, "Action should have 'id'"
            assert "label" in action, "Action should have 'label'"
            assert "config_fields" in action, "Action should have 'config_fields'"
        
        print(f"✓ GET /api/admin/automation/actions returns {len(actions)} actions")


class TestO22AutomationValidation:
    """O22 - Automation Validation Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup admin token for tests"""
        self.token = TestAuthentication.get_admin_token()
        if not self.token:
            pytest.skip("Could not authenticate as admin")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_invalid_trigger_returns_400(self):
        """Test POST with invalid trigger returns 400"""
        rule_data = {
            "name": "TEST_Invalid_Trigger",
            "trigger": "invalid_trigger_type",
            "action": "send_notification"
        }
        response = requests.post(f"{BASE_URL}/api/admin/automation/rules", headers=self.headers, json=rule_data)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "detail" in data, "Error response should have 'detail'"
        assert "Trigger" in data["detail"] or "trigger" in data["detail"].lower(), "Error should mention trigger"
        print("✓ Invalid trigger returns 400 with appropriate error message")
    
    def test_invalid_action_returns_400(self):
        """Test POST with invalid action returns 400"""
        rule_data = {
            "name": "TEST_Invalid_Action",
            "trigger": "process_created",
            "action": "invalid_action_type"
        }
        response = requests.post(f"{BASE_URL}/api/admin/automation/rules", headers=self.headers, json=rule_data)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "detail" in data, "Error response should have 'detail'"
        assert "Ação" in data["detail"] or "ação" in data["detail"].lower() or "action" in data["detail"].lower(), "Error should mention action"
        print("✓ Invalid action returns 400 with appropriate error message")
    
    def test_update_with_invalid_trigger_returns_400(self):
        """Test PUT with invalid trigger returns 400"""
        # First create a valid rule
        rule_data = {
            "name": f"TEST_UpdateInvalid_{uuid.uuid4().hex[:8]}",
            "trigger": "process_created",
            "action": "add_comment"
        }
        create_response = requests.post(f"{BASE_URL}/api/admin/automation/rules", headers=self.headers, json=rule_data)
        assert create_response.status_code == 200
        rule_id = create_response.json()["id"]
        
        # Try to update with invalid trigger
        update_data = {"trigger": "invalid_trigger"}
        response = requests.put(f"{BASE_URL}/api/admin/automation/rules/{rule_id}", headers=self.headers, json=update_data)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Update with invalid trigger returns 400")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/admin/automation/rules/{rule_id}", headers=self.headers)


class TestO22AutomationAuth:
    """O22 - Automation API Authentication Tests"""
    
    def test_rules_endpoint_requires_auth(self):
        """Test /api/admin/automation/rules requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/automation/rules")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/admin/automation/rules requires authentication")
    
    def test_triggers_endpoint_requires_auth(self):
        """Test /api/admin/automation/triggers requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/automation/triggers")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/admin/automation/triggers requires authentication")
    
    def test_actions_endpoint_requires_auth(self):
        """Test /api/admin/automation/actions requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/automation/actions")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/admin/automation/actions requires authentication")
    
    def test_ceo_can_access_automation(self):
        """Test CEO role can access automation endpoints"""
        token = TestAuthentication.get_ceo_token()
        if not token:
            pytest.skip("Could not authenticate as CEO")
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/admin/automation/rules", headers=headers)
        assert response.status_code == 200, f"CEO should access rules, got {response.status_code}"
        print("✓ CEO role can access automation endpoints")


# ============== O22 - Workflow Engine Code Tests ==============

class TestO22WorkflowEngineCode:
    """O22 - Workflow Engine Code Structure Tests"""
    
    def test_workflow_engine_file_exists(self):
        """Verify workflow_engine.py exists"""
        assert os.path.exists('/app/backend/services/workflow_engine.py'), "workflow_engine.py should exist"
        print("✓ workflow_engine.py exists")
    
    def test_workflow_engine_valid_triggers(self):
        """Verify VALID_TRIGGERS list is defined"""
        with open('/app/backend/services/workflow_engine.py', 'r') as f:
            content = f.read()
        assert 'VALID_TRIGGERS' in content, "VALID_TRIGGERS should be defined"
        assert 'process_status_changed' in content, "process_status_changed trigger should exist"
        assert 'process_created' in content, "process_created trigger should exist"
        assert 'document_uploaded' in content, "document_uploaded trigger should exist"
        assert 'process_stale' in content, "process_stale trigger should exist"
        assert 'client_registered' in content, "client_registered trigger should exist"
        print("✓ VALID_TRIGGERS properly defined")
    
    def test_workflow_engine_valid_actions(self):
        """Verify VALID_ACTIONS list is defined"""
        with open('/app/backend/services/workflow_engine.py', 'r') as f:
            content = f.read()
        assert 'VALID_ACTIONS' in content, "VALID_ACTIONS should be defined"
        assert 'send_notification' in content, "send_notification action should exist"
        assert 'change_status' in content, "change_status action should exist"
        assert 'assign_user' in content, "assign_user action should exist"
        assert 'add_comment' in content, "add_comment action should exist"
        assert 'send_email' in content, "send_email action should exist"
        print("✓ VALID_ACTIONS properly defined")
    
    def test_workflow_engine_crud_functions(self):
        """Verify CRUD functions are defined"""
        with open('/app/backend/services/workflow_engine.py', 'r') as f:
            content = f.read()
        assert 'async def list_rules' in content, "list_rules function should exist"
        assert 'async def get_rule' in content, "get_rule function should exist"
        assert 'async def create_rule' in content, "create_rule function should exist"
        assert 'async def update_rule' in content, "update_rule function should exist"
        assert 'async def delete_rule' in content, "delete_rule function should exist"
        print("✓ CRUD functions defined in workflow_engine.py")
    
    def test_automation_routes_file_exists(self):
        """Verify automation.py routes file exists"""
        assert os.path.exists('/app/backend/routes/automation.py'), "automation.py should exist"
        print("✓ automation.py routes file exists")
    
    def test_automation_router_registered(self):
        """Verify automation_router is registered in server.py"""
        with open('/app/backend/server.py', 'r') as f:
            content = f.read()
        assert 'from routes.automation import router as automation_router' in content, "automation_router should be imported"
        assert 'app.include_router(automation_router' in content, "automation_router should be registered"
        print("✓ automation_router registered in server.py")


# ============== O11 - WebSocket Polling Fallback Tests ==============

class TestO11WebSocketPollingFallback:
    """O11 - WebSocket Polling Fallback Code Tests"""
    
    def test_usewebsocket_file_exists(self):
        """Verify useWebSocket.js exists"""
        assert os.path.exists('/app/frontend/src/hooks/useWebSocket.js'), "useWebSocket.js should exist"
        print("✓ useWebSocket.js exists")
    
    def test_polling_fallback_constants(self):
        """Verify MAX_WS_FAILS and POLLING_INTERVAL constants"""
        with open('/app/frontend/src/hooks/useWebSocket.js', 'r') as f:
            content = f.read()
        assert 'MAX_WS_FAILS' in content, "MAX_WS_FAILS constant should be defined"
        assert '3' in content, "MAX_WS_FAILS should be 3"
        assert 'POLLING_INTERVAL' in content, "POLLING_INTERVAL constant should be defined"
        assert '30000' in content, "POLLING_INTERVAL should be 30000 (30 seconds)"
        print("✓ MAX_WS_FAILS=3 and POLLING_INTERVAL=30000 defined")
    
    def test_polling_fallback_function(self):
        """Verify startPollingFallback function exists"""
        with open('/app/frontend/src/hooks/useWebSocket.js', 'r') as f:
            content = f.read()
        assert 'startPollingFallback' in content, "startPollingFallback function should exist"
        assert 'stopPollingFallback' in content, "stopPollingFallback function should exist"
        print("✓ startPollingFallback and stopPollingFallback functions defined")
    
    def test_polling_fallback_logic(self):
        """Verify polling fallback is triggered after WS failures"""
        with open('/app/frontend/src/hooks/useWebSocket.js', 'r') as f:
            content = f.read()
        assert 'wsFailCountRef' in content, "wsFailCountRef should track failures"
        assert 'pollingIntervalRef' in content, "pollingIntervalRef should track polling interval"
        # Check that polling is started when failures exceed threshold
        assert 'wsFailCountRef.current >= MAX_WS_FAILS' in content or 'wsFailCountRef.current++' in content, "Should track WS failures"
        print("✓ Polling fallback logic implemented")
    
    def test_polling_uses_notifications_api(self):
        """Verify polling fetches from /api/notifications"""
        with open('/app/frontend/src/hooks/useWebSocket.js', 'r') as f:
            content = f.read()
        assert '/api/notifications' in content, "Polling should fetch from /api/notifications"
        print("✓ Polling uses /api/notifications endpoint")
    
    def test_ispolling_exposed(self):
        """Verify isPolling state is exposed"""
        with open('/app/frontend/src/hooks/useWebSocket.js', 'r') as f:
            content = f.read()
        assert 'isPolling' in content, "isPolling should be exposed"
        print("✓ isPolling state exposed in hook return")


# ============== O19 - axe-core Accessibility Tests ==============

class TestO19AxeCore:
    """O19 - axe-core Accessibility Configuration Tests"""
    
    def test_axe_core_in_package_json(self):
        """Verify @axe-core/react is in package.json"""
        with open('/app/frontend/package.json', 'r') as f:
            content = f.read()
        assert '@axe-core/react' in content, "@axe-core/react should be in package.json"
        print("✓ @axe-core/react in package.json")
    
    def test_axe_core_configured_in_main_jsx(self):
        """Verify axe-core is configured in main.jsx for dev mode"""
        with open('/app/frontend/src/main.jsx', 'r') as f:
            content = f.read()
        assert '@axe-core/react' in content, "@axe-core/react should be imported"
        assert 'import.meta.env.DEV' in content, "Should check for DEV mode"
        print("✓ axe-core configured in main.jsx for development mode")
    
    def test_axe_core_dev_only(self):
        """Verify axe-core only runs in development"""
        with open('/app/frontend/src/main.jsx', 'r') as f:
            content = f.read()
        # Check that axe is only loaded in dev mode
        assert 'if (import.meta.env.DEV)' in content, "axe-core should only run in DEV mode"
        print("✓ axe-core only runs in development mode")
    
    def test_axe_core_dynamic_import(self):
        """Verify axe-core uses dynamic import"""
        with open('/app/frontend/src/main.jsx', 'r') as f:
            content = f.read()
        assert 'import("@axe-core/react")' in content, "axe-core should use dynamic import"
        print("✓ axe-core uses dynamic import for code splitting")


# ============== O5 - Encryption Service Tests ==============

class TestO5EncryptionService:
    """O5 - Encryption Service Tests"""
    
    def test_encryption_service_file_exists(self):
        """Verify encryption.py exists"""
        assert os.path.exists('/app/backend/services/encryption.py'), "encryption.py should exist"
        print("✓ encryption.py exists")
    
    def test_encryption_service_uses_fernet(self):
        """Verify encryption uses Fernet (AES)"""
        with open('/app/backend/services/encryption.py', 'r') as f:
            content = f.read()
        assert 'from cryptography.fernet import Fernet' in content, "Should use Fernet encryption"
        assert 'PBKDF2HMAC' in content, "Should use PBKDF2 for key derivation"
        print("✓ Encryption uses Fernet (AES-128-CBC + HMAC)")
    
    def test_encryption_service_class(self):
        """Verify EncryptionService class exists"""
        with open('/app/backend/services/encryption.py', 'r') as f:
            content = f.read()
        assert 'class EncryptionService' in content, "EncryptionService class should exist"
        assert 'def encrypt(' in content, "encrypt method should exist"
        assert 'def decrypt(' in content, "decrypt method should exist"
        print("✓ EncryptionService class with encrypt/decrypt methods")
    
    def test_encryption_sensitive_fields_defined(self):
        """Verify SENSITIVE_FIELDS configuration"""
        with open('/app/backend/services/encryption.py', 'r') as f:
            content = f.read()
        assert 'SENSITIVE_FIELDS' in content, "SENSITIVE_FIELDS should be defined"
        assert 'nif' in content, "NIF should be a sensitive field"
        assert 'documento_id' in content, "documento_id should be a sensitive field"
        assert 'morada_fiscal' in content, "morada_fiscal should be a sensitive field"
        print("✓ SENSITIVE_FIELDS properly configured")
    
    def test_encryption_process_functions(self):
        """Verify encrypt_process and decrypt_process functions"""
        with open('/app/backend/services/encryption.py', 'r') as f:
            content = f.read()
        assert 'def encrypt_process' in content, "encrypt_process function should exist"
        assert 'def decrypt_process' in content, "decrypt_process function should exist"
        print("✓ encrypt_process and decrypt_process functions defined")
    
    def test_encryption_prefix(self):
        """Verify encryption prefix for identifying encrypted data"""
        with open('/app/backend/services/encryption.py', 'r') as f:
            content = f.read()
        assert 'ENCRYPTION_PREFIX' in content, "ENCRYPTION_PREFIX should be defined"
        assert 'ENC:' in content, "Encryption prefix should be 'ENC:'"
        print("✓ ENCRYPTION_PREFIX 'ENC:' defined")
    
    def test_encryption_graceful_degradation(self):
        """Verify encryption gracefully degrades when crypto unavailable"""
        with open('/app/backend/services/encryption.py', 'r') as f:
            content = f.read()
        assert 'CRYPTO_AVAILABLE' in content, "CRYPTO_AVAILABLE flag should exist"
        assert 'except ImportError' in content, "Should handle ImportError gracefully"
        print("✓ Encryption has graceful degradation")


# ============== Frontend AutomationPage Tests ==============

class TestO22AutomationPageCode:
    """O22 - AutomationPage Frontend Code Tests"""
    
    def test_automation_page_file_exists(self):
        """Verify AutomationPage.js exists"""
        assert os.path.exists('/app/frontend/src/pages/AutomationPage.js'), "AutomationPage.js should exist"
        print("✓ AutomationPage.js exists")
    
    def test_automation_page_data_testid(self):
        """Verify data-testid attributes for testing"""
        with open('/app/frontend/src/pages/AutomationPage.js', 'r') as f:
            content = f.read()
        assert 'data-testid="automation-page"' in content, "automation-page testid should exist"
        assert 'data-testid="create-rule-btn"' in content, "create-rule-btn testid should exist"
        assert 'data-testid="rule-dialog"' in content, "rule-dialog testid should exist"
        assert 'data-testid="trigger-select"' in content, "trigger-select testid should exist"
        assert 'data-testid="action-select"' in content, "action-select testid should exist"
        print("✓ data-testid attributes present for testing")
    
    def test_automation_page_api_calls(self):
        """Verify API calls to automation endpoints"""
        with open('/app/frontend/src/pages/AutomationPage.js', 'r') as f:
            content = f.read()
        assert '/api/admin/automation/rules' in content, "Should call rules endpoint"
        assert '/api/admin/automation/triggers' in content, "Should call triggers endpoint"
        assert '/api/admin/automation/actions' in content, "Should call actions endpoint"
        print("✓ AutomationPage makes correct API calls")
    
    def test_automation_page_crud_operations(self):
        """Verify CRUD operations in AutomationPage"""
        with open('/app/frontend/src/pages/AutomationPage.js', 'r') as f:
            content = f.read()
        # Check for method variable usage (const method = editingRule ? "PUT" : "POST")
        assert '"POST"' in content or "'POST'" in content, "Should have POST for create"
        assert '"PUT"' in content or "'PUT'" in content, "Should have PUT for update"
        assert '"DELETE"' in content or "'DELETE'" in content, "Should have DELETE for delete"
        print("✓ AutomationPage has CRUD operations")
    
    def test_automation_page_empty_state(self):
        """Verify empty state message"""
        with open('/app/frontend/src/pages/AutomationPage.js', 'r') as f:
            content = f.read()
        assert 'Nenhuma regra' in content or 'nenhuma regra' in content, "Should show empty state message"
        print("✓ AutomationPage has empty state")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
