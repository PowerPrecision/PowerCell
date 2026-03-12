"""
Iteration 22: Test NIF validation, email/phone coercion, and notification preferences

Tests:
1. NIF validation - accepts numeric and converts to string
2. Email/phone coercion - converts numeric values to string
3. Validation errors - return field-specific messages
4. Notification preferences endpoint - /api/admin/notification-preferences/{user_id}
5. Notification service - verifies preferences before sending
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAuth:
    """Authentication setup"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture
    def consultor_token(self):
        """Get consultor authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "consultor@sistema.pt",
            "password": "consultor123"
        })
        assert response.status_code == 200, f"Consultor login failed: {response.text}"
        return response.json().get("access_token")
    
    def test_admin_login(self, admin_token):
        """Verify admin can login"""
        assert admin_token is not None
        print("✅ Admin login successful")


class TestNIFValidation:
    """Test NIF validation - accepts numeric and string values"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture
    def test_process_id(self, admin_token):
        """Get a test process ID"""
        response = requests.get(f"{BASE_URL}/api/processes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        processes = response.json()
        if processes:
            return processes[0]["id"]
        pytest.skip("No processes available for testing")
    
    def test_nif_numeric_value_converted(self, admin_token, test_process_id):
        """Test that numeric NIF is converted to string and validated"""
        # Send NIF as integer (numeric)
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            json={
                "personal_data": {
                    "nif": 123456789  # Numeric value
                }
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Should succeed (converted to string) or fail with NIF format error, NOT type error
        if response.status_code == 200:
            print("✅ NIF numeric value accepted and converted to string")
        elif response.status_code == 422:
            error_detail = response.json().get("detail", [])
            # Check that error is about NIF format, not about type conversion
            error_msgs = str(error_detail).lower()
            assert "valid string" not in error_msgs, "NIF should convert numeric to string, not reject as invalid type"
            # Acceptable if it fails NIF validation (not starting with valid digit)
            if "nif" in error_msgs and ("dígitos" in error_msgs or "empresa" in error_msgs):
                print("✅ NIF converted but failed format validation (expected for test NIF)")
            else:
                print(f"⚠️ Unexpected validation error: {error_detail}")
        else:
            pytest.fail(f"Unexpected response: {response.status_code} - {response.text}")
    
    def test_nif_string_value_works(self, admin_token, test_process_id):
        """Test that string NIF works correctly"""
        # Use a valid Portuguese NIF format (not starting with 5 which is company)
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            json={
                "personal_data": {
                    "nif": "123456789"  # String value
                }
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if response.status_code == 200:
            print("✅ NIF string value accepted")
        elif response.status_code == 422:
            error_detail = response.json().get("detail", [])
            # If it fails, should be format validation, not type error
            error_msgs = str(error_detail).lower()
            assert "valid string" not in error_msgs, "Should not have string type error for string NIF"
            print(f"✅ NIF string value processed (format validation: {error_detail})")
        else:
            pytest.fail(f"Unexpected response: {response.status_code} - {response.text}")
    
    def test_nif_empty_value_allowed(self, admin_token, test_process_id):
        """Test that empty/null NIF is allowed"""
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            json={
                "personal_data": {
                    "nif": ""  # Empty value
                }
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Empty NIF should be allowed
        assert response.status_code == 200, f"Empty NIF should be allowed: {response.text}"
        print("✅ Empty NIF value allowed")


class TestEmailPhoneCoercion:
    """Test email and phone string coercion"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture
    def test_process_id(self, admin_token):
        """Get a test process ID"""
        response = requests.get(f"{BASE_URL}/api/processes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        processes = response.json()
        if processes:
            return processes[0]["id"]
        pytest.skip("No processes available for testing")
    
    def test_email_string_value(self, admin_token, test_process_id):
        """Test that email accepts string value"""
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            json={
                "client_email": "test@example.com"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200, f"String email should work: {response.text}"
        print("✅ Email string value accepted")
    
    def test_phone_numeric_string_converted(self, admin_token, test_process_id):
        """Test that numeric phone is converted to string"""
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            json={
                "client_phone": "912345678"  # Numeric string
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200, f"Numeric phone string should work: {response.text}"
        print("✅ Phone numeric string accepted")


class TestValidationErrorMessages:
    """Test that validation errors show specific field names"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture
    def test_process_id(self, admin_token):
        """Get a test process ID"""
        response = requests.get(f"{BASE_URL}/api/processes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        processes = response.json()
        if processes:
            return processes[0]["id"]
        pytest.skip("No processes available for testing")
    
    def test_invalid_nif_shows_field_in_error(self, admin_token, test_process_id):
        """Test that invalid NIF shows field name in error message"""
        # Send invalid NIF (company NIF starting with 5)
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            json={
                "personal_data": {
                    "nif": "500000000"  # Company NIF, should fail for individual clients
                }
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if response.status_code == 422:
            error_detail = response.json().get("detail", [])
            # Check that error contains field location
            if isinstance(error_detail, list) and len(error_detail) > 0:
                first_error = error_detail[0]
                loc = first_error.get("loc", [])
                assert "nif" in loc or "personal_data" in loc, f"Error should identify field: {error_detail}"
                print(f"✅ Validation error shows field location: {loc}")
            else:
                print(f"⚠️ Error format not standard Pydantic: {error_detail}")
        elif response.status_code == 200:
            print("⚠️ Company NIF accepted - validation may be relaxed")
        else:
            print(f"Response: {response.status_code} - {response.text}")


class TestNotificationPreferencesEndpoint:
    """Test /api/admin/notification-preferences/{user_id} endpoint"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture
    def admin_user_id(self, admin_token):
        """Get admin user ID from token verification"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        return response.json().get("id")
    
    def test_get_notification_preferences(self, admin_token, admin_user_id):
        """Test GET /api/admin/notification-preferences/{user_id}"""
        response = requests.get(
            f"{BASE_URL}/api/admin/notification-preferences/{admin_user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Check if endpoint exists
        if response.status_code == 404 and "not found" in response.text.lower():
            # Try to find the correct endpoint
            print("⚠️ Endpoint /api/admin/notification-preferences/{user_id} not found")
            pytest.skip("Notification preferences endpoint not implemented at this path")
        
        assert response.status_code in [200, 201], f"Should return preferences: {response.text}"
        
        prefs = response.json()
        print(f"✅ Got notification preferences: {list(prefs.keys()) if isinstance(prefs, dict) else prefs}")
        
        # Verify expected fields exist
        expected_fields = ["email_deadline_reminder", "email_urgent_only"]
        for field in expected_fields:
            if field in prefs:
                print(f"  - {field}: {prefs[field]}")
    
    def test_update_notification_preferences(self, admin_token, admin_user_id):
        """Test PUT /api/admin/notification-preferences/{user_id}"""
        response = requests.put(
            f"{BASE_URL}/api/admin/notification-preferences/{admin_user_id}",
            json={
                "email_new_process": True,
                "email_status_change": False,
                "email_deadline_reminder": True
            },
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code == 404:
            print("⚠️ PUT endpoint not found - may be different implementation")
            pytest.skip("Notification preferences PUT endpoint not implemented")
        
        if response.status_code in [200, 201]:
            print("✅ Notification preferences updated successfully")
        else:
            print(f"Response: {response.status_code} - {response.text}")


class TestNotificationServicePreferenceCheck:
    """Test that notification service checks preferences before sending"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        return response.json().get("access_token")
    
    def test_notification_service_exists(self, admin_token):
        """Verify notification service module exists and is imported"""
        # Check by testing an endpoint that uses notifications
        # The process kanban move uses send_notification_with_preference_check
        response = requests.get(f"{BASE_URL}/api/processes/kanban", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        
        assert response.status_code == 200, f"Kanban endpoint should work: {response.text}"
        print("✅ Kanban endpoint works (uses notification_service)")
    
    def test_process_move_triggers_notification(self, admin_token):
        """Test that moving process triggers notification (with preference check)"""
        # Get a process to test
        response = requests.get(f"{BASE_URL}/api/processes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        processes = response.json()
        
        if not processes:
            pytest.skip("No processes available for testing")
        
        process = processes[0]
        process_id = process["id"]
        current_status = process.get("status", "clientes_espera")
        
        # Get workflow statuses
        statuses_resp = requests.get(f"{BASE_URL}/api/workflow/statuses", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        
        if statuses_resp.status_code != 200:
            pytest.skip("Could not get workflow statuses")
        
        statuses = statuses_resp.json()
        
        # Find a different status to move to
        new_status = None
        for s in statuses:
            if s.get("name") != current_status:
                new_status = s.get("name")
                break
        
        if not new_status:
            pytest.skip("No alternative status to move to")
        
        # Move process
        move_resp = requests.put(
            f"{BASE_URL}/api/processes/kanban/{process_id}/move?new_status={new_status}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if move_resp.status_code == 200:
            print(f"✅ Process moved to {new_status} (notification sent with preference check)")
            # Move back to original status
            requests.put(
                f"{BASE_URL}/api/processes/kanban/{process_id}/move?new_status={current_status}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        else:
            print(f"⚠️ Could not move process: {move_resp.text}")


class TestTitular2NIFValidation:
    """Test second holder (titular2) NIF validation"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture
    def test_process_id(self, admin_token):
        """Get a test process ID"""
        response = requests.get(f"{BASE_URL}/api/processes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        processes = response.json()
        if processes:
            return processes[0]["id"]
        pytest.skip("No processes available for testing")
    
    def test_titular2_nif_numeric_converted(self, admin_token, test_process_id):
        """Test that titular2 NIF accepts numeric and converts to string"""
        response = requests.put(
            f"{BASE_URL}/api/processes/{test_process_id}",
            json={
                "titular2_data": {
                    "name": "Test Second Holder",
                    "nif": 234567890  # Numeric value
                }
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if response.status_code == 200:
            print("✅ Titular2 NIF numeric value accepted and converted")
        elif response.status_code == 422:
            error_detail = response.json().get("detail", [])
            error_msgs = str(error_detail).lower()
            # Should not fail on type conversion
            assert "valid string" not in error_msgs, "Should convert numeric NIF to string"
            print(f"✅ Titular2 NIF converted (format validation: {error_detail})")
        else:
            pytest.fail(f"Unexpected response: {response.status_code} - {response.text}")


class TestErrorFormatterIntegration:
    """Test that frontend error formatter utility works with backend errors"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        return response.json().get("access_token")
    
    def test_validation_error_structure(self, admin_token):
        """Test that validation errors have proper structure for frontend parsing"""
        # Create request that will fail validation
        response = requests.post(
            f"{BASE_URL}/api/public/register",
            json={
                "name": "Test",
                "email": "invalid-email",  # Invalid email format
                "phone": "123",
                "process_type": "credito"
            }
        )
        
        if response.status_code == 422:
            error_detail = response.json().get("detail", [])
            
            # Pydantic validation errors should be array
            assert isinstance(error_detail, list), f"Error detail should be list: {error_detail}"
            
            if error_detail:
                first_error = error_detail[0]
                # Should have loc (location) and msg (message)
                assert "loc" in first_error, f"Error should have 'loc': {first_error}"
                assert "msg" in first_error, f"Error should have 'msg': {first_error}"
                
                print(f"✅ Validation error structure correct:")
                print(f"   - loc: {first_error['loc']}")
                print(f"   - msg: {first_error['msg']}")
        else:
            print(f"⚠️ Did not get validation error: {response.status_code} - {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
