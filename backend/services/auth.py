"""
====================================================================
SERVIÇO DE AUTENTICAÇÃO — CREDITOIMO
====================================================================
Módulo central de autenticação e autorização do PowerCell CRM.

ARQUITETURA:
- JWT (JSON Web Tokens) para autenticação stateless.
  Cada token contém: user_id (sub), email, role e timestamp de expiração.
  O token é assinado com HMAC-SHA256 usando JWT_SECRET.
- bcrypt (via passlib) para hashing de passwords.
  O bcrypt é usado deliberadamente (em vez de argon2) por ser o standard
  da indústria, ter ampla compatibilidade com libs de autenticação externas
  (ex: seed.py, scripts de migração) e oferecer salt automático com custo
  de trabalho configurável.
- Role-based access control (RBAC) implementado como FastAPI Dependencies.
  Isto permite proteger endpoints com ``Depends(require_roles([...]))``
  sem lógica de autorização inline.

DECISÕES ARQUITECTURAIS:
- Passlib com bcrypt em vez de bcrypt directo: evita incompatibilidades
  de formato entre módulos (seed.py, auth.py) que possam usar versões
  diferentes da lib bcrypt.
- ``deprecated="auto"`` no CryptContext: permite migrar para hashers
  mais recentes (ex: argon2) sem quebrar passwords existentes.
- Token com expiração curta (JWT_EXPIRATION_HOURS): compromise entre
  segurança (token curto = menor janela de exploração) e UX
  (token longo = menos re-logins).
====================================================================
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import re
from passlib.context import CryptContext

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from database import db
from models.auth import UserRole


security = HTTPBearer()

# Password hashing context — unificado com seed.py (passlib)
# Isto resolve incompatibilidade entre bcrypt directo e passlib
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Valida a força da password.
    
    Requisitos mínimos:
    - Pelo menos 8 caracteres
    - Pelo menos uma letra minúscula
    - Pelo menos uma letra maiúscula
    - Pelo menos um dígito
    - Pelo menos um carácter especial (@$!%*?&)
    
    Returns:
        Tuple[bool, str]: (válido, mensagem de erro)
    """
    if len(password) < 8:
        return False, "Password deve ter pelo menos 8 caracteres"
    
    if len(password) > 128:
        return False, "Password não pode exceder 128 caracteres"
    
    if not re.search(r'[a-z]', password):
        return False, "Password deve conter pelo menos uma letra minúscula"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password deve conter pelo menos uma letra maiúscula"
    
    if not re.search(r'\d', password):
        return False, "Password deve conter pelo menos um dígito"
    
    if not re.search(r'[@$!%*?&#^()\-_=+\[\]{}|;:,.<>~`]', password):
        return False, "Password deve conter pelo menos um carácter especial (@$!%*?& etc.)"
    
    # Verificar passwords comuns fracas
    common_passwords = [
        'password', 'Password1!', '12345678', 'qwerty123', 'admin123',
        'letmein1!', 'welcome1!', 'Password123!', 'Admin123!'
    ]
    if password.lower() in [p.lower() for p in common_passwords]:
        return False, "Password é demasiado comum. Escolha uma password mais segura."
    
    return True, ""


