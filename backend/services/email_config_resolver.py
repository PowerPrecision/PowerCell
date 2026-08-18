"""
====================================================================
SERVIÇO: Email Config Resolver — Herança de Configurações
====================================================================
Resolve a configuração de email de um utilizador seguindo o caminho:

  1. User Config (email_config embedded no user)
  2. Company Config (company_email_configs — servidores padrão)
  3. System Config (system_config.email — globals)

REGRA PARA INDEXACAO:
  - Utilizadores com role='indexacao' usam SEMPRE o SharedRoleEmailConfig.
  - São ignoradas config individual e company config.
  - Se não existir SharedRoleEmailConfig para o role, retornar None.

SEGURANÇA:
  - Nunca retorna passwords nem tokens em clear-text.
  - Retorna apenas flags booleanas (has_password, has_google_oauth).
====================================================================
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from database import db
from services.encryption import encryption_service

logger = logging.getLogger(__name__)

# Roles que devem usar EXCLUSIVAMENTE a config partilhada do departamento
FORCED_SHARED_ROLES = {"indexacao", "suporte"}


def _is_nested_email_config(raw_config: Dict[str, Any]) -> bool:
    """
    Detect whether an email_config is nested (per-role) or flat (legacy).

    A config is considered nested if its top-level values include dicts,
    e.g. {"default": {...}, "consultor": {...}}.
    A flat config has scalar values like email_address, imap_server, etc.
    """
    if not raw_config:
        return False
    # If it has a known role-key that maps to a dict, it's nested
    if isinstance(raw_config.get("default"), dict):
        return True
    # If any top-level value is a dict and looks like a sub-config
    if any(isinstance(v, dict) and v.get("email_address") for v in raw_config.values()):
        return True
    return False


def _extract_role_email_config(
    raw_config: Dict[str, Any], active_role: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract the correct per-role email config from a potentially nested structure.

    - If nested: look for active_role, then fall back to "default".
    - If flat (legacy): return as-is (backward compat).

    Returns the flat config dict ready for downstream processing.
    """
    if not raw_config:
        return {}
    if not _is_nested_email_config(raw_config):
        # Flat / legacy config — return as-is
        return raw_config
    # Nested — extract role-specific, fallback to default
    if active_role and isinstance(raw_config.get(active_role), dict):
        return raw_config[active_role]
    if isinstance(raw_config.get("default"), dict):
        return raw_config["default"]
    # Fallback: return first dict value
    for v in raw_config.values():
        if isinstance(v, dict) and v.get("email_address"):
            return v
    return {}


