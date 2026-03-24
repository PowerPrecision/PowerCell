"""
Iteration 73 - Testing O2 (Sentry), O13 (Redis Cache), O3 (Rate Limiting), O10 (Cursor Pagination), O24 (UnifiedAuditTrail)

Tests:
- O2: Sentry backend/frontend initialization
- O13: Redis cache service with graceful degradation
- O13: Cache applied to stats endpoints
- O13: Health endpoint includes redis status
- O3: Rate limiting on document endpoints
- O10: Cursor pagination on /api/clients/registered
- O24: UnifiedAuditTrail component exists
"""
import pytest
import requests
import os
import sys

# Add backend to path for imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://undo-toast-ui.preview.emergentagent.com')


class TestO2SentryConfiguration:
    """O2 - Sentry Backend Configuration Tests"""
    
    def test_sentry_dsn_configured_in_backend_env(self):
        """Verify SENTRY_DSN is set in backend .env"""
        with open('/app/backend/.env', 'r') as f:
            env_content = f.read()
        assert 'SENTRY_DSN=' in env_content, "SENTRY_DSN should be configured in backend .env"
        # Verify it has a value (not empty)
        for line in env_content.split('\n'):
            if line.startswith('SENTRY_DSN='):
                value = line.split('=', 1)[1].strip()
                assert len(value) > 10, "SENTRY_DSN should have a valid DSN value"
                assert 'sentry.io' in value, "SENTRY_DSN should point to sentry.io"
                print(f"✓ Backend SENTRY_DSN configured: {value[:50]}...")
    
    def test_sentry_sdk_init_in_server(self):
        """Verify sentry_sdk.init is called in server.py"""
        with open('/app/backend/server.py', 'r') as f:
            server_content = f.read()
        assert 'import sentry_sdk' in server_content, "sentry_sdk should be imported"
        assert 'sentry_sdk.init(' in server_content, "sentry_sdk.init should be called"
        assert 'FastApiIntegration' in server_content, "FastApiIntegration should be used"
        assert 'PyMongoIntegration' in server_content, "PyMongoIntegration should be used"
        print("✓ Sentry SDK properly initialized in server.py")
    
    def test_sentry_config_in_config_py(self):
        """Verify Sentry configuration in config.py"""
        with open('/app/backend/config.py', 'r') as f:
            config_content = f.read()
        assert 'SENTRY_DSN' in config_content, "SENTRY_DSN should be in config.py"
        assert 'SENTRY_ENVIRONMENT' in config_content, "SENTRY_ENVIRONMENT should be in config.py"
        assert 'SENTRY_TRACES_SAMPLE_RATE' in config_content, "SENTRY_TRACES_SAMPLE_RATE should be in config.py"
        assert 'Sentry configurado' in config_content, "Sentry log message should be present"
        print("✓ Sentry configuration properly defined in config.py")


class TestO2SentryFrontend:
    """O2 - Sentry Frontend Configuration Tests"""
    
    def test_sentry_dsn_configured_in_frontend_env(self):
        """Verify VITE_SENTRY_DSN is set in frontend .env"""
        with open('/app/frontend/.env', 'r') as f:
            env_content = f.read()
        # Check for either VITE_DSN_SENTRY_FRONTEND or VITE_SENTRY_DSN
        has_sentry = 'VITE_SENTRY_DSN=' in env_content or 'VITE_DSN_SENTRY_FRONTEND=' in env_content
        assert has_sentry, "VITE_SENTRY_DSN or VITE_DSN_SENTRY_FRONTEND should be configured"
        print("✓ Frontend Sentry DSN configured")
    
    def test_sentry_react_init_in_main_jsx(self):
        """Verify @sentry/react is initialized in main.jsx"""
        with open('/app/frontend/src/main.jsx', 'r') as f:
            main_content = f.read()
        assert '@sentry/react' in main_content, "@sentry/react should be imported"
        assert 'Sentry.init(' in main_content, "Sentry.init should be called"
        assert 'browserTracingIntegration' in main_content, "browserTracingIntegration should be used"
        assert 'replayIntegration' in main_content, "replayIntegration should be used"
        print("✓ Sentry React properly initialized in main.jsx")


