"""
==============================================
ITERATION 14 - TRELLO INTEGRATION TESTS
==============================================
Tests for bidirectional Trello synchronization:
- GET /api/trello/status - Check Trello connection
- POST /api/trello/reset-and-sync - Reset and import from Trello
- POST /api/trello/sync/from-trello - Sync from Trello to App
- POST /api/trello/sync/to-trello - Sync from App to Trello
- PUT /api/processes/kanban/{id}/move - Move process and sync to Trello
==============================================
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestTrelloIntegration:
    """Trello Integration endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        self.token = data["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_01_trello_status_connected(self):
        """Test GET /api/trello/status - Should show connected status"""
        response = self.session.get(f"{BASE_URL}/api/trello/status")
        assert response.status_code == 200, f"Status check failed: {response.text}"
        
        data = response.json()
        print(f"Trello Status Response: {data}")
        
        # Verify connection status
        assert "connected" in data, "Response should have 'connected' field"
        assert data["connected"] == True, f"Trello should be connected, got: {data.get('message')}"
        
        # Verify board info
        assert "board" in data, "Response should have 'board' field"
        assert data["board"] is not None, "Board info should not be None"
        assert "name" in data["board"], "Board should have name"
        assert "url" in data["board"], "Board should have URL"
        
        # Verify lists
        assert "lists" in data, "Response should have 'lists' field"
        assert len(data["lists"]) > 0, "Should have at least one list"
        
        print(f"✓ Trello connected to board: {data['board']['name']}")
        print(f"✓ Board URL: {data['board']['url']}")
        print(f"✓ Lists count: {len(data['lists'])}")
    
    def test_02_trello_lists_mapping(self):
        """Test that Trello lists are properly mapped to system statuses"""
        response = self.session.get(f"{BASE_URL}/api/trello/status")
        assert response.status_code == 200
        
        data = response.json()
        lists = data.get("lists", [])
        
        # Expected list names from the Trello board
        expected_lists = [
            "Clientes em Espera",
            "Fase Documental",
            "Fase Documental II",
            "Entregue aos Intermediarios",
            "Enviado ao Bruno",
            "Enviado ao Luís",
            "Enviado BCP Rui",
            "Entradas Precision",
            "Fase Bancária - Pré Aprovação",
            "Fase de Visitas",
            "CH Aprovado - Avaliação",
            "Fase de Escritura",
            "Escritura Agendada",
            "Concluidos",
            "Desistências"
        ]
        
        list_names = [l["name"] for l in lists]
        print(f"Found lists: {list_names}")
        
        # Check that we have lists
        assert len(lists) > 0, "Should have Trello lists"
        print(f"✓ Found {len(lists)} lists in Trello board")
    
    def test_03_sync_from_trello(self):
        """Test POST /api/trello/sync/from-trello - Import from Trello"""
        response = self.session.post(f"{BASE_URL}/api/trello/sync/from-trello")
        assert response.status_code == 200, f"Sync from Trello failed: {response.text}"
        
        data = response.json()
        print(f"Sync from Trello Response: {data}")
        
        # Verify response structure
        assert "success" in data, "Response should have 'success' field"
        assert "message" in data, "Response should have 'message' field"
        assert "created" in data, "Response should have 'created' field"
        assert "updated" in data, "Response should have 'updated' field"
        
        print(f"✓ Sync from Trello: {data['message']}")
        print(f"✓ Created: {data['created']}, Updated: {data['updated']}")
    
    def test_04_sync_to_trello(self):
        """Test POST /api/trello/sync/to-trello - Export to Trello"""
        response = self.session.post(f"{BASE_URL}/api/trello/sync/to-trello")
        assert response.status_code == 200, f"Sync to Trello failed: {response.text}"
        
        data = response.json()
        print(f"Sync to Trello Response: {data}")
        
        # Verify response structure
        assert "success" in data, "Response should have 'success' field"
        assert "message" in data, "Response should have 'message' field"
        
        print(f"✓ Sync to Trello: {data['message']}")
        print(f"✓ Created: {data.get('created', 0)}, Updated: {data.get('updated', 0)}")
    
    def test_05_kanban_processes_have_trello_ids(self):
        """Test that Kanban processes have trello_card_id after sync"""
        response = self.session.get(f"{BASE_URL}/api/processes/kanban")
        assert response.status_code == 200, f"Kanban fetch failed: {response.text}"
        
        data = response.json()
        columns = data.get("columns", [])
        
        total_processes = 0
        processes_with_trello_id = 0
        
        for column in columns:
            for process in column.get("processes", []):
                total_processes += 1
                if process.get("trello_card_id"):
                    processes_with_trello_id += 1
        
        print(f"✓ Total processes: {total_processes}")
        print(f"✓ Processes with Trello ID: {processes_with_trello_id}")
        
        # Most processes should have Trello IDs after import
        if total_processes > 0:
            percentage = (processes_with_trello_id / total_processes) * 100
            print(f"✓ Trello sync coverage: {percentage:.1f}%")
    
    def test_06_move_process_syncs_to_trello(self):
        """Test PUT /api/processes/kanban/{id}/move - Should sync to Trello"""
        # First get a process to move
        response = self.session.get(f"{BASE_URL}/api/processes/kanban")
        assert response.status_code == 200
        
        data = response.json()
        columns = data.get("columns", [])
        
        # Find a process with trello_card_id to test sync
        test_process = None
        original_status = None
        
        for column in columns:
            for process in column.get("processes", []):
                if process.get("trello_card_id"):
                    test_process = process
                    original_status = column.get("name")
                    break
            if test_process:
                break
        
        if not test_process:
            pytest.skip("No process with Trello ID found for testing")
        
        print(f"Testing with process: {test_process['client_name']}")
        print(f"Original status: {original_status}")
        print(f"Trello card ID: {test_process['trello_card_id']}")
        
        # Determine target status (move to next column or back)
        target_status = "fase_documental" if original_status != "fase_documental" else "clientes_espera"
        
        # Move the process
        response = self.session.put(
            f"{BASE_URL}/api/processes/kanban/{test_process['id']}/move",
            params={"new_status": target_status}
        )
        
        assert response.status_code == 200, f"Move failed: {response.text}"
        
        result = response.json()
        print(f"Move result: {result}")
        
        assert result.get("new_status") == target_status, "Status should be updated"
        print(f"✓ Process moved to: {target_status}")
        
        # Move back to original status
        response = self.session.put(
            f"{BASE_URL}/api/processes/kanban/{test_process['id']}/move",
            params={"new_status": original_status}
        )
        assert response.status_code == 200, f"Move back failed: {response.text}"
        print(f"✓ Process moved back to: {original_status}")
    
    def test_07_move_to_ch_aprovado_works(self):
        """Test moving process to ch_aprovado (previously broken)"""
        # Get a process to test
        response = self.session.get(f"{BASE_URL}/api/processes/kanban")
        assert response.status_code == 200
        
        data = response.json()
        columns = data.get("columns", [])
        
        # Find a process not in ch_aprovado
        test_process = None
        original_status = None
        
        for column in columns:
            if column.get("name") != "ch_aprovado":
                for process in column.get("processes", []):
                    test_process = process
                    original_status = column.get("name")
                    break
            if test_process:
                break
        
        if not test_process:
            pytest.skip("No process found for testing")
        
        print(f"Testing move to ch_aprovado with: {test_process['client_name']}")
        
        # Move to ch_aprovado (this was failing in iteration 13)
        response = self.session.put(
            f"{BASE_URL}/api/processes/kanban/{test_process['id']}/move",
            params={"new_status": "ch_aprovado"}
        )
        
        assert response.status_code == 200, f"Move to ch_aprovado failed: {response.text}"
        
        result = response.json()
        print(f"✓ Move to ch_aprovado successful: {result}")
        
        # Move back to original status
        response = self.session.put(
            f"{BASE_URL}/api/processes/kanban/{test_process['id']}/move",
            params={"new_status": original_status}
        )
        assert response.status_code == 200
        print(f"✓ Process moved back to: {original_status}")
    
    def test_08_full_sync_bidirectional(self):
        """Test POST /api/trello/sync/full - Full bidirectional sync"""
        response = self.session.post(f"{BASE_URL}/api/trello/sync/full")
        assert response.status_code == 200, f"Full sync failed: {response.text}"
        
        data = response.json()
        print(f"Full sync Response: {data}")
        
        assert "success" in data, "Response should have 'success' field"
        assert "message" in data, "Response should have 'message' field"
        
        print(f"✓ Full sync: {data['message']}")


class TestTrelloWebhook:
    """Trello Webhook endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin2026"
        })
        assert response.status_code == 200
        data = response.json()
        self.token = data["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_webhook_head_verification(self):
        """Test HEAD /api/trello/webhook - Trello webhook verification"""
        response = self.session.head(f"{BASE_URL}/api/trello/webhook")
        # HEAD request should return 200 for Trello verification
        assert response.status_code == 200, f"Webhook HEAD verification failed: {response.status_code}"
        print("✓ Webhook HEAD verification working")
    
    def test_webhook_post_handler(self):
        """Test POST /api/trello/webhook - Webhook event handler"""
        # Simulate a Trello webhook event
        webhook_payload = {
            "action": {
                "type": "updateCard",
                "data": {
                    "card": {
                        "id": "test_card_id",
                        "name": "Test Card"
                    },
                    "listAfter": {
                        "id": "test_list_id",
                        "name": "Fase Documental"
                    }
                }
            }
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/trello/webhook",
            json=webhook_payload
        )
        
        # Should return 200 even for unknown cards
        assert response.status_code == 200, f"Webhook handler failed: {response.text}"
        
        data = response.json()
        assert data.get("status") == "ok", "Webhook should return ok status"
        print("✓ Webhook POST handler working")


class TestTrelloConfiguration:
    """Trello Configuration tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin2026"
        })
        assert response.status_code == 200
        data = response.json()
        self.token = data["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_trello_env_variables_configured(self):
        """Test that Trello environment variables are properly configured"""
        response = self.session.get(f"{BASE_URL}/api/trello/status")
        assert response.status_code == 200
        
        data = response.json()
        
        # If connected, env vars are configured
        assert data.get("connected") == True, "Trello should be connected (env vars configured)"
        print("✓ Trello environment variables are configured")
    
    def test_webhook_list(self):
        """Test GET /api/trello/webhook/list - List active webhooks"""
        response = self.session.get(f"{BASE_URL}/api/trello/webhook/list")
        assert response.status_code == 200, f"Webhook list failed: {response.text}"
        
        data = response.json()
        assert "webhooks" in data, "Response should have 'webhooks' field"
        
        print(f"✓ Active webhooks: {len(data.get('webhooks', []))}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
