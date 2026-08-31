"""
====================================================================
SERVIÇO: User Email Config Service — CRUD + Migração
====================================================================
Gere a coleção user_email_configs, a fonte canónica de configurações
de email pessoal por utilizador e empresa.

COLEÇÃO: user_email_configs
INDEX ÚNICO: (user_id, company_id, email_address) — várias contas por perfil (DN.4)
is_primary: conta por omissão do UCR (dual-write para user.email_config embebido)

DUAL-WRITE:
  Sempre que se guarda uma config, escreve-se na coleção AND no
  user.email_config embebido (backward compat). A leitura preferencial
  é da coleção (ver email_config_resolver.py).

MIGRAÇÃO:
  O endpoint POST /admin/user-email-configs/migrate popula a coleção
  a partir das configs embebidas nos documentos dos utilizadores.
====================================================================
"""

import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from database import db
from services.encryption import encryption_service

logger = logging.getLogger(__name__)


async def get_user_email_config(
    user_id: str,
    company_id: str,
    account_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Obtém a config de email de um utilizador para uma empresa.

    Se ``account_id`` for dado, devolve essa conta. Caso contrário
    prefere ``is_primary=True`` e cai na primeira config da empresa.
    """
    if account_id:
        return await db.user_email_configs.find_one(
            {"id": account_id, "user_id": user_id},
            {"_id": 0},
        )
    primary = await db.user_email_configs.find_one(
        {"user_id": user_id, "company_id": company_id, "is_primary": True},
        {"_id": 0},
    )
    if primary:
        return primary
    return await db.user_email_configs.find_one(
        {"user_id": user_id, "company_id": company_id},
        {"_id": 0},
    )


async def list_company_email_configs(
    user_id: str,
    company_id: str,
) -> List[Dict[str, Any]]:
    """Lista todas as contas de email de um utilizador para uma empresa."""
    cursor = db.user_email_configs.find(
        {"user_id": user_id, "company_id": company_id},
        {"_id": 0},
    ).sort([("is_primary", -1), ("created_at", 1)])
    return await cursor.to_list(50)


def publicize_email_account(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Serializa uma config sem secrets (password / refresh token)."""
    if not doc:
        return {}
    has_oauth = bool(doc.get("google_refresh_token"))
    has_password = bool(doc.get("encrypted_password"))
    auth_method = doc.get("auth_method") or "none"
    if has_oauth:
        auth_method = "google_oauth"
    elif has_password and auth_method == "none":
        auth_method = "imap_smtp"
    email_address = doc.get("email_address") or ""
    return {
        "id": doc.get("id"),
        "company_id": doc.get("company_id") or "default",
        "email_address": email_address,
        "label": doc.get("label") or email_address,
        "imap_server": doc.get("imap_server") or "",
        "imap_port": doc.get("imap_port") or 993,
        "smtp_server": doc.get("smtp_server") or "",
        "smtp_port": doc.get("smtp_port") or 465,
        "is_configured": bool(doc.get("is_configured")),
        "is_primary": bool(doc.get("is_primary")),
        "has_password": has_password,
        "has_google_oauth": has_oauth,
        "auth_method": auth_method,
        "google_email": doc.get("google_email"),
        "oauth_connected_at": doc.get("oauth_connected_at"),
    }


async def get_all_user_email_configs(user_id: str) -> List[Dict[str, Any]]:
    """
    Lista todas as configs de email de um utilizador (uma por empresa).

    Returns:
        Lista de dicts com as configs.
    """
    cursor = db.user_email_configs.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("company_id", 1)
    return await cursor.to_list(50)


async def get_user_companies_with_config(user_id: str) -> List[str]:
    """
    Retorna os company_ids para os quais o utilizador tem config.

    Returns:
        Lista de company_id strings.
    """
    cursor = db.user_email_configs.find(
        {"user_id": user_id, "is_configured": True},
        {"_id": 0, "company_id": 1}
    )
    docs = await cursor.to_list(50)
    return [doc["company_id"] for doc in docs]


async def get_active_email_configs_for_sync(
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Retorna todas as configs de email pessoais ativas para sincronização
    automática em background (multi-empresa).

    SUBSTITUI a query legacy ``db.users.find({"email_config.is_configured": True})``
    que só funcionava para configs flat embebidas em ``user.email_config``. Esta
    função consulta a coleção canónica ``user_email_configs`` (uma config por
    par user+empresa) e devolve apenas configs com credenciais válidas cujo
    utilizador esteja ativo.

    Filtros aplicados:
      - ``is_configured: True`` — a flag de ativação da config
      - Credenciais presentes: ``encrypted_password`` (IMAP/SMTP) OU
        ``google_refresh_token`` (Google OAuth)
      - Utilizador ativo (``users.is_active`` != False)

    Returns:
        Lista de dicts (um por par user+empresa ativo), cada um com:
          - ``user_id``: ID do utilizador
          - ``company_id``: ID/nome da empresa ativa
          - ``email_address``: endereço de email configurado
          - ``auth_method``: "imap_smtp" | "google_oauth" | "none"
          - ``user_email``: email de login do utilizador (para logging)
    """
    # 1. Buscar configs ativas com credenciais (IMAP/SMTP OU Google OAuth)
    cursor = db.user_email_configs.find(
        {
            "is_configured": True,
            "$or": [
                {"encrypted_password": {"$nin": ["", None], "$exists": True}},
                {"google_refresh_token": {"$nin": ["", None], "$exists": True}},
            ],
        },
        {
            "_id": 0,
            "user_id": 1,
            "company_id": 1,
            "email_address": 1,
            "auth_method": 1,
            "id": 1,
        }
    )
    configs = await cursor.to_list(limit)

    if not configs:
        return []

    # 2. Filtrar utilizadores ativos (batch query — 1 round-trip)
    user_ids = list({c["user_id"] for c in configs if c.get("user_id")})
    active_cursor = db.users.find(
        {"id": {"$in": user_ids}, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "email": 1}
    )
    active_users = {u["id"]: u for u in await active_cursor.to_list(len(user_ids))}

    # 3. Combinar: só incluir configs cujo user está ativo
    result = []
    for c in configs:
        uid = c.get("user_id")
        if not uid or uid not in active_users:
            continue
        result.append({
            "user_id": uid,
            "company_id": c.get("company_id") or "default",
            "email_address": c.get("email_address", ""),
            "auth_method": c.get("auth_method", "imap_smtp"),
            "user_email": active_users[uid].get("email", ""),
            "id": c.get("id"),
        })
    return result


async def _count_company_accounts(user_id: str, company_id: str) -> int:
    return await db.user_email_configs.count_documents(
        {"user_id": user_id, "company_id": company_id}
    )


async def upsert_user_email_config(
    user_id: str,
    company_id: str,
    email_address: str,
    imap_server: str = "",
    imap_port: int = 993,
    smtp_server: str = "",
    smtp_port: int = 465,
    encrypted_password: str = "",
    google_refresh_token: Optional[str] = None,
    google_access_token: Optional[str] = None,
    google_email: Optional[str] = None,
    auth_method: str = "none",
    oauth_connected_at: Optional[str] = None,
    is_configured: bool = True,
    config_id: Optional[str] = None,
    create_new: bool = False,
    label: Optional[str] = None,
    is_primary: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Cria ou atualiza uma conta de email do utilizador para uma empresa.

    Unicidade: (user_id, company_id, email_address).
    ``create_new=True`` insere uma conta extra (Pacote DN.4).
    Sem ``create_new``, actualiza a conta ``config_id``, a do mesmo
    ``email_address``, ou a primária do perfil (legado).
    """
    now = datetime.now(timezone.utc).isoformat()
    clean_email = (email_address or "").strip().lower()
    existing = None

    if config_id:
        existing = await db.user_email_configs.find_one(
            {"id": config_id, "user_id": user_id},
            {"_id": 0},
        )
    if existing is None and clean_email:
        existing = await db.user_email_configs.find_one(
            {
                "user_id": user_id,
                "company_id": company_id,
                "email_address": clean_email,
            },
            {"_id": 0},
        )
    if existing is None and not create_new:
        existing = await get_user_email_config(user_id, company_id)

    sibling_count = await _count_company_accounts(user_id, company_id)
    make_primary = is_primary
    if make_primary is None:
        make_primary = sibling_count == 0 or (
            bool(existing.get("is_primary")) if existing else sibling_count == 0
        )

    if existing:
        filter_q = {"id": existing["id"], "user_id": user_id}
        update_data = {
            "email_address": clean_email,
            "imap_server": imap_server.strip(),
            "imap_port": imap_port,
            "smtp_server": smtp_server.strip(),
            "smtp_port": smtp_port,
            "is_configured": is_configured,
            "updated_at": now,
            "company_id": company_id,
        }
        if encrypted_password:
            update_data["encrypted_password"] = encrypted_password
        if google_refresh_token is not None:
            update_data["google_refresh_token"] = google_refresh_token
        if google_access_token is not None:
            update_data["google_access_token"] = google_access_token
        if google_email is not None:
            update_data["google_email"] = google_email
        if auth_method != "none":
            update_data["auth_method"] = auth_method
        if oauth_connected_at is not None:
            update_data["oauth_connected_at"] = oauth_connected_at
        if label is not None:
            update_data["label"] = label
        if make_primary:
            update_data["is_primary"] = True

        await db.user_email_configs.update_one(filter_q, {"$set": update_data})
        updated = await db.user_email_configs.find_one(filter_q, {"_id": 0})
        if make_primary:
            await _ensure_single_primary(user_id, company_id, updated.get("id"))
            await _sync_to_embedded(user_id, company_id, updated or update_data)
        elif updated and updated.get("is_primary"):
            await _sync_to_embedded(user_id, company_id, updated)
        return updated or update_data

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "company_id": company_id,
        "email_address": clean_email,
        "imap_server": imap_server.strip(),
        "imap_port": imap_port,
        "smtp_server": smtp_server.strip(),
        "smtp_port": smtp_port,
        "encrypted_password": encrypted_password,
        "google_refresh_token": google_refresh_token,
        "google_access_token": google_access_token,
        "google_email": google_email,
        "auth_method": auth_method,
        "oauth_connected_at": oauth_connected_at,
        "is_configured": is_configured,
        "is_primary": bool(make_primary) or sibling_count == 0,
        "label": label or clean_email,
        "created_at": now,
        "updated_at": now,
    }

    try:
        await db.user_email_configs.insert_one(doc)
    except Exception as e:
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            logger.warning(
                f"[UserEmailConfig] Duplicate key on insert for user={user_id} "
                f"company={company_id} email={clean_email}. A fazer upsert."
            )
            await db.user_email_configs.update_one(
                {
                    "user_id": user_id,
                    "company_id": company_id,
                    "email_address": clean_email,
                },
                {"$set": {k: v for k, v in doc.items() if k not in ("id", "created_at")}},
            )
            doc = await db.user_email_configs.find_one(
                {
                    "user_id": user_id,
                    "company_id": company_id,
                    "email_address": clean_email,
                },
                {"_id": 0},
            )
        else:
            raise

    if doc.get("is_primary"):
        await _ensure_single_primary(user_id, company_id, doc.get("id"))
        await _sync_to_embedded(user_id, company_id, doc)
    return doc


async def _ensure_single_primary(user_id: str, company_id: str, primary_id: Optional[str]):
    """Garante no máximo uma conta primária por (user, empresa)."""
    if not primary_id:
        return
    await db.user_email_configs.update_many(
        {
            "user_id": user_id,
            "company_id": company_id,
            "id": {"$ne": primary_id},
        },
        {"$set": {"is_primary": False}},
    )
    await db.user_email_configs.update_one(
        {"id": primary_id, "user_id": user_id},
        {"$set": {"is_primary": True}},
    )


async def set_primary_email_config(
    user_id: str,
    company_id: str,
    account_id: str,
) -> Optional[Dict[str, Any]]:
    """Marca uma conta como primária do perfil/empresa."""
    doc = await db.user_email_configs.find_one(
        {"id": account_id, "user_id": user_id, "company_id": company_id},
        {"_id": 0},
    )
    if not doc:
        return None
    await _ensure_single_primary(user_id, company_id, account_id)
    updated = await db.user_email_configs.find_one({"id": account_id}, {"_id": 0})
    if updated:
        await _sync_to_embedded(user_id, company_id, updated)
    return updated


async def update_oauth_tokens(
    user_id: str,
    company_id: str,
    google_refresh_token: str,
    google_access_token: Optional[str] = None,
    google_email: Optional[str] = None,
    auth_method: str = "google_oauth",
    oauth_connected_at: Optional[str] = None,
) -> bool:
    """
    Atualiza apenas os tokens OAuth na config do utilizador para uma empresa.
    Usado pelo callback do Google OAuth.

    Returns:
        True se atualizou, False se não encontrou a config.
    """
    now = datetime.now(timezone.utc).isoformat()

    update_data = {
        "google_refresh_token": google_refresh_token,
        "auth_method": auth_method,
        "updated_at": now,
        "is_configured": True,
    }
    if google_access_token is not None:
        update_data["google_access_token"] = google_access_token
    if google_email is not None:
        update_data["google_email"] = google_email
    if oauth_connected_at is not None:
        update_data["oauth_connected_at"] = oauth_connected_at

    result = await db.user_email_configs.update_one(
        {"user_id": user_id, "company_id": company_id},
        {"$set": update_data}
    )

    if result.modified_count > 0 or result.matched_count > 0:
        # Dual-write: atualizar embebido também
        updated_doc = await db.user_email_configs.find_one(
            {"user_id": user_id, "company_id": company_id},
            {"_id": 0}
        )
        if updated_doc:
            await _sync_to_embedded(user_id, company_id, updated_doc)
        return True

    return False


async def disconnect_oauth(user_id: str, company_id: str) -> bool:
    """
    Remove os tokens OAuth da config de email.
    """
    now = datetime.now(timezone.utc).isoformat()

    result = await db.user_email_configs.update_one(
        {"user_id": user_id, "company_id": company_id},
        {"$set": {
            "google_refresh_token": None,
            "google_access_token": None,
            "google_email": None,
            "auth_method": "none",
            "oauth_connected_at": None,
            "updated_at": now,
        }}
    )

    if result.modified_count > 0 or result.matched_count > 0:
        # Dual-write
        updated_doc = await db.user_email_configs.find_one(
            {"user_id": user_id, "company_id": company_id},
            {"_id": 0}
        )
        if updated_doc:
            await _sync_to_embedded(user_id, company_id, updated_doc)
        return True

    return False


async def delete_user_email_config(
    user_id: str,
    company_id: str,
    account_id: Optional[str] = None,
) -> bool:
    """
    Remove uma conta de email (ou todas as da empresa se account_id for None).
    Se apagar a primária, promove a conta mais antiga restante.
    """
    if account_id:
        doomed = await db.user_email_configs.find_one(
            {"id": account_id, "user_id": user_id},
            {"_id": 0, "id": 1, "is_primary": 1, "company_id": 1},
        )
        if not doomed:
            return False
        company_id = doomed.get("company_id") or company_id
        was_primary = bool(doomed.get("is_primary"))
        result = await db.user_email_configs.delete_one(
            {"id": account_id, "user_id": user_id}
        )
        if result.deleted_count == 0:
            return False
        remaining = await list_company_email_configs(user_id, company_id)
        if was_primary and remaining:
            await set_primary_email_config(user_id, company_id, remaining[0]["id"])
        elif not remaining:
            company_key = f"company:{company_id}"
            await db.users.update_one(
                {"id": user_id},
                {"$unset": {f"email_config.{company_key}": ""}},
            )
        return True

    result = await db.user_email_configs.delete_many(
        {"user_id": user_id, "company_id": company_id}
    )
    if result.deleted_count > 0:
        company_key = f"company:{company_id}"
        await db.users.update_one(
            {"id": user_id},
            {"$unset": {f"email_config.{company_key}": ""}},
        )
    return result.deleted_count > 0


async def migrate_embedded_to_collection() -> Dict[str, int]:
    """
    Migração: move as configs de email embebidas nos documentos dos
    utilizadores para a coleção user_email_configs.

    Para cada sub-config em user.email_config (chaves como "default",
    "company:Power Real Estate", etc.), cria um documento na coleção
    com (user_id, company_id) único.

    Returns:
        Dict com contadores: {created, skipped, errors, total_users}
    """
    from services.email_config_resolver import _is_nested_email_config

    users = await db.users.find(
        {"email_config": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "id": 1, "company": 1, "email_config": 1}
    ).to_list(500)

    created = 0
    skipped = 0
    errors = 0
    now = datetime.now(timezone.utc).isoformat()

    for user in users:
        user_id = user["id"]
        raw_config = user.get("email_config", {})
        fallback_company = user.get("company", "default")

        if not raw_config:
            continue

        if _is_nested_email_config(raw_config):
            # Nested — iterar sobre cada sub-config
            for key, sub_config in raw_config.items():
                if not isinstance(sub_config, dict):
                    continue

                # Determinar company_id a partir da chave
                if key.startswith("company:"):
                    company_id = key.replace("company:", "", 1)
                elif key == "default":
                    company_id = fallback_company or "default"
                else:
                    # Role-based key — usar company fallback
                    company_id = fallback_company or "default"

                # Verificar se já existe
                existing = await db.user_email_configs.find_one(
                    {"user_id": user_id, "company_id": company_id},
                    {"_id": 0, "id": 1}
                )
                if existing:
                    skipped += 1
                    continue

                try:
                    doc = {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "company_id": company_id,
                        "email_address": sub_config.get("email_address", ""),
                        "imap_server": sub_config.get("imap_server", ""),
                        "imap_port": sub_config.get("imap_port", 993),
                        "smtp_server": sub_config.get("smtp_server", ""),
                        "smtp_port": sub_config.get("smtp_port", 465),
                        "encrypted_password": sub_config.get("encrypted_password", ""),
                        "google_refresh_token": sub_config.get("google_refresh_token"),
                        "google_access_token": sub_config.get("google_access_token"),
                        "google_email": sub_config.get("google_email"),
                        "auth_method": sub_config.get("auth_method", "none"),
                        "oauth_connected_at": sub_config.get("oauth_connected_at"),
                        "is_configured": sub_config.get("is_configured", False),
                        "is_primary": True,
                        "created_at": now,
                        "updated_at": now,
                    }
                    await db.user_email_configs.insert_one(doc)
                    created += 1
                except Exception as e:
                    if "duplicate key" in str(e).lower() or "E11000" in str(e):
                        skipped += 1
                    else:
                        logger.error(
                            f"[UserEmailConfig] Erro na migração user={user_id} "
                            f"company={company_id}: {e}"
                        )
                        errors += 1
        else:
            # Flat config (legacy) — migrar como config da empresa principal
            company_id = fallback_company or "default"

            existing = await db.user_email_configs.find_one(
                {"user_id": user_id, "company_id": company_id},
                {"_id": 0, "id": 1}
            )
            if existing:
                skipped += 1
                continue

            try:
                doc = {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "company_id": company_id,
                    "email_address": raw_config.get("email_address", ""),
                    "imap_server": raw_config.get("imap_server", ""),
                    "imap_port": raw_config.get("imap_port", 993),
                    "smtp_server": raw_config.get("smtp_server", ""),
                    "smtp_port": raw_config.get("smtp_port", 465),
                    "encrypted_password": raw_config.get("encrypted_password", ""),
                    "google_refresh_token": raw_config.get("google_refresh_token"),
                    "google_access_token": raw_config.get("google_access_token"),
                    "google_email": raw_config.get("google_email"),
                    "auth_method": raw_config.get("auth_method", "none"),
                    "oauth_connected_at": raw_config.get("oauth_connected_at"),
                    "is_configured": raw_config.get("is_configured", False),
                    "is_primary": True,
                    "created_at": now,
                    "updated_at": now,
                }
                await db.user_email_configs.insert_one(doc)
                created += 1
            except Exception as e:
                if "duplicate key" in str(e).lower() or "E11000" in str(e):
                    skipped += 1
                else:
                    logger.error(
                        f"[UserEmailConfig] Erro na migração user={user_id}: {e}"
                    )
                    errors += 1

    logger.info(
        f"[UserEmailConfig] Migração concluída: {created} criados, "
        f"{skipped} já existiam, {errors} erros, {len(users)} utilizadores"
    )

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "total_users": len(users),
    }


