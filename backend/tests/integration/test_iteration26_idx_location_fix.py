"""
Iteration 26: Test idx_location index fix and other features

Tests:
1. Login as admin (admin@admin.com / admin)
2. Verify /api/properties endpoint loads correctly
3. Test property creation (idx_location fix for duplicate key)
4. Test /api/admin/db/indexes/repair endpoint (Maintenance tab)
5. Test /api/auth/preferences endpoint (Notification preferences)
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestIteration26IdxLocationFix:
    """Test idx_location index fix and Maintenance features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test - get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        
        self.token = data["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.created_property_ids = []
        
        yield
        
        # Cleanup - delete created properties
        for prop_id in self.created_property_ids:
            try:
                self.session.delete(f"{BASE_URL}/api/properties/{prop_id}")
            except:
                pass
    
    def test_01_admin_login(self):
        """Test 1: Admin login works"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@admin.com",
            "password": "admin"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data.get("user", {}).get("role") == "admin"
        print("✅ Admin login successful")
    
    def test_02_properties_list(self):
        """Test 2: Verify /api/properties endpoint loads correctly"""
        response = self.session.get(f"{BASE_URL}/api/properties")
        assert response.status_code == 200, f"Properties list failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of properties"
        print(f"✅ Properties endpoint working - {len(data)} properties returned")
    
    def test_03_create_property_no_duplicate_key_error(self):
        """Test 3: Create property - verify idx_location fix (no duplicate key error)"""
        # Create first property with same district/municipality
        prop1_data = {
            "title": f"TEST_Property_Lisboa_1_{uuid.uuid4().hex[:8]}",
            "property_type": "apartamento",
            "address": {
                "district": "Lisboa",
                "municipality": "Lisboa",
                "locality": "Benfica",
                "street": "Rua de Teste 1"
            },
            "financials": {
                "asking_price": 250000
            },
            "owner": {
                "name": "Test Owner 1"
            },
            "status": "disponivel"
        }
        
        response1 = self.session.post(f"{BASE_URL}/api/properties", json=prop1_data)
        assert response1.status_code == 200, f"First property creation failed: {response1.text}"
        data1 = response1.json()
        assert "id" in data1
        self.created_property_ids.append(data1["id"])
        print(f"✅ First property created: {data1.get('internal_reference')}")
        
        # Create second property with SAME district/municipality 
        # This would fail with old idx_location index (duplicate key)
        prop2_data = {
            "title": f"TEST_Property_Lisboa_2_{uuid.uuid4().hex[:8]}",
            "property_type": "moradia",
            "address": {
                "district": "Lisboa",  # Same district
                "municipality": "Lisboa",  # Same municipality
                "locality": "Lumiar",
                "street": "Rua de Teste 2"
            },
            "financials": {
                "asking_price": 350000
            },
            "owner": {
                "name": "Test Owner 2"
            },
            "status": "disponivel"
        }
        
        response2 = self.session.post(f"{BASE_URL}/api/properties", json=prop2_data)
        assert response2.status_code == 200, f"Second property creation failed (idx_location issue?): {response2.text}"
        data2 = response2.json()
        assert "id" in data2
        self.created_property_ids.append(data2["id"])
        print(f"✅ Second property created: {data2.get('internal_reference')}")
        
        # Create third property with same location - triple check
        prop3_data = {
            "title": f"TEST_Property_Lisboa_3_{uuid.uuid4().hex[:8]}",
            "property_type": "loja",
            "address": {
                "district": "Lisboa",  # Same district
                "municipality": "Lisboa",  # Same municipality
                "locality": "Alfama",
                "street": "Rua de Teste 3"
            },
            "financials": {
                "asking_price": 150000
            },
            "owner": {
                "name": "Test Owner 3"
            },
            "status": "disponivel"
        }
        
        response3 = self.session.post(f"{BASE_URL}/api/properties", json=prop3_data)
        assert response3.status_code == 200, f"Third property creation failed: {response3.text}"
        data3 = response3.json()
        assert "id" in data3
        self.created_property_ids.append(data3["id"])
        print(f"✅ Third property created: {data3.get('internal_reference')}")
        
        print("✅ idx_location fix verified - 3 properties with same district/municipality created without duplicate key error!")
    
    def test_04_get_index_stats(self):
        """Test 4: Verify /api/admin/db/indexes endpoint works"""
        response = self.session.get(f"{BASE_URL}/api/admin/db/indexes")
        assert response.status_code == 200, f"Get indexes failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert "indexes" in data
        
        indexes = data.get("indexes", {})
        # Check properties collection has indexes
        if "properties" in indexes:
            prop_indexes = indexes["properties"]
            print(f"✅ Properties indexes: {prop_indexes.get('indexes', [])}")
        
        print(f"✅ Index stats retrieved successfully - {len(indexes)} collections")
    
    def test_05_repair_indexes(self):
        """Test 5: Verify /api/admin/db/indexes/repair endpoint (Maintenance tab)"""
        response = self.session.post(f"{BASE_URL}/api/admin/db/indexes/repair")
        assert response.status_code == 200, f"Repair indexes failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        
        # Check cleanup results
        cleanup = data.get("cleanup", {})
        dropped = cleanup.get("dropped", [])
        not_found = cleanup.get("not_found", [])
        
        # idx_location should be in either dropped (if it existed) or not_found (if already cleaned)
        # Check if properties.idx_location was handled
        has_idx_location_result = any("idx_location" in item for item in dropped + not_found)
        
        print(f"✅ Repair indexes completed:")
        print(f"   - Created: {len(data.get('created', []))}")
        print(f"   - Skipped (already exist): {len(data.get('skipped', []))}")
        print(f"   - Dropped deprecated: {dropped}")
        print(f"   - Not found (already removed): {not_found}")
    
    def test_06_notification_preferences(self):
        """Test 6: Verify /api/auth/preferences endpoint (notification settings)"""
        # Test PUT preferences
        preferences_data = {
            "notifications": {
                "email_new_process": True,
                "email_status_change": True,
                "email_document_expiry": False,
                "email_deadline_reminder": True
            }
        }
        
        response = self.session.put(f"{BASE_URL}/api/auth/preferences", json=preferences_data)
        assert response.status_code == 200, f"Save preferences failed: {response.text}"
        data = response.json()
        print(f"✅ Notification preferences saved successfully")
    
    def test_07_properties_stats(self):
        """Test 7: Verify /api/properties/stats endpoint"""
        response = self.session.get(f"{BASE_URL}/api/properties/stats")
        assert response.status_code == 200, f"Properties stats failed: {response.text}"
        data = response.json()
        assert "total" in data
        assert "by_status" in data or "disponivel" in data
        print(f"✅ Properties stats: Total={data.get('total')}")
    
    def test_08_system_config(self):
        """Test 8: Verify /api/system-config endpoint (SystemConfigPage)"""
        response = self.session.get(f"{BASE_URL}/api/system-config")
        assert response.status_code == 200, f"System config failed: {response.text}"
        data = response.json()
        assert "config" in data
        assert "fields" in data
        print(f"✅ System config loaded - sections: {list(data.get('fields', {}).keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