def hash_password(password: str) -> str:
    """Gera um hash bcrypt seguro para uma password em texto claro.

    Utiliza passlib (que internamente delega no bcrypt) para garantir
    compatibilidade de formato com outros módulos do sistema (ex: seed.py).
    Cada invocação gera um salt aleatório — hashes diferentes para a mesma
    password, mas ``verify_password()`` consegue comparar corretamente.

    Args:
        password: Password em texto claro. Deve ser validada por
            ``validate_password_strength()`` antes de chamar esta função.

    Returns:
        str: Hash bcrypt com formato ``$2b$12$...`` (pronto para guardar na BD).
    """
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verifica se uma password em texto claro corresponde a um hash bcrypt.

    Função crítica no fluxo de login — compara a password fornecida com o
    hash armazenado na base de dados. Se o formato do hash for incompatível
    (ex: versão diferente de bcrypt), passlib tenta automaticamente uma
    verificação de contingência graças a ``deprecated="auto"``.

    Args:
        password: Password em texto claro (fornecida pelo utilizador).
        hashed: Hash bcrypt armazenado na base de dados.

    Returns:
        bool: True se a password corresponde ao hash, False caso contrário.
    """
    return pwd_context.verify(password, hashed)


def create_token(user_id: str, email: str, role: str) -> str:
    """Cria um token JWT com os dados essenciais do utilizador autenticado.

    O token é usado em todas as requests subsequentes como mecanismo de
    autenticação stateless. Contém o user_id como ``sub`` (subject), email
    e role para autorização rápida sem consulta à BD. A expiração é definida
    por ``JWT_EXPIRATION_HOURS`` para limitar a janela de exploração em caso
    de roubo de token.

    Args:
        user_id: Identificador único do utilizador (campo ``id`` na BD).
        email: Email do utilizador (usado para identificação e logs).
        role: Role do utilizador (ex: ``UserRole.ADMIN``, ``UserRole.CONSULTOR``).
            É incluída no token para evitar lookup à BD em cada request.

    Returns:
        str: Token JWT codificado (string base64url).
    """
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(data: Dict[str, Any]) -> str:
    """
    Criar token JWT com dados personalizados.
    Usado para impersonate e outros cenários especiais.
    """
    payload = {
        **data,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency do FastAPI que extrai e valida o utilizador a partir do JWT.

    Esta é a dependency de autenticação principal — é injetada em todos os
    endpoints protegidos do CRM. O fluxo é:

    1. Extrai o token do header ``Authorization: Bearer <token>``.
    2. Decodifica e valida o JWT (assinatura + expiração).
    3. Procura o utilizador na BD pelo ``sub`` (user_id).
    4. Verifica se a conta está ativa.
    5. Se o token contém metadados de impersonate, adiciona-os ao utilizador.

    O suporte a impersonate permite que um admin assuma a identidade de outro
    utilizador para troubleshooting, sem revelar a password real.

    Args:
        credentials: Credenciais HTTP Bearer extraídas automaticamente pelo
            FastAPI (``HTTPBearer``).

    Returns:
        dict: Documento do utilizador da BD (sem ``_id``), com campos
            adicionais ``is_impersonated``, ``impersonated_by`` e
            ``impersonated_by_name`` se aplicável.

    Raises:
        HTTPException: 401 se o token estiver expirado, inválido, o utilizador
            não existir ou a conta estiver desativada.
    """
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Utilizador não encontrado")
        if not user.get("is_active", True):
            raise HTTPException(status_code=401, detail="Conta desativada")
        
        # Adicionar informação de impersonate se presente no token
        if payload.get("is_impersonated"):
            user["is_impersonated"] = True
            user["impersonated_by"] = payload.get("impersonated_by")
            user["impersonated_by_name"] = payload.get("impersonated_by_name")
        
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


def require_roles(allowed_roles: List[str]):
    """
    Dependency do FastAPI que verifica se o utilizador autenticado possui
    pelo menos um dos roles permitidos, incluindo roles adicionais.

    Porquê uma hierarquia de permissões implícita: em vez de exigir
    que cada endpoint liste explicitamente todos os roles com acesso,
    esta função implementa herança de permissões:
    - Admin: acesso total a tudo.
    - CEO: acesso a rotas de consultor, mediador e CEO.
    - Diretor: acesso a rotas de consultor, mediador e diretor.
    - Administrativo: acesso a rotas de consultor, mediador e administrativo.
    - Outros: verificação direta contra roles primário + adicionais.

    Isto simplifica a manutenção — ao adicionar um novo nível
    hierárquico, basta atualizar este ponto central.

    Args:
        allowed_roles: Lista de roles que têm permissão para aceder
            ao endpoint (ex: [UserRole.ADMIN, UserRole.CEO]).

    Returns:
        Callable: Dependency function para uso com ``Depends()``.

    Raises:
        HTTPException: 403 se o utilizador não tiver nenhum dos roles permitidos.
    """
    async def role_checker(user: dict = Depends(get_current_user)):
        user_role = user.get("role", "")
        additional_roles = user.get("additional_roles", [])
        
        # Combine primary role with additional roles for checking
        all_user_roles = [user_role] + (additional_roles if additional_roles else [])
        
        # Admin and CEO have access to most things
        if user_role == UserRole.ADMIN:
            return user
        
        # CEO has access to consultor and mediador routes
        if user_role == UserRole.CEO:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.CEO]):
                return user
        
        # Diretor has access to both consultor and mediador routes
        if user_role == UserRole.DIRETOR:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.DIRETOR]):
                return user
        
        # Administrativo has general access to most routes
        if user_role == UserRole.ADMINISTRATIVO:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.ADMINISTRATIVO]):
                return user
        
        # Standard role check - check against ALL user roles (primary + additional)
        if not any(r in allowed_roles for r in all_user_roles):
            raise HTTPException(status_code=403, detail="Permissão negada")
        return user
    return role_checker


def require_staff():
    """Dependency do FastAPI que restringe acesso a membros da equipa (staff).

    Um utilizador é considerado "staff" se o seu role não for "cliente".
    Isto é usado para endpoints internos (ex: dashboard administrativo,
    gestão de utilizadores) que nunca devem ser acessíveis por clientes.

    Retorna uma dependency function para uso com ``Depends()`` — o FastAPI
    injeta automaticamente o resultado de ``get_current_user`` como argumento
    da função interna.

    Returns:
        Callable: Função async que retorna o utilizador autenticado.

    Raises:
        HTTPException: 403 se o utilizador autenticado tiver role "cliente".
    """
    async def staff_checker(user: dict = Depends(get_current_user)):
        if not UserRole.is_staff(user["role"]):
            raise HTTPException(status_code=403, detail="Permissão negada")
        return user
    return staff_checker
