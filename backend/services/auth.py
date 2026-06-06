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
from typing import List, Dict, Any, Tuple, Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import re
import logging
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

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
    """Verifica se uma password em texto claro corresponde a um hash.

    Aceita dois formatos de hash:
    - bcrypt (``$2b$12$...``): formato padrão e recomendado.
    - SHA-256 (64 hex chars): formato legacy do antigo seed_database.py.

    Esta compatibilidade backward permite migrar gradualmente os hashes
    sem resetar passwords. O login-v2 detecta hashes SHA-256 e re-hasha
    automaticamente para bcrypt após login bem-sucedido.

    Args:
        password: Password em texto claro (fornecida pelo utilizador).
        hashed: Hash armazenado na base de dados (bcrypt ou SHA-256).

    Returns:
        bool: True se a password corresponde ao hash, False caso contrário.
    """
    if not hashed:
        return False

    # bcrypt — formato padrão
    if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
        return pwd_context.verify(password, hashed)

    # SHA-256 legacy — compatibilidade backward com seed_database.py antigo
    import hashlib
    if len(hashed) == 64:
        sha256_hash = hashlib.sha256(password.encode()).hexdigest()
        return sha256_hash == hashed

    # Fallback para passlib (cobre outros formatos suportados)
    return pwd_context.verify(password, hashed)


def needs_rehash(hashed: str) -> bool:
    """Verifica se o hash precisa de ser actualizado para bcrypt.

    Quando um hash SHA-256 é detectado, indica que a password deve ser
    re-hashada com bcrypt após o próximo login bem-sucedido.

    Args:
        hashed: Hash armazenado na base de dados.

    Returns:
        bool: True se o hash é SHA-256 ou outro formato não-bcrypt.
    """
    if not hashed:
        return False
    return not (hashed.startswith("$2b$") or hashed.startswith("$2a$"))


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
        
        # CEO has access to consultor and intermediario routes
        if user_role == UserRole.CEO:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.CEO]):
                return user
        
        # Diretor has access to both consultor and intermediario routes
        if user_role == UserRole.DIRETOR:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR]):
                return user
        
        # Administrativo has general access to most routes
        if user_role == UserRole.ADMINISTRATIVO:
            if any(r in allowed_roles for r in [UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.ADMINISTRATIVO]):
                return user
        
        # Standard role check - check against ALL user roles (primary + additional)
        if not any(r in allowed_roles for r in all_user_roles):
            raise HTTPException(status_code=403, detail="Permissão negada")
        return user
    return role_checker


def get_effective_role(request: Request, user: dict) -> str:
    """
    Extrai o cargo efetivo do pedido HTTP, considerando o Context Isolation.
    
    Prioridade:
    1. Header X-Active-Role — se presente e válido para este utilizador
    2. user["role"] — cargo primário do JWT (fallback)
    
    Validação: O X-Active-Role só é aceite se existir no role primário
    OU na lista de additional_roles do utilizador. Isto impede que um
    utilizador simule um cargo que não lhe pertence.
    
    Args:
        request: Objeto FastAPI Request (para ler headers)
        user: Dicionário do utilizador (do JWT)
    
    Returns:
        str: O cargo efetivo a usar para filtragem de dados
    """
    active_role = request.headers.get("X-Active-Role")
    
    if not active_role:
        return user.get("role", "")
    
    # Normalizar para lowercase
    active_role = active_role.strip().lower()
    
    # Se for "all", retornar sentinel especial para processar multi-cargo
    if active_role == "all":
        return "__all_roles__"
    
    # Validar: o cargo deve ser o primário ou estar nos additional_roles
    user_primary = user.get("role", "")
    additional = user.get("additional_roles", []) or []
    
    if active_role == user_primary or active_role in additional:
        return active_role
    
    # Cargo inválido — ignorar e usar o primário
    logger.warning(
        f"X-Active-Role inválido: '{active_role}' para user {user.get('id')} "
        f"(primário: {user_primary}, adicionais: {additional}). "
        f"A usar cargo primário."
    )
    return user_primary


def get_all_user_roles(user: dict) -> list:
    """
    Retorna todos os cargos de um utilizador (primário + adicionais), sem duplicados.
    
    Args:
        user: Dicionário do utilizador (do JWT)
    
    Returns:
        list: Lista de cargos únicos
    """
    roles = [user.get("role", "")]
    additional = user.get("additional_roles", []) or []
    for r in additional:
        if r and r not in roles:
            roles.append(r)
    return [r for r in roles if r]


def require_admin():
    """Dependency do FastAPI que restringe acesso a administradores e CEO.

    Um utilizador é considerado "admin" se o seu role for ``UserRole.ADMIN``
    ou ``UserRole.CEO``. Isto é usado para endpoints sensíveis (ex: gestão
    de configs de email por empresa, configurações do sistema) que só devem
    ser acessíveis por administradores ou CEO.

    Retorna uma dependency function para uso com ``Depends()`` — o FastAPI
    injeta automaticamente o resultado de ``get_current_user`` como argumento
    da função interna.

    Returns:
        Callable: Função async que retorna o utilizador autenticado.

    Raises:
        HTTPException: 403 se o utilizador autenticado não tiver role de admin ou CEO.
    """
    return require_roles([UserRole.ADMIN, UserRole.CEO])


