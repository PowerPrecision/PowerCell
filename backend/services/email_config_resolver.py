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
from services.shared_mailbox_scope import config_do_utilizador
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
    raw_config: Dict[str, Any], active_role: Optional[str] = None,
    sem_chaves_de_empresa: bool = False,
) -> Dict[str, Any]:
    """
    Extract the correct per-role email config from a potentially nested structure.

    - If nested: look for active_role, then fall back to "default".
    - If flat (legacy): return as-is (backward compat).

    ``sem_chaves_de_empresa``: quando o chamador já procurou a config da empresa pedida
    (``company:<id>``) e não a encontrou, o último recurso («o primeiro dict com email»)
    não pode devolver a ``company:<outra>`` — era a conta da Power a aparecer na Precision.

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
    for chave, v in raw_config.items():
        if sem_chaves_de_empresa and str(chave).startswith("company:"):
            continue
        if isinstance(v, dict) and v.get("email_address"):
            return v
    return {}


async def _recurso_e_de_outra_empresa(user: Dict[str, Any], user_id: str, empresa_pedida: str) -> bool:
    """A config genérica («default»/por cargo) do utilizador pertence a OUTRA empresa?

    A config sem chave de empresa vem do tempo em que cada utilizador tinha uma só. Para
    quem tem acesso a várias empresas (o Master), ela é a da empresa de origem dele
    (`users.company`): usá-la para a Precision era enviar com as credenciais da Power e
    mostrar a conta da Power no cartão da Precision. Quem tem uma só empresa mantém o recurso.
    """
    try:
        ucrs = await db.user_company_roles.find(
            {"user_id": user_id, "is_deleted": {"$ne": True}, "is_active": {"$ne": False}},
            {"_id": 0, "company_id": 1},
        ).to_list(100)
        empresas = {u.get("company_id") for u in ucrs if u.get("company_id")}
        if len(empresas) < 2:
            return False
        casa = str(user.get("company") or "").strip().lower()
        if not casa:
            return True
        if casa == str(empresa_pedida).strip().lower():
            return False
        empresa = await db.companies.find_one({"id": empresa_pedida}, {"_id": 0, "name": 1})
        nome = str((empresa or {}).get("name") or "").strip().lower()
        return not (nome and nome == casa)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[EmailConfigResolver] Falha a decidir o recurso genérico: %s", exc)
        return False


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

    # CAMINHO 0c: Fallback para extração por role ou "default" — mas NUNCA com a config
    # de outra empresa quando foi pedida uma empresa concreta.
    if not user_email_config:
        empresa_concreta = bool(active_company_id) and str(active_company_id).strip().lower() != "default"
        if empresa_concreta and await _recurso_e_de_outra_empresa(user, user_id, active_company_id):
            user_email_config = {}
        else:
            user_email_config = _extract_role_email_config(
                raw_email_config, active_role, sem_chaves_de_empresa=empresa_concreta,
            )

    # ==================================================================
    # REGRAS PARA ROLES COM FORÇA PARTILHADA (indexacao, suporte, etc.)
    # ==================================================================
    if effective_role in FORCED_SHARED_ROLES:
        shared_config = await _load_shared_role_config(
            effective_role,
            {"id": user_id, "role": user_role, "company": user.get("company")},
        )
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
    # Isolamento estrito: os servidores globais são da rede de omissão. Uma empresa
    # de outra rede não os herda — sem servidores próprios a configuração fica por
    # fazer (o utilizador indica-os), nunca preenchida com os da empresa-mãe.
    from services.webmail_heranca import pode_herdar_configuracao_global

    herda_a_global = await pode_herdar_configuracao_global(
        active_company_id or user_company,
        user={"id": user_id, "role": user_role, "company": user.get("company")},
    )
    system_config = await _load_system_config() if herda_a_global else None
    if not herda_a_global:
        logger.debug(
            "[EmailConfigResolver] user=%s company=%s: rede satélite, sem herança da config global.",
            user_id, active_company_id or user_company,
        )
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


# Pacote DO.3 / DV — Caixa Geral só para quem tem um destes cargos, e apenas
# quando existe um email real (ex.: geral@empresa.pt).
#
# BLOCO 2 (Lote 12): o Administrativo também. O back-office é quem trata o
# correio geral da empresa, e deixá-lo de fora fazia a Caixa Geral
# desaparecer-lhe da lista de contas sem erro nenhum.
#
# UM conjunto só. Eram três cópias (`INJECT`, `ACCESS` e dois literais
# `{"admin","ceo","diretor"}` no `email_webmail`) e a que ficava para trás
# esconderia a caixa a um cargo sem dar erro. Os dois nomes antigos ficam
# como alias, porque o resto do código importa-os.
CAIXA_GERAL_ACCOUNT_ID = "caixa-geral"
CAIXA_GERAL_ROLES = frozenset({"diretor", "ceo", "master", "admin", "administrativo"})
CAIXA_GERAL_INJECT_ROLES = CAIXA_GERAL_ROLES
CAIXA_GERAL_ACCESS_ROLES = CAIXA_GERAL_ROLES


def pode_abrir_caixa_geral(effective_role, ucr_roles=()) -> bool:
    """O perfil activo — ou qualquer cargo UCR válido — tem direito à Caixa Geral?

    Registo POSITIVO: o que estava antes era «qualquer cargo menos três»,
    que deixava passar um parceiro ou um cliente e dependia de se lembrar
    de cada cargo novo.
    """
    activo = str(effective_role or "").strip().lower()
    if activo in CAIXA_GERAL_ROLES:
        return True
    return bool({str(r or "").strip().lower() for r in (ucr_roles or ())} & CAIXA_GERAL_ROLES)


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
    *,
    user: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Credenciais da Caixa Geral (system_config.email da empresa, depois contas globais).

    Inclui ``password`` já desencriptada para SMTP/IMAP interno.

    ISOLAMENTO ESTRITO (``services/webmail_heranca.py``): a configuração global
    — o recurso ``default`` e as contas de ambiente — é da rede de omissão. Uma
    empresa de OUTRA rede só tem Caixa Geral se a configurou ela (lida sem criar
    a cópia que o ``get_system_config`` grava por herança, e sem aceitar essa
    cópia); sem caixa própria devolve ``None`` e o ecrã fica vazio. ``user``
    serve para recusar uma empresa fora do âmbito de rede de quem pergunta e
    para decidir o sentinel ``default``.
    """
    from services.system_config import get_system_config
    from services.webmail_heranca import (
        e_copia_da_global,
        email_do_documento,
        empresa_no_ambito_do_utilizador,
        pode_herdar_configuracao_global,
    )

    cid = (company_id or "").strip()
    if not await empresa_no_ambito_do_utilizador(cid, user):
        logger.warning(
            "[CaixaGeral] Empresa %s fora do âmbito de rede do utilizador %s: sem Caixa Geral.",
            cid, (user or {}).get("id"),
        )
        return None

    herda_a_global = await pode_herdar_configuracao_global(cid, user=user)
    if not herda_a_global:
        # Rede satélite: só a configuração PRÓPRIA da empresa. Nunca `default`,
        # nunca contas de ambiente, nunca a cópia da global.
        if not cid or cid == "default":
            return None
        if not await email_do_documento(f"company:{cid}") or await e_copia_da_global(cid):
            return None

    candidates = []
    if cid and cid != "default":
        candidates.append(cid)
    if herda_a_global:
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

    if not herda_a_global:
        return None

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