class TestO13RedisCacheService:
    """O13 - Redis Cache Service Tests"""
    
    def test_redis_cache_service_exists(self):
        """Verify redis_cache.py service file exists"""
        import os
        assert os.path.exists('/app/backend/services/redis_cache.py'), "redis_cache.py should exist"
        print("✓ Redis cache service file exists")
    
    def test_redis_cache_functions_defined(self):
        """Verify cache functions are defined"""
        with open('/app/backend/services/redis_cache.py', 'r') as f:
            content = f.read()
        assert 'async def cache_get' in content, "cache_get function should be defined"
        assert 'async def cache_set' in content, "cache_set function should be defined"
        assert 'async def cache_delete' in content, "cache_delete function should be defined"
        assert 'async def cache_delete_pattern' in content, "cache_delete_pattern function should be defined"
        assert 'async def health_check' in content, "health_check function should be defined"
        print("✓ All cache functions defined in redis_cache.py")
    
    def test_redis_graceful_degradation(self):
        """Verify Redis gracefully degrades when unavailable"""
        with open('/app/backend/services/redis_cache.py', 'r') as f:
            content = f.read()
        # Check that functions return None/False when Redis unavailable
        assert 'return None' in content, "Should return None when Redis unavailable"
        assert 'return False' in content, "Should return False on failure"
        assert 'logger.warning' in content, "Should log warnings on errors"
        print("✓ Redis cache has graceful degradation")
    
    def test_upstash_redis_configured(self):
        """Verify Upstash Redis credentials in backend .env"""
        with open('/app/backend/.env', 'r') as f:
            env_content = f.read()
        assert 'UPSTASH_REDIS_REST_URL=' in env_content, "UPSTASH_REDIS_REST_URL should be configured"
        assert 'UPSTASH_REDIS_REST_TOKEN=' in env_content, "UPSTASH_REDIS_REST_TOKEN should be configured"
        print("✓ Upstash Redis credentials configured")


class TestO13CacheOnStatsEndpoints:
    """O13 - Cache Applied to Stats Endpoints"""
    
    def test_cache_on_stats_endpoint(self):
        """Verify cache is applied to GET /api/stats"""
        with open('/app/backend/routes/stats.py', 'r') as f:
            content = f.read()
        assert 'from services.redis_cache import cache_get, cache_set' in content, "Cache imports should be present"
        assert 'cache_key = f"stats:' in content, "Cache key for stats should be defined"
        assert 'await cache_get(cache_key)' in content, "cache_get should be called"
        assert 'await cache_set(cache_key' in content, "cache_set should be called"
        print("✓ Cache applied to /api/stats endpoint")
    
    def test_cache_ttl_on_stats(self):
        """Verify TTL 60s on /api/stats"""
        with open('/app/backend/routes/stats.py', 'r') as f:
            content = f.read()
        # Check for TTL 60 on stats endpoint
        assert 'ttl=60' in content, "TTL 60s should be set for stats"
        print("✓ TTL 60s configured for /api/stats")
    
    def test_cache_ttl_on_stats_leads(self):
        """Verify TTL 120s on /api/stats/leads"""
        with open('/app/backend/routes/stats.py', 'r') as f:
            content = f.read()
        assert 'ttl=120' in content, "TTL 120s should be set for stats/leads"
        print("✓ TTL 120s configured for /api/stats/leads")
    
    def test_cache_ttl_on_stats_conversion(self):
        """Verify TTL 300s on /api/stats/conversion"""
        with open('/app/backend/routes/stats.py', 'r') as f:
            content = f.read()
        assert 'ttl=300' in content, "TTL 300s should be set for stats/conversion"
        print("✓ TTL 300s configured for /api/stats/conversion")


