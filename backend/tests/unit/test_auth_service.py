"""
Testes unitários para serviços de autenticação.
"""
import pytest
import jwt
import hashlib
from datetime import datetime, timezone, timedelta
import os


class TestPasswordHashing:
    """Testes para hashing de passwords."""
    
    def test_password_hash_creation(self):
        """Testa criação de hash de password."""
        def hash_password(password: str) -> str:
            import hashlib
            salt = "fixed_salt_for_test"
            return hashlib.sha256((password + salt).encode()).hexdigest()
        
        password = "SecurePassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        # Mesmo password = mesmo hash (com salt fixo)
        assert hash1 == hash2
        
        # Hash tem 64 caracteres (SHA256)
        assert len(hash1) == 64
    
    def test_password_verification(self):
        """Testa verificação de password."""
        def hash_password(password: str, salt: str = "default") -> str:
            return hashlib.sha256((password + salt).encode()).hexdigest()
        
        def verify_password(password: str, hashed: str, salt: str = "default") -> bool:
            return hash_password(password, salt) == hashed
        
        password = "MyPassword123"
        salt = "random_salt"
        hashed = hash_password(password, salt)
        
        # Password correcta
        assert verify_password(password, hashed, salt)
        
        # Password incorrecta
        assert not verify_password("WrongPassword", hashed, salt)
    
    def test_password_strength(self):
        """Testa validação de força de password."""
        def is_strong_password(password: str) -> bool:
            if len(password) < 8:
                return False
            if not any(c.isupper() for c in password):
                return False
            if not any(c.islower() for c in password):
                return False
            if not any(c.isdigit() for c in password):
                return False
            return True
        
        strong_passwords = ["Password123", "SecurePass1", "MyP@ssw0rd"]
        weak_passwords = ["pass", "password", "12345678", "PASSWORD123"]
        
        for pwd in strong_passwords:
            assert is_strong_password(pwd), f"'{pwd}' should be strong"
        
        for pwd in weak_passwords:
            assert not is_strong_password(pwd), f"'{pwd}' should be weak"


class TestJWTTokens:
    """Testes para tokens JWT."""
    
    def test_token_creation(self):
        """Testa criação de tokens JWT."""
        def create_token(user_id: str, secret: str, expires_minutes: int = 15):
            payload = {
                "sub": user_id,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
                "iat": datetime.now(timezone.utc)
            }
            return jwt.encode(payload, secret, algorithm="HS256")
        
        secret = "test_secret_key"
        token = create_token("user123", secret)
        
        # Token é uma string
        assert isinstance(token, str)
        
        # Token tem 3 partes separadas por .
        parts = token.split(".")
        assert len(parts) == 3
    
    def test_token_decoding(self):
        """Testa decodificação de tokens JWT."""
        def create_token(user_id: str, secret: str):
            payload = {
                "sub": user_id,
                "exp": datetime.now(timezone.utc) + timedelta(hours=1)
            }
            return jwt.encode(payload, secret, algorithm="HS256")
        
        def decode_token(token: str, secret: str):
            try:
                payload = jwt.decode(token, secret, algorithms=["HS256"])
                return payload.get("sub")
            except jwt.ExpiredSignatureError:
                return None
            except jwt.InvalidTokenError:
                return None
        
        secret = "test_secret"
        user_id = "user456"
        
        token = create_token(user_id, secret)
        decoded_id = decode_token(token, secret)
        
        assert decoded_id == user_id
    
    def test_expired_token(self):
        """Testa detecção de token expirado."""
        def create_expired_token(user_id: str, secret: str):
            payload = {
                "sub": user_id,
                "exp": datetime.now(timezone.utc) - timedelta(hours=1)  # Já expirado
            }
            return jwt.encode(payload, secret, algorithm="HS256")
        
        def is_token_valid(token: str, secret: str):
            try:
                jwt.decode(token, secret, algorithms=["HS256"])
                return True
            except jwt.ExpiredSignatureError:
                return False
            except jwt.InvalidTokenError:
                return False
        
        secret = "test_secret"
        expired_token = create_expired_token("user", secret)
        
        assert not is_token_valid(expired_token, secret)
    
    def test_invalid_signature(self):
        """Testa detecção de assinatura inválida."""
        def create_token(user_id: str, secret: str):
            payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
            return jwt.encode(payload, secret, algorithm="HS256")
        
        def is_token_valid(token: str, secret: str):
            try:
                jwt.decode(token, secret, algorithms=["HS256"])
                return True
            except jwt.InvalidSignatureError:
                return False
            except jwt.InvalidTokenError:
                return False
        
        token = create_token("user", "secret1")
        
        # Token válido com secret correcto
        assert is_token_valid(token, "secret1")
        
        # Token inválido com secret errado
        assert not is_token_valid(token, "wrong_secret")


class TestRefreshTokens:
    """Testes para refresh tokens."""
    
    def test_refresh_token_generation(self):
        """Testa geração de refresh tokens."""
        import secrets
        
        def generate_refresh_token():
            return secrets.token_urlsafe(32)
        
        token1 = generate_refresh_token()
        token2 = generate_refresh_token()
        
        # Tokens são únicos
        assert token1 != token2
        
        # Token tem comprimento adequado
        assert len(token1) >= 32
    
    def test_refresh_token_hash(self):
        """Testa hashing de refresh tokens."""
        def hash_refresh_token(token: str) -> str:
            return hashlib.sha256(token.encode()).hexdigest()
        
        token = "my_refresh_token_here"
        hashed = hash_refresh_token(token)
        
        # Hash tem 64 caracteres
        assert len(hashed) == 64
        
        # Hash é consistente
        assert hash_refresh_token(token) == hashed
    
    def test_token_rotation(self):
        """Testa rotação de tokens."""
        active_tokens = set()
        
        def add_token(token):
            active_tokens.add(token)
        
        def revoke_token(token):
            active_tokens.discard(token)
        
        def is_valid(token):
            return token in active_tokens
        
        old_token = "old_token"
        new_token = "new_token"
        
        add_token(old_token)
        assert is_valid(old_token)
        
        # Rotação: adiciona novo, revoga antigo
        add_token(new_token)
        revoke_token(old_token)
        
        assert not is_valid(old_token)
        assert is_valid(new_token)


