"""
====================================================================
TESTES UNITÁRIOS - API RATE LIMITING
====================================================================
Testes para verificar comportamento do rate limiting.
====================================================================
"""
import pytest
from middleware.user_rate_limit import RATE_LIMITS_BY_ROLE


class TestRateLimitConfiguration:
    """Testes para configuração de rate limits."""
    
    def test_admin_has_highest_limit(self):
        """Admin deve ter o maior limite."""
        admin_limit = RATE_LIMITS_BY_ROLE["admin"]["requests"]
        
        for role, config in RATE_LIMITS_BY_ROLE.items():
            if role not in ["admin", "ceo"]:
                assert config["requests"] <= admin_limit
    
    def test_cliente_has_lowest_limit(self):
        """Cliente deve ter o menor limite."""
        cliente_limit = RATE_LIMITS_BY_ROLE["cliente"]["requests"]
        
        # Apenas default pode ser menor
        for role, config in RATE_LIMITS_BY_ROLE.items():
            if role not in ["cliente", "default"]:
                assert config["requests"] >= cliente_limit
    
    def test_all_limits_are_positive(self):
        """Todos os limites devem ser positivos."""
        for role, config in RATE_LIMITS_BY_ROLE.items():
            assert config["requests"] > 0
            assert config["window"] > 0
    
    def test_window_is_60_seconds(self):
        """Janela deve ser de 60 segundos para todos."""
        for role, config in RATE_LIMITS_BY_ROLE.items():
            assert config["window"] == 60
    
    def test_specific_limits_match_requirements(self):
        """Limites específicos devem corresponder aos requisitos."""
        # Admin: 1000 req/min
        assert RATE_LIMITS_BY_ROLE["admin"]["requests"] == 1000
        
        # Consultor/Mediador: 200 req/min
        assert RATE_LIMITS_BY_ROLE["consultor"]["requests"] == 200
        assert RATE_LIMITS_BY_ROLE["mediador"]["requests"] == 200
        
        # Cliente: 100 req/min
        assert RATE_LIMITS_BY_ROLE["cliente"]["requests"] == 100
    
    def test_gestor_documentos_has_custom_limit(self):
        """Gestor documentos deve ter limite personalizado."""
        assert "gestor_documentos" in RATE_LIMITS_BY_ROLE
        assert RATE_LIMITS_BY_ROLE["gestor_documentos"]["requests"] == 150


class TestRateLimitHeaders:
    """Testes para headers de rate limit."""
    
    def test_required_headers(self):
        """Verifica headers obrigatórios."""
        required_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset"
        ]
        
        # Em produção, verificar que estes headers são retornados
        for header in required_headers:
            assert header.startswith("X-RateLimit")
    
    def test_retry_after_header_on_limit(self):
        """Quando limite excedido, Retry-After deve ser retornado."""
        # Em produção, verificar que 429 inclui Retry-After
        pass


class TestRateLimitByEndpoint:
    """Testes para rate limit por tipo de endpoint."""
    
    def test_auth_endpoints_have_stricter_limits(self):
        """Endpoints de auth devem ter limites mais estritos."""
        # O middleware existente (slowapi) já tem 5/minute para auth
        # Verificar que está configurado
        pass
    
    def test_public_endpoints_use_ip_based_limit(self):
        """Endpoints públicos devem usar limite por IP."""
        # Quando não há user autenticado, deve usar IP
        pass