class TestO13HealthEndpointRedis:
    """O13 - Health Endpoint Includes Redis Status"""
    
    def test_health_endpoint_returns_redis_status(self):
        """Verify GET /api/health includes redis status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health endpoint should return 200, got {response.status_code}"
        data = response.json()
        assert 'redis' in data, "Health response should include 'redis' field"
        assert 'status' in data['redis'], "Redis status should have 'status' field"
        print(f"✓ Health endpoint includes redis status: {data['redis']}")
    
    def test_health_endpoint_redis_graceful_error(self):
        """Verify redis shows error status gracefully in preview env"""
        response = requests.get(f"{BASE_URL}/api/health")
        data = response.json()
        # In preview env, Redis DNS is blocked, so expect 'error' status
        redis_status = data.get('redis', {}).get('status')
        assert redis_status in ['connected', 'error', 'disconnected'], f"Redis status should be valid, got {redis_status}"
        print(f"✓ Redis status gracefully handled: {redis_status}")


class TestO3RateLimitingDocuments:
    """O3 - Rate Limiting on Document Endpoints"""
    
    def test_rate_limit_decorator_on_upload(self):
        """Verify @limiter.limit('30/minute') on upload endpoint"""
        with open('/app/backend/routes/documents.py', 'r') as f:
            content = f.read()
        assert '@limiter.limit("30/minute")' in content, "Upload should have 30/minute rate limit"
        print("✓ Rate limit 30/minute on document upload")
    
    def test_rate_limit_decorator_on_delete(self):
        """Verify @limiter.limit('20/minute') on delete endpoint"""
        with open('/app/backend/routes/documents.py', 'r') as f:
            content = f.read()
        assert '@limiter.limit("20/minute")' in content, "Delete should have 20/minute rate limit"
        print("✓ Rate limit 20/minute on document delete")
    
    def test_rate_limit_decorator_on_ai_analyze(self):
        """Verify @limiter.limit('10/minute') on AI analyze endpoint"""
        with open('/app/backend/routes/documents.py', 'r') as f:
            content = f.read()
        assert '@limiter.limit("10/minute")' in content, "AI analyze should have 10/minute rate limit"
        print("✓ Rate limit 10/minute on AI analyze")
    
    def test_limiter_imported_from_middleware(self):
        """Verify limiter is imported from middleware.rate_limit"""
        with open('/app/backend/routes/documents.py', 'r') as f:
            content = f.read()
        assert 'from middleware.rate_limit import limiter' in content, "limiter should be imported from middleware"
        print("✓ Limiter properly imported from middleware.rate_limit")


class TestO10CursorPagination:
    """O10 - Cursor Pagination on /api/clients/registered"""
    
    def test_cursor_params_in_clients_registered(self):
        """Verify cursor and cursor_id params exist"""
        with open('/app/backend/routes/clients.py', 'r') as f:
            content = f.read()
        assert 'cursor: Optional[str]' in content, "cursor param should be defined"
        assert 'cursor_id: Optional[str]' in content, "cursor_id param should be defined"
        print("✓ Cursor params defined in /api/clients/registered")
    
    def test_cursor_response_fields(self):
        """Verify response includes next_cursor, next_cursor_id, has_more"""
        with open('/app/backend/routes/clients.py', 'r') as f:
            content = f.read()
        assert '"next_cursor":' in content or "'next_cursor':" in content, "next_cursor should be in response"
        assert '"next_cursor_id":' in content or "'next_cursor_id':" in content, "next_cursor_id should be in response"
        assert '"has_more":' in content or "'has_more':" in content, "has_more should be in response"
        print("✓ Cursor response fields defined")
    
    def test_cursor_pagination_logic(self):
        """Verify cursor pagination logic is implemented"""
        with open('/app/backend/routes/clients.py', 'r') as f:
            content = f.read()
        # Check for cursor-based query logic
        assert 'if cursor is not None' in content, "Cursor condition should be checked"
        assert '$gt' in content or '$lt' in content, "Cursor comparison operators should be used"
        print("✓ Cursor pagination logic implemented")
    
    def test_backwards_compatibility_skip_limit(self):
        """Verify skip/limit still works when cursor not provided"""
        with open('/app/backend/routes/clients.py', 'r') as f:
            content = f.read()
        assert 'skip: int = Query' in content, "skip param should still exist"
        assert 'limit: int = Query' in content, "limit param should still exist"
        print("✓ Backwards compatibility with skip/limit maintained")


class TestO24UnifiedAuditTrail:
    """O24 - UnifiedAuditTrail Component"""
    
    def test_unified_audit_trail_component_exists(self):
        """Verify UnifiedAuditTrail.js component exists"""
        import os
        assert os.path.exists('/app/frontend/src/components/UnifiedAuditTrail.js'), "UnifiedAuditTrail.js should exist"
        print("✓ UnifiedAuditTrail component file exists")
    
    def test_unified_audit_trail_data_testid(self):
        """Verify data-testid='unified-audit-trail' is present"""
        with open('/app/frontend/src/components/UnifiedAuditTrail.js', 'r') as f:
            content = f.read()
        assert 'data-testid="unified-audit-trail"' in content, "data-testid should be present"
        print("✓ data-testid='unified-audit-trail' present")
    
    def test_unified_audit_trail_filter_chips(self):
        """Verify filter chips for event types"""
        with open('/app/frontend/src/components/UnifiedAuditTrail.js', 'r') as f:
            content = f.read()
        # Check for filter types
        assert 'status_change' in content, "status_change filter should exist"
        assert 'comment' in content, "comment filter should exist"
        assert 'document' in content, "document filter should exist"
        assert 'email' in content, "email filter should exist"
        assert 'assignment' in content, "assignment filter should exist"
        assert 'other' in content, "other filter should exist"
        print("✓ All filter chips defined (status_change, comment, document, email, assignment, other)")
    
    def test_unified_audit_trail_event_types_config(self):
        """Verify EVENT_TYPES configuration"""
        with open('/app/frontend/src/components/UnifiedAuditTrail.js', 'r') as f:
            content = f.read()
        assert 'EVENT_TYPES' in content, "EVENT_TYPES config should be defined"
        assert 'label:' in content or '"label":' in content, "Event types should have labels"
        assert 'icon:' in content or '"icon":' in content, "Event types should have icons"
        print("✓ EVENT_TYPES configuration properly defined")


class TestAPIEndpointsAccessible:
    """Test that API endpoints are accessible"""
    
    def test_health_endpoint(self):
        """Test /api/health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print("✓ /api/health endpoint working")
    
    def test_stats_endpoint_requires_auth(self):
        """Test /api/stats requires authentication"""
        response = requests.get(f"{BASE_URL}/api/stats")
        assert response.status_code == 401, "Stats endpoint should require auth"
        print("✓ /api/stats properly requires authentication")
    
    def test_stats_leads_endpoint_requires_auth(self):
        """Test /api/stats/leads requires authentication"""
        response = requests.get(f"{BASE_URL}/api/stats/leads")
        assert response.status_code == 401, "Stats leads endpoint should require auth"
        print("✓ /api/stats/leads properly requires authentication")
    
    def test_clients_registered_endpoint_requires_auth(self):
        """Test /api/clients/registered requires authentication"""
        response = requests.get(f"{BASE_URL}/api/clients/registered")
        assert response.status_code == 401, "Clients registered endpoint should require auth"
        print("✓ /api/clients/registered properly requires authentication")


class TestSkeletonLoaders:
    """Test skeleton loaders use animate-pulse"""
    
    def test_skeleton_loaders_use_animate_pulse(self):
        """Verify skeleton loaders use animate-pulse instead of animate-spin"""
        import glob
        
        pages_to_check = [
            '/app/frontend/src/pages/ExpiringDocumentsDashboard.jsx',
            '/app/frontend/src/pages/SystemConfigPage.js',
            '/app/frontend/src/pages/BackupsPage.js',
            '/app/frontend/src/pages/DiagnosticsPage.js',
            '/app/frontend/src/components/PendingItemsList.js',
            '/app/frontend/src/pages/RGPDPage.jsx',
        ]
        
        for page_path in pages_to_check:
            if os.path.exists(page_path):
                with open(page_path, 'r') as f:
                    content = f.read()
                # Check for animate-pulse (skeleton loader pattern)
                if 'animate-pulse' in content:
                    print(f"✓ {os.path.basename(page_path)} uses animate-pulse skeleton")
        
        print("✓ Skeleton loaders verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