async def _sync_to_embedded(user_id: str, company_id: str, config: Dict[str, Any]):
    """
    Dual-write: sincroniza a config da coleção para o campo embebido
    no documento do utilizador (user.email_config["company:<company_id>"]).

    Isto garante retrocompatibilidade com código que ainda lê do embebido.
    """
    try:
        company_key = f"company:{company_id}"

        embedded_config = {
            "email_address": config.get("email_address", ""),
            "imap_server": config.get("imap_server", ""),
            "imap_port": config.get("imap_port", 993),
            "smtp_server": config.get("smtp_server", ""),
            "smtp_port": config.get("smtp_port", 465),
            "encrypted_password": config.get("encrypted_password", ""),
            "company_id": company_id,
            "is_configured": config.get("is_configured", False),
            "updated_at": config.get("updated_at", ""),
        }

        # Preservar campos OAuth se existirem
        if config.get("google_refresh_token"):
            embedded_config["google_refresh_token"] = config["google_refresh_token"]
        if config.get("google_access_token"):
            embedded_config["google_access_token"] = config["google_access_token"]
        if config.get("google_email"):
            embedded_config["google_email"] = config["google_email"]
        if config.get("auth_method") and config["auth_method"] != "none":
            embedded_config["auth_method"] = config["auth_method"]
        if config.get("oauth_connected_at"):
            embedded_config["oauth_connected_at"] = config["oauth_connected_at"]

        await db.users.update_one(
            {"id": user_id},
            {"$set": {f"email_config.{company_key}": embedded_config}}
        )

    except Exception as e:
        logger.warning(
            f"[UserEmailConfig] Erro no dual-write para user={user_id} "
            f"company={company_id}: {e}"
        )