def require_management():
    """Dependency do FastAPI que restringe acesso a roles de gestão.

    Um utilizador é considerado "gestão" se o seu role for ``UserRole.ADMIN``,
    ``UserRole.CEO`` ou ``UserRole.ADMINISTRATIVO``. Isto é usado para endpoints
    de gestão operacional (ex: templates de email, estatísticas, RGPD,
    gestão de formulários) que devem ser acessíveis por toda a equipa de gestão.

    Retorna uma dependency function para uso com ``Depends()`` — o FastAPI
    injeta automaticamente o resultado de ``get_current_user`` como argumento
    da função interna.

    Returns:
        Callable: Função async que retorna o utilizador autenticado.

    Raises:
        HTTPException: 403 se o utilizador autenticado não tiver role de gestão.
    """
    return require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO])


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


def get_active_company_id(request: Request, user: dict) -> Optional[str]:
    """
    Extrai o contexto de empresa ativa do pedido HTTP.

    Prioridade:
    1. Header X-Company-Id — se presente e válido para este utilizador
    2. user["company"] — empresa padrão do utilizador (fallback)

    Validação: O X-Company-Id só é aceite se existir na coleção
    user_company_roles para este utilizador. Isto impede que um
    utilizador aceda a dados de empresas a que não pertence.

    Args:
        request: Objeto FastAPI Request (para ler headers)
        user: Dicionário do utilizador (do JWT)

    Returns:
        str | None: O company_id ativo, ou None se não houver contexto
    """
    active_company = request.headers.get("X-Company-Id")

    if not active_company:
        # Fallback: usar o campo company do utilizador
        return user.get("company") or None

    active_company = active_company.strip()

    # Importar db aqui para evitar circular imports
    import asyncio
    from database import db as _db

    # Validar: o utilizador deve ter associação com esta empresa
    # Usar cache em request.state para evitar queries repetidas
    cache_key = f"_company_valid_{active_company}"
    cached = getattr(request.state, cache_key, None) if hasattr(request, 'state') else None

    if cached is not None:
        return active_company if cached else (user.get("company") or None)

    try:
        # Synchronous check — we're in async context
        loop = asyncio.get_event_loop()

        async def _check():
            assoc = await _db.user_company_roles.find_one(
                {"user_id": user["id"], "company_id": active_company},
                {"_id": 0, "company_id": 1}
            )
            return assoc is not None

        is_valid = loop.run_until_complete(_check())

        # Cache result on request state
        if hasattr(request, 'state'):
            setattr(request.state, cache_key, is_valid)

        if is_valid:
            return active_company

    except Exception as e:
        logger.warning(
            f"[get_active_company_id] Erro ao validar X-Company-Id '{active_company}' "
            f"para user {user.get('id')}: {e}. A usar fallback."
        )

    # Fallback: usar campo company do user
    return user.get("company") or None


async def get_active_company_id_async(request: Request, user: dict) -> Optional[str]:
    """
    Versão assíncrona de get_active_company_id.

    Preferir esta versão em endpoints FastAPI (que já são async).

    Args:
        request: Objeto FastAPI Request (para ler headers)
        user: Dicionário do utilizador (do JWT)

    Returns:
        str | None: O company_id ativo, ou None se não houver contexto
    """
    active_company = request.headers.get("X-Company-Id")

    if not active_company:
        return user.get("company") or None

    active_company = active_company.strip()

    # Cache em request.state
    cache_key = f"_company_valid_{active_company}"
    if hasattr(request, 'state'):
        cached = getattr(request.state, cache_key, None)
        if cached is not None:
            return active_company if cached else (user.get("company") or None)

    try:
        from database import db as _db

        assoc = await _db.user_company_roles.find_one(
            {"user_id": user["id"], "company_id": active_company},
            {"_id": 0, "company_id": 1}
        )

        is_valid = assoc is not None

        if hasattr(request, 'state'):
            setattr(request.state, cache_key, is_valid)

        if is_valid:
            return active_company

    except Exception as e:
        logger.warning(
            f"[get_active_company_id_async] Erro ao validar X-Company-Id "
            f"'{active_company}' para user {user.get('id')}: {e}"
        )

    return user.get("company") or None


async def get_user_companies(user_id: str) -> list:
    """
    Retorna todas as associações user-company-role para um utilizador.

    Inclui a empresa padrão (is_default=True) e todas as outras.

    Returns:
        list[dict]: [{ company_id, company_name, role, is_default }]
    """
    from database import db as _db

    associations = await _db.user_company_roles.find(
        {"user_id": user_id},
        {"_id": 0, "id": 1, "company_id": 1, "company_name": 1, "role": 1, "is_default": 1,
         "signature": 1, "professional_phone": 1, "job_title": 1}
    ).sort("company_name", 1).to_list(50)

    return associations


def require_permission(capability: str):
    """
    Dependency do FastAPI que verifica se o utilizador tem uma capability granular.

    Algoritmo de resolução (via models.permissions.resolve_capability):
    1. Se role ∈ ["admin", "ceo"] → Super Admin Bypass → sempre True
    2. Se user.permissions.capabilities[capability] existe → usar esse valor
    3. Fallback → ROLE_CAPABILITY_DEFAULTS[role][capability]
    4. Se não existe → False (acesso negado)

    Isto permite proteger endpoints com granularidade fina:
    ``Depends(require_permission("PROCESS_DELETE"))`` em vez de verificar
    apenas o role do utilizador.

    Args:
        capability: Nome da capability (ex: "PROCESS_DELETE", "FINANCE_VIEW").

    Returns:
        Callable: Dependency function para uso com ``Depends()``.

    Raises:
        HTTPException: 403 se o utilizador não tiver a capability.
    """
    async def permission_checker(user: dict = Depends(get_current_user)):
        from models.permissions import resolve_capability as _resolve
        if not _resolve(user, capability):
            raise HTTPException(
                status_code=403,
                detail=f"Permissão negada: requer capability '{capability}'"
            )
        return user
    return permission_checker
