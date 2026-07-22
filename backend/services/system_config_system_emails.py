"""
System email configs CRUD (DOCUMENTS, RGPD, SYSTEM_ALERTS, etc.).

Extraído de `routes/system_config.py`.
Do NOT overwrite `services/system_config.py` (core config load/save).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

VALID_SYSTEM_EMAIL_PURPOSES = ["DOCUMENTS", "RGPD", "SYSTEM_ALERTS", "NOTIFICATIONS", "CUSTOM"]


class SystemEmailConfigCreate(BaseModel):
    purpose: str  # e.g. "DOCUMENTS", "RGPD", "SYSTEM_ALERTS"
    host: str
    port: int = 465
    user: str
    password: str
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    use_ssl: bool = True
    use_tls: bool = False


class SystemEmailConfigUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None  # if empty, keep existing
    from_name: Optional[str] = None
    from_email: Optional[str] = None
    use_ssl: Optional[bool] = None
    use_tls: Optional[bool] = None
    is_active: Optional[bool] = None


def _mask_system_email_config(doc: dict) -> dict:
    """Remove encrypted_password, add has_password boolean."""
    doc = dict(doc)
    doc.pop("encrypted_password", None)
    doc["has_password"] = bool(doc.pop("_has_password", False))
    return doc


async def run_list_system_email_configs() -> dict:
    """Listar todas as configurações de email do sistema."""
    from database import db
    cursor = db.system_email_configs.find({}, {"encrypted_password": 0})
    results = []
    async for doc in cursor:
        has_pwd = False
        pw = await db.system_email_configs.find_one(
            {"purpose": doc["purpose"]},
            {"encrypted_password": 1}
        )
        if pw and pw.get("encrypted_password"):
            has_pwd = True
        doc = dict(doc)
        doc["has_password"] = has_pwd
        results.append(doc)
    return {"configs": results, "valid_purposes": VALID_SYSTEM_EMAIL_PURPOSES}


async def run_get_system_email_config(purpose: str) -> dict:
    """Obter configuração de email do sistema por propósito."""
    if purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db
    purpose_upper = purpose.upper()
    doc = await db.system_email_configs.find_one({"purpose": purpose_upper})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")
    has_pwd = bool(doc.get("encrypted_password"))
    return _mask_system_email_config({**doc, "_has_password": has_pwd})


async def run_create_system_email_config(payload: SystemEmailConfigCreate, user: dict) -> dict:
    """Criar nova configuração de email do sistema."""
    if payload.purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {payload.purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db
    from services.encryption import encryption_service

    purpose = payload.purpose.upper()
    existing = await db.system_email_configs.find_one({"purpose": purpose})
    if existing:
        raise HTTPException(status_code=409, detail=f"Configuração para '{purpose}' já existe. Use PUT para actualizar.")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": purpose,
        "purpose": purpose,
        "host": payload.host,
        "port": payload.port,
        "user": payload.user,
        "encrypted_password": encryption_service.encrypt(payload.password) if payload.password else "",
        "from_name": payload.from_name,
        "from_email": payload.from_email,
        "use_ssl": payload.use_ssl,
        "use_tls": payload.use_tls,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.system_email_configs.insert_one(doc)
    logger.info(f"System email config criada para '{purpose}' por {user.get('email')}")
    return _mask_system_email_config({**doc, "_has_password": bool(payload.password)})


async def run_update_system_email_config(purpose: str, payload: SystemEmailConfigUpdate, user: dict) -> dict:
    """Actualizar configuração de email do sistema."""
    if purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db
    from services.encryption import encryption_service

    purpose_upper = purpose.upper()
    existing = await db.system_email_configs.find_one({"purpose": purpose_upper})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")

    update_fields = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "password":
            if value:  # non-empty string → encrypt and update
                update_fields["encrypted_password"] = encryption_service.encrypt(value)
            # if empty or None → keep existing password (do nothing)
        else:
            update_fields[field] = value

    if not update_fields:
        return {"message": "Nenhum campo para actualizar", "purpose": purpose_upper}

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.system_email_configs.update_one(
        {"purpose": purpose_upper},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")

    logger.info(f"System email config actualizada para '{purpose_upper}' por {user.get('email')}")
    updated = await db.system_email_configs.find_one({"purpose": purpose_upper})
    has_pwd = bool(updated.get("encrypted_password")) if updated else False
    return _mask_system_email_config({**updated, "_has_password": has_pwd})


async def run_delete_system_email_config(purpose: str, user: dict) -> dict:
    """Eliminar configuração de email do sistema."""
    if purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db

    purpose_upper = purpose.upper()
    result = await db.system_email_configs.delete_one({"purpose": purpose_upper})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")

    logger.info(f"System email config eliminada para '{purpose_upper}' por {user.get('email')}")
    return {"success": True, "message": f"Configuração '{purpose_upper}' eliminada"}


async def run_test_system_email_config(purpose: str) -> dict:
    """Testar ligação SMTP para um propósito específico."""
    if purpose.upper() not in VALID_SYSTEM_EMAIL_PURPOSES:
        raise HTTPException(status_code=400, detail=f"Purpose inválido: {purpose}. Válidos: {VALID_SYSTEM_EMAIL_PURPOSES}")
    from database import db
    from services.encryption import encryption_service

    purpose_upper = purpose.upper()
    doc = await db.system_email_configs.find_one({"purpose": purpose_upper})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Configuração para '{purpose_upper}' não encontrada")

    if not doc.get("is_active", True):
        return {"success": False, "message": f"Configuração '{purpose_upper}' está inactiva"}

    encrypted_pw = doc.get("encrypted_password", "")
    password = encryption_service.decrypt(encrypted_pw) if encrypted_pw else ""

    host = doc.get("host", "")
    port = int(doc.get("port", 465))
    smtp_user = doc.get("user", "")
    use_ssl = doc.get("use_ssl", True)
    use_tls = doc.get("use_tls", False)

    if not host or not smtp_user:
        return {"success": False, "message": "Host ou utilizador não configurado"}

    try:
        import smtplib
        import ssl

        context = ssl.create_default_context()
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if use_tls:
                server.starttls(context=context)

        server.login(smtp_user, password)
        server.quit()
        logger.info(f"[System Email Test] Ligação SMTP bem sucedida para '{purpose_upper}' ({host}:{port})")
        return {"success": True, "message": f"Ligação SMTP bem sucedida para '{purpose_upper}' ({host}:{port})"}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "Erro de autenticação: utilizador ou password incorrectos"}
    except smtplib.SMTPConnectError:
        return {"success": False, "message": "Não foi possível conectar ao servidor SMTP"}
    except TimeoutError:
        return {"success": False, "message": "Timeout: servidor SMTP não respondeu"}
    except Exception as e:
        logger.error(f"[System Email Test] Erro para '{purpose_upper}': {type(e).__name__}: {e}")
        return {"success": False, "message": f"Erro: {type(e).__name__}: {str(e)}"}