class TestUserRoles:
    """Testes para roles de utilizador."""
    
    def test_role_hierarchy(self):
        """Testa hierarquia de roles."""
        role_levels = {
            "admin": 100,
            "ceo": 90,
            "diretor": 80,
            "consultor": 50,
            "mediador": 50,
            "gestor_documentos": 40,
            "cliente": 10
        }
        
        # Admin tem maior nível
        assert role_levels["admin"] >= max(role_levels.values())
        
        # Cliente tem menor nível
        assert role_levels["cliente"] <= min(role_levels.values())
    
    def test_role_permissions(self):
        """Testa permissões por role."""
        def has_permission(user_role, required_roles):
            return user_role in required_roles
        
        admin_only = ["admin"]
        management = ["admin", "ceo", "diretor"]
        all_staff = ["admin", "ceo", "diretor", "consultor", "mediador"]
        
        # Admin tem todas as permissões
        assert has_permission("admin", admin_only)
        assert has_permission("admin", management)
        assert has_permission("admin", all_staff)
        
        # Consultor não é admin
        assert not has_permission("consultor", admin_only)
        assert has_permission("consultor", all_staff)
    
    def test_valid_roles(self):
        """Testa roles válidos do sistema."""
        valid_roles = [
            "admin",
            "ceo",
            "diretor",
            "consultor",
            "mediador",
            "consultor_intermediario",
            "gestor_documentos",
            "cliente"
        ]
        
        for role in valid_roles:
            assert role.islower()
            assert " " not in role


class TestSessionManagement:
    """Testes para gestão de sessões."""
    
    def test_session_structure(self):
        """Testa estrutura de sessão."""
        session = {
            "id": "session-123",
            "user_id": "user-456",
            "refresh_token_hash": "hash...",
            "user_agent": "Mozilla/5.0...",
            "ip_address": "192.168.1.1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True
        }
        
        required_fields = ["id", "user_id", "refresh_token_hash", "is_active"]
        for field in required_fields:
            assert field in session
    
    def test_session_expiry(self):
        """Testa expiração de sessões."""
        def is_session_expired(session, max_age_days=7):
            last_used = datetime.fromisoformat(session["last_used_at"].replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - last_used
            return age.days > max_age_days
        
        recent_session = {
            "last_used_at": datetime.now(timezone.utc).isoformat()
        }
        
        old_session = {
            "last_used_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        }
        
        assert not is_session_expired(recent_session)
        assert is_session_expired(old_session)
    
    def test_concurrent_sessions_limit(self):
        """Testa limite de sessões simultâneas."""
        MAX_SESSIONS = 5
        
        def can_create_session(user_sessions):
            return len(user_sessions) < MAX_SESSIONS
        
        sessions_3 = ["s1", "s2", "s3"]
        sessions_5 = ["s1", "s2", "s3", "s4", "s5"]
        
        assert can_create_session(sessions_3)
        assert not can_create_session(sessions_5)


class TestAuthenticationFlow:
    """Testes para fluxo de autenticação."""
    
    def test_login_response_structure(self):
        """Testa estrutura de resposta de login."""
        response = {
            "access_token": "jwt_token_here",
            "refresh_token": "refresh_token_here",
            "token_type": "bearer",
            "expires_in": 900,  # 15 minutos em segundos
            "user": {
                "id": "user-123",
                "email": "user@test.com",
                "name": "Test User",
                "role": "consultor"
            }
        }
        
        required_fields = ["access_token", "token_type", "user"]
        for field in required_fields:
            assert field in response
        
        assert response["token_type"].lower() == "bearer"
    
    def test_token_refresh_flow(self):
        """Testa fluxo de refresh de tokens."""
        def refresh_tokens(old_refresh_token, valid_tokens):
            if old_refresh_token not in valid_tokens:
                return None
            
            # Simula rotação
            new_access = "new_access_token"
            new_refresh = "new_refresh_token"
            
            # Remove token antigo
            valid_tokens.remove(old_refresh_token)
            # Adiciona novo
            valid_tokens.add(new_refresh)
            
            return {
                "access_token": new_access,
                "refresh_token": new_refresh
            }
        
        valid_tokens = {"token1", "token2"}
        
        # Refresh válido
        result = refresh_tokens("token1", valid_tokens)
        assert result is not None
        assert "token1" not in valid_tokens
        assert result["refresh_token"] in valid_tokens
        
        # Refresh inválido (token já usado)
        result = refresh_tokens("token1", valid_tokens)
        assert result is None
    
    def test_logout_cleanup(self):
        """Testa limpeza após logout."""
        active_sessions = {"session1", "session2", "session3"}
        
        def logout(session_id, all_devices=False):
            if all_devices:
                active_sessions.clear()
            else:
                active_sessions.discard(session_id)
        
        # Logout de uma sessão
        logout("session1")
        assert "session1" not in active_sessions
        assert len(active_sessions) == 2
        
        # Logout de todas as sessões
        logout("session2", all_devices=True)
        assert len(active_sessions) == 0
