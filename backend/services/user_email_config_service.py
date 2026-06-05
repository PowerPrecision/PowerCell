"""
====================================================================
SERVIÇO: User Email Config Service — CRUD + Migração
====================================================================
Gere a coleção user_email_configs, a fonte canónica de configurações
de email pessoal por utilizador e empresa.

COLEÇÃO: user_email_configs
INDEX ÚNICO: (user_id, company_id)

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


async def get_user_email_config(user_id: str, company_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtém a config de email de um utilizador para uma empresa específica.

    Args:
        user_id: ID do utilizador.
        company_id: ID/nome da empresa.

    Returns:
        Dict com a config ou None se não existir.
    """
    return await db.user_email_configs.find_one(
        {"user_id": user_id, "company_id": company_id},
        {"_id": 0}
    )


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
) -> Dict[str, Any]:
    """
    Cria ou atualiza a config de email de um utilizador para uma empresa.
    Usa upsert com o índice único (user_id, company_id).

    Também faz dual-write para o user.email_config embebido (backward compat).

    Returns:
        Dict com o documento atualizado.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Verificar se já existe
    existing = await db.user_email_configs.find_one(
        {"user_id": user_id, "company_id": company_id},
        {"_id": 0}
    )

    if existing:
        # Atualizar — preservar campos que não foram enviados
        update_data = {
            "email_address": email_address.strip().lower(),
            "imap_server": imap_server.strip(),
            "imap_port": imap_port,
            "smtp_server": smtp_server.strip(),
            "smtp_port": smtp_port,
            "is_configured": is_configured,
            "updated_at": now,
        }

        # Password: só atualizar se foi fornecida uma nova
        if encrypted_password:
            update_data["encrypted_password"] = encrypted_password

        # OAuth: só atualizar se foram fornecidos novos valores
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

        await db.user_email_configs.update_one(
            {"user_id": user_id, "company_id": company_id},
            {"$set": update_data}
        )

        # Recarregar o documento atualizado
        updated = await db.user_email_configs.find_one(
            {"user_id": user_id, "company_id": company_id},
            {"_id": 0}
        )

        # Dual-write: atualizar embebido
        await _sync_to_embedded(user_id, company_id, updated or update_data)

        return updated or update_data

    else:
        # Criar novo documento
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "company_id": company_id,
            "email_address": email_address.strip().lower(),
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
            "created_at": now,
            "updated_at": now,
        }

        try:
            await db.user_email_configs.insert_one(doc)
        except Exception as e:
            # Duplicate key — fazer update em vez de insert
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                logger.warning(
                    f"[UserEmailConfig] Duplicate key on insert for user={user_id} "
                    f"company={company_id}. A fazer upsert."
                )
                await db.user_email_configs.update_one(
                    {"user_id": user_id, "company_id": company_id},
                    {"$set": {k: v for k, v in doc.items() if k != "id" and k != "created_at"}}
                )
                doc = await db.user_email_configs.find_one(
                    {"user_id": user_id, "company_id": company_id},
                    {"_id": 0}
                )
            else:
                raise

        # Dual-write: atualizar embebido
        await _sync_to_embedded(user_id, company_id, doc)

        return doc


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


async def delete_user_email_config(user_id: str, company_id: str) -> bool:
    """
    Remove a config de email de um utilizador para uma empresa.
    """
    result = await db.user_email_configs.delete_one(
        {"user_id": user_id, "company_id": company_id}
    )

    # Também limpar do embebido
    if result.deleted_count > 0:
        company_key = f"company:{company_id}"
        user_doc = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "email_config": 1}
        )
        if user_doc and user_doc.get("email_config", {}).get(company_key):
            await db.users.update_one(
                {"id": user_id},
                {"$unset": {f"email_config.{company_key}": ""}}
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
        {"email_config": {"$exists": True, "$ne": None, "$ne": ""}},
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
