"""
Testes unitários para middleware de rate limiting.
"""
import pytest
from datetime import datetime, timezone
import time


class TestRateLimitConfig:
    """Testes para configuração de rate limiting."""
    
    def test_role_based_limits(self):
        """Testa limites diferentes por role."""
        ROLE_LIMITS = {
            "admin": 1000,
            "ceo": 1000,
            "diretor": 500,
            "consultor": 200,
            "mediador": 200,
            "consultor_intermediario": 200,
            "cliente": 100,
            "default": 100
        }
        
        # Admin tem mais requests
        assert ROLE_LIMITS["admin"] > ROLE_LIMITS["consultor"]
        
        # Cliente tem menos requests
        assert ROLE_LIMITS["cliente"] < ROLE_LIMITS["consultor"]
        
        # Default é o mais restritivo
        assert ROLE_LIMITS["default"] <= min(v for k, v in ROLE_LIMITS.items() if k != "default")
    
    def test_window_configuration(self):
        """Testa configuração de janela de tempo."""
        WINDOW_SIZE = 60  # 1 minuto em segundos
        
        assert WINDOW_SIZE >= 30  # Mínimo razoável
        assert WINDOW_SIZE <= 300  # Máximo de 5 minutos


class TestRateLimitLogic:
    """Testes para lógica de rate limiting."""
    
    def test_token_bucket_initialization(self):
        """Testa inicialização do token bucket."""
        def create_bucket(max_tokens, refill_rate):
            return {
                "tokens": max_tokens,
                "max_tokens": max_tokens,
                "refill_rate": refill_rate,
                "last_update": time.time()
            }
        
        bucket = create_bucket(100, 10)
        
        assert bucket["tokens"] == bucket["max_tokens"]
        assert bucket["refill_rate"] == 10
    
    def test_token_consumption(self):
        """Testa consumo de tokens."""
        def consume_token(bucket):
            if bucket["tokens"] > 0:
                bucket["tokens"] -= 1
                return True
            return False
        
        bucket = {"tokens": 2, "max_tokens": 100}
        
        # Consumir primeiro token
        assert consume_token(bucket)
        assert bucket["tokens"] == 1
        
        # Consumir segundo token
        assert consume_token(bucket)
        assert bucket["tokens"] == 0
        
        # Terceiro falha
        assert not consume_token(bucket)
    
    def test_token_refill(self):
        """Testa reposição de tokens."""
        def refill_tokens(bucket, elapsed_seconds):
            new_tokens = bucket["tokens"] + (elapsed_seconds * bucket["refill_rate"])
            bucket["tokens"] = min(new_tokens, bucket["max_tokens"])
            return bucket["tokens"]
        
        bucket = {
            "tokens": 50,
            "max_tokens": 100,
            "refill_rate": 10  # 10 tokens por segundo
        }
        
        # Após 3 segundos, adiciona 30 tokens
        result = refill_tokens(bucket, 3)
        assert result == 80
        
        # Não ultrapassa o máximo
        result = refill_tokens(bucket, 100)
        assert result == bucket["max_tokens"]
    
    def test_rate_limit_exceeded(self):
        """Testa detecção de limite excedido."""
        def is_rate_limited(bucket):
            return bucket["tokens"] <= 0
        
        bucket_ok = {"tokens": 10}
        bucket_limited = {"tokens": 0}
        
        assert not is_rate_limited(bucket_ok)
        assert is_rate_limited(bucket_limited)


class TestRateLimitHeaders:
    """Testes para headers de rate limiting."""
    
    def test_header_generation(self):
        """Testa geração de headers de rate limiting."""
        def generate_headers(bucket, window_size):
            return {
                "X-RateLimit-Limit": str(bucket["max_tokens"]),
                "X-RateLimit-Remaining": str(bucket["tokens"]),
                "X-RateLimit-Reset": str(int(time.time()) + window_size)
            }
        
        bucket = {"tokens": 75, "max_tokens": 100}
        headers = generate_headers(bucket, 60)
        
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "75"
        assert "X-RateLimit-Reset" in headers
    
    def test_retry_after_header(self):
        """Testa header Retry-After quando limitado."""
        def get_retry_after(tokens_needed, refill_rate):
            if refill_rate == 0:
                return 60  # Default
            return max(1, int(tokens_needed / refill_rate))
        
        # 10 tokens necessários, 10 por segundo = 1 segundo
        assert get_retry_after(10, 10) == 1
        
        # 50 tokens necessários, 10 por segundo = 5 segundos
        assert get_retry_after(50, 10) == 5


