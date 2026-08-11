"""Minuta de exclusividade template admin endpoints + active-template lookup.

Extraído de `routes/rgpd.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from database import db

logger = logging.getLogger(__name__)

MINUTA_TEMPLATE_VERSIONS_COLLECTION = "minuta_template_versions"

MINUTA_DEFAULT_TEMPLATE = """MINUTA DE EXCLUSIVIDADE

Eu, {{NOME}}, titular do {{TIPO_DOCUMENTO}} n.º {{NUMERO_DOCUMENTO}}, válido até {{VALIDADE_DOCUMENTO}} com o nº de contribuinte {{CONTRIBUINTE}}, residente na {{MORADA}}, {{LOCALIDADE}}, código postal: {{CODIGO_POSTAL}}, venho por este meio solicitar de forma exclusiva e de livre vontade os serviços gratuitos de intermediação de crédito da {{NOME_EMPRESA}}, vinculado sob o registo nº _________ no Banco de Portugal, abdicando dos serviços de outras entidades de intermediação de crédito."""


class MinutaTemplateUpdate(BaseModel):
    """Modelo para actualização do template Minuta."""
    content: str
    changelog: Optional[str] = Field(None, description="Descrição opcional da alteração realizada")


async def _get_active_minuta_template() -> Optional[str]:
    """
    Função auxiliar para obter o texto do template Minuta ativo.

    Prioridade:
    1. Versão ativa na coleção minuta_template_versions
    2. Conteúdo em system_config (compatibilidade retroativa)
    3. Template padrão definido no código
    """
    try:
        active_version = await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].find_one(
            {"is_active": True},
            {"_id": 0, "content": 1},
        )
        if active_version and active_version.get("content"):
            return active_version["content"]

        doc = await db.system_config.find_one(
            {"_id": "minuta_template"},
            {"_id": 0, "content": 1},
        )
        if doc and doc.get("content"):
            return doc["content"]

        return MINUTA_DEFAULT_TEMPLATE
    except Exception as e:
        logger.error(f"Erro ao obter template Minuta ativo: {e}")
        return MINUTA_DEFAULT_TEMPLATE


async def run_get_minuta_template(user: dict):
    """Obter o template de texto da Minuta de Exclusividade."""
    try:
        doc = await db.system_config.find_one({"_id": "minuta_template"}, {"_id": 0})

        if doc and doc.get("content"):
            return {
                "content": doc["content"],
                "updated_at": doc.get("updated_at"),
                "updated_by": doc.get("updated_by"),
                "is_default": False,
                "active_version_id": doc.get("active_version_id"),
                "active_version": doc.get("active_version"),
            }

        return {
            "content": MINUTA_DEFAULT_TEMPLATE,
            "updated_at": None,
            "updated_by": None,
            "is_default": True,
            "active_version_id": None,
            "active_version": None,
        }
    except Exception as e:
        logger.error(f"Erro ao obter template Minuta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter template Minuta")


async def run_update_minuta_template(template_data: MinutaTemplateUpdate, user: dict):
    """Atualizar o template de texto da Minuta de Exclusividade (com versionamento)."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        created_by = user.get("name", user.get("email", "unknown"))

        last_version = await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].find_one(
            sort=[("version", -1)]
        )
        next_version = (last_version["version"] + 1) if last_version else 1

        new_version_id = str(uuid.uuid4())
        version_doc = {
            "id": new_version_id,
            "content": template_data.content,
            "version": next_version,
            "changelog": template_data.changelog,
            "created_at": now,
            "created_by": created_by,
            "is_active": True,
        }
        await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].insert_one(version_doc)

        await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].update_many(
            {"id": {"$ne": new_version_id}},
            {"$set": {"is_active": False}},
        )

        await db.system_config.update_one(
            {"_id": "minuta_template"},
            {
                "$set": {
                    "content": template_data.content,
                    "active_version_id": new_version_id,
                    "active_version": next_version,
                    "updated_at": now,
                    "updated_by": created_by,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

        logger.info(f"Template Minuta versão {next_version} criada por {created_by}")

        return {
            "success": True,
            "message": f"Template Minuta atualizado com sucesso (versão {next_version})",
            "version": next_version,
            "version_id": new_version_id,
            "updated_at": now,
        }
    except Exception as e:
        logger.error(f"Erro ao atualizar template Minuta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar template Minuta")


async def run_list_minuta_template_versions(user: dict):
    """Listar todas as versões do template Minuta."""
    try:
        versions = await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].find(
            {},
            {"_id": 0, "content": 0},
        ).sort("version", -1).to_list(100)

        return {
            "versions": versions,
            "total": len(versions),
        }
    except Exception as e:
        logger.error(f"Erro ao listar versões do template Minuta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao listar versões")


async def run_get_minuta_template_version(version_id: str, user: dict):
    """Obter o conteúdo completo de uma versão específica do template Minuta."""
    try:
        version = await db[MINUTA_TEMPLATE_VERSIONS_COLLECTION].find_one(
            {"id": version_id},
            {"_id": 0},
        )

        if not version:
            raise HTTPException(status_code=404, detail="Versão do template Minuta não encontrada")

        return version
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter versão do template Minuta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter versão")
