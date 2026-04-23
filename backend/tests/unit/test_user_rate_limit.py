"""
====================================================================
TESTES UNITÁRIOS - RATE LIMITING POR UTILIZADOR
====================================================================
Testes para o sistema de rate limiting diferenciado por role.
====================================================================
"""
import pytest
import asyncio
from middleware.user_rate_limit import (
    InMemoryRateLimiter,
    RATE_LIMITS_BY_ROLE,
    get_rate_limits_config,
)


class TestRateLimitsConfig:
    """Testes para configuração de limites."""
    
    def test_admin_has_highest_limit(self):
        """Admin deve ter o maior limite."""
        admin_limit = RATE_LIMITS_BY_ROLE["admin"]["requests"]
        client_limit = RATE_LIMITS_BY_ROLE["cliente"]["requests"]
        assert admin_limit > client_limit
    
    def test_consultor_limit(self):
        """Consultor deve ter limite de 600 req/min."""
        assert RATE_LIMITS_BY_ROLE["consultor"]["requests"] == 600
        assert RATE_LIMITS_BY_ROLE["consultor"]["window"] == 60
    
    def test_cliente_limit(self):
        """Cliente deve ter limite de 400 req/min."""
        assert RATE_LIMITS_BY_ROLE["cliente"]["requests"] == 400
    
    def test_all_roles_have_limits(self):
        """Todos os roles devem ter limites definidos."""
        required_roles = ["admin", "ceo", "consultor", "cliente", "default"]
        for role in required_roles:
            assert role in RATE_LIMITS_BY_ROLE
            assert "requests" in RATE_LIMITS_BY_ROLE[role]
            assert "window" in RATE_LIMITS_BY_ROLE[role]


class TestInMemoryRateLimiter:
    """Testes para o rate limiter in-memory."""
    
    @pytest.fixture
    def limiter(self):
        return InMemoryRateLimiter()
    
    @pytest.mark.asyncio
    async def test_first_request_allowed(self, limiter):
        """Primeiro request deve ser permitido."""
        allowed, info = await limiter.is_allowed("user1", "admin")
        assert allowed == True
        assert info["remaining"] > 0
    
    @pytest.mark.asyncio
    async def test_tracks_requests(self, limiter):
        """Deve rastrear requests correctamente."""
        # Fazer 5 requests
        for i in range(5):
            await limiter.is_allowed("user1", "consultor")
        
        status = await limiter.get_status("user1", "consultor")
        assert status["current_requests"] == 5
    
    @pytest.mark.asyncio
    async def test_blocks_after_limit(self, limiter):
        """Deve bloquear após exceder limite."""
        # Usar role com limite baixo para teste
        limit = RATE_LIMITS_BY_ROLE["cliente"]["requests"]
        
        # Esgotar limite
        for i in range(limit):
            allowed, _ = await limiter.is_allowed("user_test", "cliente")
            assert allowed == True
        
        # Próximo request deve ser bloqueado
        allowed, info = await limiter.is_allowed("user_test", "cliente")
        assert allowed == False
        assert info["remaining"] == 0
        assert "retry_after" in info
    
    @pytest.mark.asyncio
    async def test_different_users_independent(self, limiter):
        """Utilizadores diferentes devem ter limites independentes."""
        cliente_limit = RATE_LIMITS_BY_ROLE["cliente"]["requests"]
        # Esgotar limite do user1
        for i in range(cliente_limit):
            await limiter.is_allowed("user1", "cliente")
        
        # user2 ainda deve poder fazer requests
        allowed, info = await limiter.is_allowed("user2", "cliente")
        assert allowed == True
        assert info["remaining"] == cliente_limit - 1
    
    @pytest.mark.asyncio
    async def test_stats(self, limiter):
        """Deve retornar estatísticas."""
        await limiter.is_allowed("user1", "admin")
        await limiter.is_allowed("user2", "admin")
        
        stats = limiter.get_stats()
        assert stats["active_users"] == 2
        assert stats["tracked_requests"] == 2
    
    def test_get_rate_limits_config(self):
        """Deve retornar cópia da configuração."""
        config = get_rate_limits_config()
        assert config == RATE_LIMITS_BY_ROLE
        # Verificar que é uma cópia, não a referência original
        config["admin"]["requests"] = 99999
        assert RATE_LIMITS_BY_ROLE["admin"]["requests"] != 99999