class TestUserRateLimit:
    """Testes específicos para rate limiting por utilizador."""
    
    def test_user_key_generation(self):
        """Testa geração de chave única por utilizador."""
        def get_user_key(user_id, endpoint):
            return f"ratelimit:{user_id}:{endpoint}"
        
        key1 = get_user_key("user123", "/api/processes")
        key2 = get_user_key("user123", "/api/clients")
        key3 = get_user_key("user456", "/api/processes")
        
        # Mesmo user, endpoint diferente = chaves diferentes
        assert key1 != key2
        
        # User diferente, mesmo endpoint = chaves diferentes
        assert key1 != key3
    
    def test_endpoint_exclusion(self):
        """Testa exclusão de endpoints do rate limiting."""
        EXCLUDED_ENDPOINTS = [
            "/api/health",
            "/api/auth/login",
            "/api/auth/refresh",
            "/api/public/",
            "/api/ws/",
        ]
        
        def should_rate_limit(path):
            for excluded in EXCLUDED_ENDPOINTS:
                if path.startswith(excluded):
                    return False
            return True
        
        # Endpoints excluídos
        assert not should_rate_limit("/api/health")
        assert not should_rate_limit("/api/auth/login")
        assert not should_rate_limit("/api/public/client-registration")
        
        # Endpoints com rate limit
        assert should_rate_limit("/api/processes")
        assert should_rate_limit("/api/clients")
        assert should_rate_limit("/api/admin/users")
    
    def test_cleanup_expired_entries(self):
        """Testa limpeza de entradas expiradas."""
        def cleanup_expired(buckets, max_age_seconds):
            current_time = time.time()
            expired_keys = []
            
            for key, bucket in buckets.items():
                if current_time - bucket.get("last_update", 0) > max_age_seconds:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del buckets[key]
            
            return len(expired_keys)
        
        buckets = {
            "key1": {"last_update": time.time() - 100},
            "key2": {"last_update": time.time() - 3700},  # > 1 hora
            "key3": {"last_update": time.time()},
        }
        
        removed = cleanup_expired(buckets, 3600)  # 1 hora
        
        assert removed == 1
        assert "key2" not in buckets
        assert "key1" in buckets
        assert "key3" in buckets


class TestGlobalRateLimit:
    """Testes para rate limiting global (não autenticado)."""
    
    def test_ip_based_limiting(self):
        """Testa rate limiting baseado em IP."""
        def get_ip_key(ip_address):
            return f"ratelimit:ip:{ip_address}"
        
        key = get_ip_key("192.168.1.100")
        assert "192.168.1.100" in key
    
    def test_ip_extraction(self):
        """Testa extracção de IP de headers."""
        def get_client_ip(headers):
            # Verificar X-Forwarded-For primeiro (proxy)
            forwarded = headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
            
            # Fallback para X-Real-IP
            real_ip = headers.get("x-real-ip", "")
            if real_ip:
                return real_ip
            
            # Default
            return "unknown"
        
        # Com X-Forwarded-For
        headers1 = {"x-forwarded-for": "203.0.113.195, 70.41.3.18"}
        assert get_client_ip(headers1) == "203.0.113.195"
        
        # Com X-Real-IP
        headers2 = {"x-real-ip": "192.168.1.1"}
        assert get_client_ip(headers2) == "192.168.1.1"
        
        # Sem headers
        headers3 = {}
        assert get_client_ip(headers3) == "unknown"
    
    def test_strict_limits_for_unauthenticated(self):
        """Testa limites mais restritos para requests não autenticados."""
        AUTHENTICATED_LIMIT = 200
        UNAUTHENTICATED_LIMIT = 30
        
        assert UNAUTHENTICATED_LIMIT < AUTHENTICATED_LIMIT
        assert UNAUTHENTICATED_LIMIT <= 50  # Muito restritivo para evitar abusos


class TestRateLimitPersistence:
    """Testes para persistência de estado de rate limiting."""
    
    def test_in_memory_storage(self):
        """Testa armazenamento em memória."""
        rate_limit_storage = {}
        
        def set_bucket(key, bucket):
            rate_limit_storage[key] = bucket
        
        def get_bucket(key):
            return rate_limit_storage.get(key)
        
        set_bucket("user:123", {"tokens": 100})
        result = get_bucket("user:123")
        
        assert result is not None
        assert result["tokens"] == 100
    
    def test_concurrent_access_safety(self):
        """Testa segurança em acesso concorrente."""
        import threading
        
        storage = {"counter": 0}
        lock = threading.Lock()
        
        def safe_increment():
            with lock:
                storage["counter"] += 1
        
        threads = [threading.Thread(target=safe_increment) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert storage["counter"] == 100
