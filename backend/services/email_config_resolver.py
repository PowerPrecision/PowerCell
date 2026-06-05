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
    active_company_id: Optional[str] = None
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

    Returns:
        Dict com:
          - config_source: "user" | "company" | "system" | "shared_role" | "none"
          - email_address, imap_server, imap_port, smtp_server, smtp_port
          - has_password, has_google_oauth, auth_method
          - encrypted_password (se existir, para uso interno)
          - shared_role (se config_source == "shared_role")
    """
    # Buscar utilizador completo (role + company + email_config)
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "role": 1, "company": 1, "email_config": 1, "additional_roles": 1}
    )

    if not user:
        return _empty_response("none")

    user_role = user.get("role", "")
    # Se active_company_id foi fornecido, usá-lo em vez do campo `company`
    user_company = active_company_id or user.get("company", "")
    raw_email_config = user.get("email_config", {})

    # Normalize: extract per-role config if nested, or use flat (legacy)
    user_email_config = _extract_role_email_config(raw_email_config, active_role)

    # ==================================================================
    # REGRAS PARA ROLES COM FORÇA PARTILHADA (indexacao, suporte, etc.)
    # ==================================================================
    if user_role in FORCED_SHARED_ROLES:
        shared_config = await _load_shared_role_config(user_role)
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
        }

    # Nenhuma config encontrada
    return _empty_response("none")


async def resolve_email_config_for_sync(
    user_id: str, active_role: Optional[str] = None,
    active_company_id: Optional[str] = None
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
        active_company_id=active_company_id
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


def _empty_response(source: str, reason: str = "") -> Dict[str, Any]:
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