async def _load_shared_role_config(role: str, user: dict) -> Optional[Dict[str, Any]]:
    """
    Carrega a config partilhada do role (SharedRoleEmailConfig) **da rede do utilizador**.

    D-8: a caixa é de (cargo, rede). Sem o utilizador, a config de uma rede
    (com o refresh token do Google dela) saía para quem tivesse o cargo
    noutra rede.

    Returns dict com config resolvida, ou None se não existir.
    """
    config = await config_do_utilizador(role, user)

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


# ====================================================================
# CONTA DE ENVIO — ponto ÚNICO de resolução
# ====================================================================


async def resolve_sending_account(
    request: Any,
    current_user: Dict[str, Any],
    active_company_id: Optional[str] = None,
) -> tuple:
    """Resolve a conta SMTP que um envio deste utilizador vai mesmo usar.

    PORQUÊ AQUI E NÃO EM CADA CHAMADOR: o incidente de 2026-09-21 nasceu de
    dois caminhos resolverem a configuração de email de maneiras diferentes
    — o botão "Testar" dava verde numa sub-configuração e o envio usava
    outra. Duplicar esta lógica é o que permite essa divergência, por isso
    ela vive num sítio só e todos a chamam.

    Ordem (a mesma do envio de documentação):
      1. Configuração do perfil activo (`resolve_email_config_for_sync`
         com o papel do UCR).
      2. Caixa Geral da empresa.
      3. Nenhuma — cabe ao chamador decidir o erro a devolver.

    Returns:
        ``(EmailAccount | None, source)`` — ``source`` identifica a origem
        (``"profile:<config_source>"``, ``"caixa_geral"``, ``"none"``) e é
        o que torna um envio falhado diagnosticável sem ler logs.
    """
    # Import tardio: `email_service` importa deste módulo.
    from services.email_service import EmailAccount

    account = None
    source = "none"
    motivo_do_recurso: Optional[str] = None

    try:
        ucr_role = (
            await resolve_active_ucr_role(request, current_user, active_company_id)
            if request is not None
            else current_user.get("role", "")
        )
        resolved = await resolve_email_config_for_sync(
            current_user["id"],
            active_role=ucr_role,
            active_company_id=active_company_id,
        )
        if resolved:
            password = decrypt_email_secret(
                resolved.get("encrypted_password", ""),
                (
                    f"sending-account user={current_user.get('id')} "
                    f"email={resolved.get('email_address')} "
                    f"source={resolved.get('config_source')}"
                ),
            )
            host = resolved.get("smtp_server") or resolved.get("imap_server")
            user_email = resolved.get("email_address")
            if not password:
                motivo_do_recurso = "password do perfil ilegível ou vazia"
            elif not (user_email and host):
                motivo_do_recurso = "configuração do perfil incompleta (email ou servidor em falta)"
            if user_email and host and password:
                account = EmailAccount(
                    name="personal",
                    imap_server=resolved.get("imap_server") or host,
                    imap_port=int(resolved.get("imap_port") or 993),
                    smtp_server=host,
                    smtp_port=int(resolved.get("smtp_port") or 465),
                    email=user_email,
                    password=password,
                )
                source = f"profile:{resolved.get('config_source')}"
    except Exception as exc:
        logger.warning(
            "[SendingAccount] Falha a resolver SMTP do perfil user=%s: %s: %s",
            current_user.get("id"), type(exc).__name__, exc,
        )

    if account is None:
        try:
            caixa = await load_caixa_geral_config(active_company_id, user=current_user)
            if (
                caixa
                and caixa.get("password")
                and caixa.get("smtp_server")
                and caixa.get("email_address")
            ):
                account = EmailAccount(
                    name="caixa_geral",
                    imap_server=caixa.get("imap_server") or caixa["smtp_server"],
                    imap_port=int(caixa.get("imap_port") or 993),
                    smtp_server=caixa["smtp_server"],
                    smtp_port=int(caixa.get("smtp_port") or 465),
                    email=caixa["email_address"],
                    password=caixa["password"],
                )
                source = caixa.get("source") or "caixa_geral"
                if motivo_do_recurso:
                    # O perfil EXISTE mas não é utilizável: o envio sai pela
                    # Caixa Geral e, se esta recusar as credenciais, o erro
                    # parece ser da conta do consultor. Fica dito no log.
                    logger.warning(
                        "[SendingAccount] user=%s: a usar a Caixa Geral (%s) porque o "
                        "perfil não é utilizável: %s.",
                        current_user.get("id"), source, motivo_do_recurso,
                    )
        except Exception as exc:
            logger.warning(
                "[SendingAccount] Falha a resolver Caixa Geral company=%s: %s: %s",
                active_company_id, type(exc).__name__, exc,
            )

    return account, source