async def resolve_email_config(
    user_id: str, active_role: Optional[str] = None,
    active_company_id: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve a configuração de email de um utilizador seguindo a herança.

    Args:
        user_id: ID do utilizador.
        active_role: Optional role key for per-role email configs.
                        If the user has a nested email_config, this selects
                        the sub-config for the given role (falls back to "default").
        active_company_id: Optional company_id para resolução de email.
                        Se fornecido, sobrepõe o campo `company` do utilizador
                        para determinar qual a config da empresa a usar.
                        Isto suporta a arquitetura multi-empresa onde um
                        utilizador pode alternar entre empresas.

    RESOLUÇÃO MULTI-EMPRESA:
        Quando active_company_id é fornecido, o resolver procura a config
        do utilizador pela seguinte ordem:
          1. Coleção user_email_configs (canónica, com índice único)
          2. user.email_config["company:<company_id>"] (embebido, backward compat)
          3. user.email_config["default"] (fallback para config genérica)
          4. Extração por role (fallback final)

    Returns:
        Dict com:
          - config_source: "user" | "company" | "system" | "shared_role" | "none"
          - email_address, imap_server, imap_port, smtp_server, smtp_port
          - has_password, has_google_oauth, auth_method
          - encrypted_password (se existir, para uso interno)
          - shared_role (se config_source == "shared_role")
          - resolved_company_id: o company_id usado na resolução
    """
    # Buscar utilizador completo (role + company + email_config)
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "role": 1, "company": 1, "email_config": 1, "additional_roles": 1}
    )

    if not user:
        return _empty_response("none")

    user_role = user.get("role", "")
    # Effective role drives FORCED_SHARED (indexacao/suporte): use the
    # active profile from the request, not only the primary JWT role.
    # Multi-profile users may have indexacao as additional_role while
    # acting as consultor (or vice-versa).
    effective_role = (active_role or user_role or "").strip().lower()
    # Se active_company_id foi fornecido, usá-lo em vez do campo `company`
    user_company = active_company_id or user.get("company", "")
    raw_email_config = user.get("email_config", {})

    # ==================================================================
    # MULTI-EMPRESA: Extração por empresa ativa
    # ==================================================================
    # Quando active_company_id é fornecido, procurar a config do user
    # para essa empresa específica, pela seguinte ordem:
    #   1. Coleção user_email_configs (fonte canónica)
    #   2. user.email_config["company:<company_id>"] (embebido)
    #   3. Fallback para role/default
    user_email_config = {}
    resolved_from_collection = False

    if active_company_id:
        # CAMINHO 0a: Coleção user_email_configs (fonte canónica)
        try:
            collection_query = {"user_id": user_id, "company_id": active_company_id}
            if account_id:
                collection_query["id"] = account_id
                collection_config = await db.user_email_configs.find_one(
                    collection_query, {"_id": 0}
                )
            else:
                collection_config = await db.user_email_configs.find_one(
                    {**collection_query, "is_primary": True, "is_configured": True},
                    {"_id": 0},
                )
                if not collection_config:
                    collection_config = await db.user_email_configs.find_one(
                        {**collection_query, "is_configured": True},
                        {"_id": 0},
                    )
            if collection_config and collection_config.get("is_configured"):
                user_email_config = collection_config
                resolved_from_collection = True
                logger.debug(
                    f"[EmailConfigResolver] Config resolvida da coleção "
                    f"user_email_configs para user={user_id} company={active_company_id}"
                    f" account={account_id or collection_config.get('id')}"
                )
        except Exception as e:
            logger.warning(
                f"[EmailConfigResolver] Erro ao consultar user_email_configs: {e}. "
                f"A tentar embebido."
            )

        # CAMINHO 0b: user.email_config["company:<company_id>"] (embebido)
        if not resolved_from_collection:
            company_key = f"company:{active_company_id}"
            if isinstance(raw_email_config.get(company_key), dict):
                user_email_config = raw_email_config[company_key]
                logger.debug(
                    f"[EmailConfigResolver] Config resolvida do embebido "
                    f"email_config[\"{company_key}\"] para user={user_id}"
                )

    # CAMINHO 0c: Fallback para extração por role ou "default"
    if not user_email_config:
        user_email_config = _extract_role_email_config(raw_email_config, active_role)

    # ==================================================================
    # REGRAS PARA ROLES COM FORÇA PARTILHADA (indexacao, suporte, etc.)
    # ==================================================================
    if effective_role in FORCED_SHARED_ROLES:
        shared_config = await _load_shared_role_config(effective_role)
        if shared_config:
            return shared_config
        # Se não tem config partilhada, retornar vazio (não fallback)
        return _empty_response("none", reason="no_shared_config_for_role")

    # ==================================================================
    # CAMINHO 1: User Config
    # ==================================================================
    if user_email_config and user_email_config.get("is_configured"):
        has_oauth = bool(user_email_config.get("google_refresh_token"))
        has_password = bool(user_email_config.get("encrypted_password"))

        # Verificar se o utilizador preencheu dados próprios de servidor
        user_imap = user_email_config.get("imap_server", "")
        user_smtp = user_email_config.get("smtp_server", "")

        if has_oauth or has_password:
            if has_oauth:
                auth_method = "google_oauth"
            else:
                auth_method = "imap_smtp"

            return {
                "config_source": "user",
                "email_address": user_email_config.get("email_address"),
                "imap_server": user_imap or None,
                "imap_port": user_email_config.get("imap_port", 993),
                "smtp_server": user_smtp or None,
                "smtp_port": user_email_config.get("smtp_port", 465),
                "has_password": has_password,
                "has_google_oauth": has_oauth,
                "auth_method": auth_method,
                "encrypted_password": user_email_config.get("encrypted_password", ""),
                "google_refresh_token": user_email_config.get("google_refresh_token"),
                "google_email": user_email_config.get("google_email"),
                "oauth_connected_at": user_email_config.get("oauth_connected_at"),
                "resolved_company_id": active_company_id or user_company,
            }

    # ==================================================================
    # CAMINHO 2: Company Config (servidores, password continuam individuais)
    # ==================================================================
    if user_company:
        company_config = await _load_company_config(user_company)
        if company_config:
            # Mesclar: servidores da empresa + credenciais do user (se houver)
            has_password = bool(user_email_config.get("encrypted_password"))
            has_oauth = bool(user_email_config.get("google_refresh_token"))

            auth_method = "none"
            if has_oauth:
                auth_method = "google_oauth"
            elif has_password:
                auth_method = "imap_smtp"

            return {
                "config_source": "company",
                "email_address": user_email_config.get("email_address"),
                "imap_server": company_config.get("imap_server"),
                "imap_port": company_config.get("imap_port", 993),
                "smtp_server": company_config.get("smtp_server"),
                "smtp_port": company_config.get("smtp_port", 465),
                "has_password": has_password,
                "has_google_oauth": has_oauth,
                "auth_method": auth_method,
                "encrypted_password": user_email_config.get("encrypted_password", ""),
                "google_refresh_token": user_email_config.get("google_refresh_token"),
                "google_email": user_email_config.get("google_email"),
                "company_name": user_company,
                "resolved_company_id": active_company_id or user_company,
            }

    # ==================================================================
    # CAMINHO 3: System Config (globals)
    # ==================================================================
    system_config = await _load_system_config()
    if system_config:
        has_password = bool(user_email_config.get("encrypted_password"))
        has_oauth = bool(user_email_config.get("google_refresh_token"))

        auth_method = "none"
        if has_oauth:
            auth_method = "google_oauth"
        elif has_password:
            auth_method = "imap_smtp"

        return {
            "config_source": "system",
            "email_address": user_email_config.get("email_address"),
            "imap_server": system_config.get("imap_server"),
            "imap_port": system_config.get("imap_port", 993),
            "smtp_server": system_config.get("smtp_server"),
            "smtp_port": system_config.get("smtp_port", 465),
            "has_password": has_password,
            "has_google_oauth": has_oauth,
            "auth_method": auth_method,
            "encrypted_password": user_email_config.get("encrypted_password", ""),
            "google_refresh_token": user_email_config.get("google_refresh_token"),
            "resolved_company_id": active_company_id or user_company,
        }

    # Nenhuma config encontrada
    return _empty_response("none", active_company_id=active_company_id)


async def resolve_email_config_for_sync(
    user_id: str, active_role: Optional[str] = None,
    active_company_id: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve config completa para sincronização/envio (inclui credenciais).

    Args:
        user_id: ID do utilizador.
        active_role: Role ativo (para nested configs).
        active_company_id: Empresa ativa (para resolução multi-empresa).

    Returns None se não for possível resolver uma config funcional.
    """
    resolved = await resolve_email_config(
        user_id, active_role=active_role,
        active_company_id=active_company_id,
        account_id=account_id,
    )
    source = resolved.get("config_source", "none")

    if source == "none":
        return None

    # Para "company" e "system", o utilizador precisa de credenciais próprias
    if source in ("company", "system"):
        if not resolved.get("has_password") and not resolved.get("has_google_oauth"):
            return None

    # Para "shared_role", as credenciais vêm do role config
    if source == "shared_role":
        if not resolved.get("has_password") and not resolved.get("has_google_oauth"):
            return None

    return resolved


# Pacote DO.3 — Diretor herda a Caixa Geral da empresa (sem password pessoal).
CAIXA_GERAL_ACCOUNT_ID = "caixa-geral"
CAIXA_GERAL_INJECT_ROLES = {"diretor"}
CAIXA_GERAL_ACCESS_ROLES = {"diretor", "admin", "ceo", "administrativo"}


def decrypt_email_secret(value: Optional[str], context: str = "") -> str:
    """Desencripta password SMTP/IMAP. Nunca devolve o blob ENC: ao SMTP.

    Se a desencriptação falhar, devolve string vazia e regista o contexto
    (host/user/purpose) sem a password em claro.
    """
    if not value:
        return ""
    if not isinstance(value, str):
        value = str(value)
    if not value.startswith(encryption_service.ENCRYPTION_PREFIX):
        return value
    try:
        decrypted = encryption_service.decrypt(value)
    except Exception as exc:
        logger.error(
            "[SMTP] Falha a desencriptar credencial (%s): %s",
            context or "unknown", type(exc).__name__,
        )
        return ""
    if isinstance(decrypted, str) and decrypted.startswith(encryption_service.ENCRYPTION_PREFIX):
        logger.error(
            "[SMTP] Credencial permanece encriptada após decrypt (%s). "
            "ENCRYPTION_KEY provavelmente diferente da usada a gravar.",
            context or "unknown",
        )
        return ""
    return decrypted or ""


async def resolve_active_ucr_role(
    request: Any,
    current_user: Dict[str, Any],
    company_id: Optional[str] = None,
) -> str:
    """Role activo do UCR da empresa, com fallback para X-Active-Role / JWT."""
    from services.auth import get_effective_role

    effective = (get_effective_role(request, current_user) or "").strip().lower()
    cid = (company_id or "").strip()
    user_id = current_user.get("id")
    if not user_id or not cid or cid == "default":
        return effective
    try:
        ucr = await db.user_company_roles.find_one(
            {"user_id": user_id, "company_id": cid},
            {"_id": 0, "role": 1},
        )
        ucr_role = str((ucr or {}).get("role") or "").strip().lower()
        if ucr_role:
            return ucr_role
    except Exception as exc:
        logger.warning(
            "[EmailConfig] Falha a ler UCR role user=%s company=%s: %s",
            user_id, cid, exc,
        )
    return effective


def publicize_caixa_geral_account(
    config: Dict[str, Any],
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Serializa a Caixa Geral sem secrets, para GET /users/me/email-accounts."""
    email_address = (config.get("email_address") or "").strip()
    return {
        "id": CAIXA_GERAL_ACCOUNT_ID,
        "company_id": company_id or config.get("company_id") or "default",
        "email_address": email_address,
        "label": config.get("label") or "Caixa Geral",
        "imap_server": config.get("imap_server") or "",
        "imap_port": int(config.get("imap_port") or 993),
        "smtp_server": config.get("smtp_server") or "",
        "smtp_port": int(config.get("smtp_port") or 465),
        "is_configured": True,
        "is_primary": False,
        "has_password": bool(config.get("password") or config.get("has_password")),
        "has_google_oauth": bool(config.get("google_refresh_token")),
        "auth_method": "imap_smtp",
        "is_caixa_geral": True,
        "is_shared": True,
        "managed_centralized": True,
        "read_only": True,
    }


async def load_caixa_geral_config(
    company_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Credenciais da Caixa Geral (system_config.email da empresa, depois contas globais).

    Inclui ``password`` já desencriptada para SMTP/IMAP interno.
    """
    from services.system_config import get_system_config

    candidates = []
    cid = (company_id or "").strip()
    if cid and cid != "default":
        candidates.append(cid)
    candidates.append("default")

    for cfg_id in candidates:
        try:
            sys_cfg = await get_system_config(cfg_id)
            email_cfg = sys_cfg.email
            user = (email_cfg.imap_user or email_cfg.smtp_user or "").strip()
            raw_pw = email_cfg.imap_password or email_cfg.smtp_password or ""
            password = decrypt_email_secret(
                raw_pw, f"caixa_geral system_config company={cfg_id} user={user}",
            )
            smtp_server = email_cfg.smtp_server or email_cfg.imap_server
            imap_server = email_cfg.imap_server or email_cfg.smtp_server
            if user and password and smtp_server:
                return {
                    "email_address": user,
                    "imap_server": imap_server,
                    "imap_port": int(email_cfg.imap_port or 993),
                    "smtp_server": smtp_server,
                    "smtp_port": int(email_cfg.smtp_port or 465),
                    "password": password,
                    "has_password": True,
                    "company_id": cfg_id,
                    "source": f"system_config:{cfg_id}",
                    "label": "Caixa Geral",
                }
        except Exception as exc:
            logger.warning(
                "[CaixaGeral] Falha a ler system_config company=%s: %s",
                cfg_id, exc,
            )

    try:
        from services.email_service import get_email_accounts_async
        accounts = await get_email_accounts_async()
        if accounts:
            account = accounts[0]
            password = decrypt_email_secret(
                account.password,
                f"caixa_geral global account={account.name} user={account.email}",
            )
            if account.email and password and account.smtp_server:
                return {
                    "email_address": account.email,
                    "imap_server": account.imap_server,
                    "imap_port": int(account.imap_port or 993),
                    "smtp_server": account.smtp_server,
                    "smtp_port": int(account.smtp_port or 465),
                    "password": password,
                    "has_password": True,
                    "company_id": cid or "default",
                    "source": f"global:{account.name}",
                    "label": "Caixa Geral",
                }
    except Exception as exc:
        logger.warning("[CaixaGeral] Falha no fallback de contas globais: %s", exc)

    return None


def _empty_response(source: str, reason: str = "", active_company_id: Optional[str] = None) -> Dict[str, Any]:
    """Retorna resposta vazia com config_source indicado."""
    resp = {
        "config_source": source,
        "email_address": None,
        "imap_server": None,
        "imap_port": None,
        "smtp_server": None,
        "smtp_port": None,
        "has_password": False,
        "has_google_oauth": False,
        "auth_method": "none",
        "encrypted_password": "",
        "resolved_company_id": active_company_id,
    }
    if reason:
        resp["reason"] = reason
    return resp


async def _load_shared_role_config(role: str) -> Optional[Dict[str, Any]]:
    """
    Carrega a config partilhada do role (SharedRoleEmailConfig).

    Returns dict com config resolvida, ou None se não existir.
    """
    config = await db.shared_role_email_configs.find_one(
        {"role": role},
        {"_id": 0}
    )

    if not config:
        return None

    has_oauth = bool(config.get("google_refresh_token"))
    has_password = bool(config.get("encrypted_password"))

    if has_oauth:
        auth_method = "google_oauth"
    elif has_password:
        auth_method = "imap_smtp"
    else:
        return None  # Config existe mas sem credenciais

    return {
        "config_source": "shared_role",
        "shared_role": role,
        "email_address": config.get("email_address"),
        "imap_server": config.get("imap_server"),
        "imap_port": config.get("imap_port", 993),
        "smtp_server": config.get("smtp_server"),
        "smtp_port": config.get("smtp_port", 465),
        "has_password": has_password,
        "has_google_oauth": has_oauth,
        "auth_method": auth_method,
        "encrypted_password": config.get("encrypted_password", ""),
        "google_refresh_token": config.get("google_refresh_token"),
        "google_email": config.get("google_email"),
        "display_name": config.get("display_name"),
    }


async def _load_company_config(company_name: str) -> Optional[Dict[str, Any]]:
    """
    Carrega a config de servidores padrão de uma empresa.

    Returns dict com imap_server/smtp_server/etc, ou None se não existir.
    """
    config = await db.company_email_configs.find_one(
        {"company_name": company_name},
        {"_id": 0}
    )

    if not config:
        return None

    if not config.get("imap_server") and not config.get("smtp_server"):
        return None  # Config existe mas sem servidores definidos

    return {
        "imap_server": config.get("imap_server"),
        "imap_port": config.get("imap_port", 993),
        "smtp_server": config.get("smtp_server"),
        "smtp_port": config.get("smtp_port", 465),
        "company_name": company_name,
    }


async def _load_system_config() -> Optional[Dict[str, Any]]:
    """
    Carrega a config de email do sistema (system_config.email).

    Retorna apenas os campos de servidor (Account 1).
    """
    try:
        config = await db.system_config.find_one(
            {"_id": "main"},
            {"_id": 0, "email": 1}
        )

        if not config or not config.get("email"):
            return None

        email_config = config["email"]
        imap_server = email_config.get("imap_server")
        smtp_server = email_config.get("smtp_server")

        if not imap_server and not smtp_server:
            return None

        return {
            "imap_server": imap_server,
            "imap_port": int(email_config.get("imap_port", 993)),
            "smtp_server": smtp_server,
            "smtp_port": int(email_config.get("smtp_port", 465)),
        }
    except Exception as e:
        logger.warning(f"[EmailConfigResolver] Erro ao carregar system_config: {e}")
        return None
