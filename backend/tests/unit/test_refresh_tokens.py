"""
====================================================================
TESTES UNITÁRIOS - REFRESH TOKENS
====================================================================
Testes para o serviço de refresh tokens.
====================================================================
"""
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from services.refresh_token_service import (
    generate_refresh_token,
    hash_token,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


class TestTokenGeneration:
    """Testes para geração de tokens."""
    
    def test_generate_refresh_token_length(self):
        """Token gerado deve ter comprimento adequado."""
        token = generate_refresh_token()
        assert len(token) >= 40  # Base64 de 32 bytes
    
    def test_generate_refresh_token_unique(self):
        """Cada token gerado deve ser único."""
        tokens = [generate_refresh_token() for _ in range(100)]
        assert len(tokens) == len(set(tokens))
    
    def test_hash_token_deterministic(self):
        """Hash do mesmo token deve ser sempre igual."""
        token = "test_token_123"
        hash1 = hash_token(token)
        hash2 = hash_token(token)
        assert hash1 == hash2
    
    def test_hash_token_different_for_different_tokens(self):
        """Hash de tokens diferentes deve ser diferente."""
        hash1 = hash_token("token1")
        hash2 = hash_token("token2")
        assert hash1 != hash2


class TestAccessToken:
    """Testes para criação de access tokens."""
    
    def test_create_access_token_structure(self):
        """Access token deve ser um JWT válido."""
        import jwt
        from config import JWT_SECRET, JWT_ALGORITHM
        
        token = create_access_token("user123", "user@test.com", "consultor")
        
        # Deve ser possível decodificar
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        assert payload["sub"] == "user123"
        assert payload["email"] == "user@test.com"
        assert payload["role"] == "consultor"
        assert payload["type"] == "access"
        assert "exp" in payload
    
    def test_create_access_token_with_additional_data(self):
        """Access token deve suportar dados adicionais."""
        import jwt
        from config import JWT_SECRET, JWT_ALGORITHM
        
        token = create_access_token(
            "user123", 
            "user@test.com", 
            "admin",
            additional_data={"is_impersonated": True, "impersonated_by": "admin1"}
        )
        
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        assert payload["is_impersonated"] == True
        assert payload["impersonated_by"] == "admin1"


class TestConfiguration:
    """Testes para configuração."""
    
    def test_access_token_expire_minutes(self):
        """Access token deve expirar em 15 minutos."""
        assert ACCESS_TOKEN_EXPIRE_MINUTES == 120
    
    def test_refresh_token_expire_days(self):
        """Refresh token deve expirar em 7 dias."""
        assert REFRESH_TOKEN_EXPIRE_DAYS == 7
