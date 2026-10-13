"""Company create / update / delete handlers.

Extraído de `routes/companies_crud.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from typing import Optional

from models.company import CompanyCreate, CompanyResponse, CompanyUpdate
from services.admin_helpers import _audit_log
from services.reauth_password import exigir_password_actual
from services.role_scope import utilizador_e_global
from services.user_management_scope import exigir_empresas_concediveis

logger = logging.getLogger(__name__)


async def run_create_company(data: CompanyCreate, *, actor: Optional[dict] = None):
    """Cria uma nova empresa. Só o Master (a rota exige-o)."""
    existing = await db.companies.find_one({"name": data.name})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma empresa com o nome '{data.name}'",
        )

    now = datetime.now(timezone.utc).isoformat()
    company_id = str(uuid.uuid4())

    doc = {
        "id": company_id,
        "name": data.name,
        # Rede / Grupo Empresarial (Lote 4, ponto 10). Por omissão `None`
        # — uma empresa nova nasce como ilha de uma só, e é o
        # administrador que a junta a um grupo. Herdar a rede de outra
        # empresa aqui seria abrir a fuga no acto da criação.
        "network_id": data.network_id,
        "nif": data.nif,
        "address": data.address,
        "phone": data.phone,
        "email": data.email,
        "website": data.website,
        "logo_url": data.logo_url,
        "email_sync_enabled": data.email_sync_enabled,
        "is_active": data.is_active,
        "smtp_email": data.smtp_email,
        "smtp_password": data.smtp_password,
        "smtp_host": data.smtp_host,
        "smtp_port": data.smtp_port,
        "imap_email": data.imap_email,
        "imap_password": data.imap_password,
        "imap_host": data.imap_host,
        "imap_port": data.imap_port,
        "created_at": now,
        "updated_at": now,
    }

    await db.companies.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"[COMPANIES] Empresa criada: {data.name} ({company_id})")

    return CompanyResponse(**doc)


def _rede_gravada(doc: Optional[dict]) -> str:
    """O `network_id` normalizado: ausente, `None` e vazio são a mesma coisa (ilha)."""
    return str((doc or {}).get("network_id") or "").strip()


async def _registar_rasto(actor: dict, acao: str, empresa_id: str, detalhes: dict) -> None:
    """Rasto em `audit_logs` (sem a password); nunca faz a operação falhar."""
    try:
        await _audit_log(acao, "company", empresa_id, actor, detalhes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[COMPANIES] Falha a registar %s: %s", acao, exc)


async def run_update_company(company_id: str, data: CompanyUpdate, *, actor: dict):
    """Atualiza os dados de uma empresa.

    Um perfil local só actualiza a SUA empresa e **nunca muda a rede**: o
    `network_id` define quem vê os dados de quem, e deixar o CEO de uma
    empresa pô-lo igual ao de outra dava-lhe, de graça, a leitura dos
    clientes dessa outra. É decisão do Master — e exige a password ACTUAL dele
    (`reauth_password`) quando a rede MUDA: um token roubado não redesenha a
    fronteira de dados. Reenviar a mesma rede (o formulário manda o objecto
    inteiro) não pede nada.
    """
    existing = await db.companies.find_one({"id": company_id})
    if not existing:
        existing = await db.companies.find_one({"name": company_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    real_id = existing.get("id", company_id)

    await exigir_empresas_concediveis(actor, [real_id])
    if data.network_id is not None and not utilizador_e_global(actor):
        raise HTTPException(
            status_code=403,
            detail="Apenas o perfil Master pode alterar a rede de uma empresa.",
        )
    # Abrir (ou fechar) uma empresa ao mercado de parceiros é decisão do Master, como a rede: um
    # Admin local não escolhe quem lhe manda leads. `model_fields_set` apanha o `null` explícito
    # (voltar ao automático), que `is not None` deixaria passar.
    if "aceita_parceiros" in data.model_fields_set and not utilizador_e_global(actor):
        raise HTTPException(
            status_code=403,
            detail="Apenas o perfil Master pode definir se a empresa recebe leads de parceiros.",
        )
    rede_antiga = _rede_gravada(existing)
    rede_nova = _rede_gravada({"network_id": data.network_id}) if data.network_id is not None else rede_antiga
    mudou_a_rede = rede_nova != rede_antiga
    if mudou_a_rede:
        # ANTES de qualquer escrita (a renomeação abaixo já mexe nos utilizadores).
        await exigir_password_actual(actor, data.confirm_password)

    if data.name and data.name != existing.get("name"):
        dup = await db.companies.find_one({"name": data.name})
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe uma empresa com o nome '{data.name}'",
            )
        old_name = existing.get("name")
        if old_name:
            await db.users.update_many(
                {"company": old_name},
                {"$set": {"company": data.name}},
            )
            logger.info(
                f"[COMPANIES] Nome da empresa '{old_name}' → '{data.name}' "
                f"atualizado em utilizadores"
            )

    update_fields = data.model_dump(exclude_unset=True)
    update_fields.pop("confirm_password", None)  # nunca chega à base de dados
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.companies.update_one(
        {"id": real_id},
        {"$set": update_fields},
    )

    updated = await db.companies.find_one({"id": real_id}, {"_id": 0})
    if not updated:
        updated = existing
        updated.update(update_fields)
    total_users = await db.users.count_documents({
        "company": updated.get("name", ""),
    })
    updated["total_users"] = total_users
    if not updated.get("id"):
        updated["id"] = real_id
    if not updated.get("name"):
        updated["name"] = company_id
    updated.pop("_id", None)

    if mudou_a_rede:
        await _registar_rasto(
            actor, "company_network_changed", real_id,
            {"company_name": existing.get("name"), "rede_antiga": rede_antiga, "rede_nova": rede_nova},
        )
    logger.info(f"[COMPANIES] Empresa atualizada: {real_id}")
    return CompanyResponse(**updated)


async def run_delete_company(company_id: str, password: Optional[str], *, actor: dict):
    """Remove uma empresa e gere utilizadores associados.

    Acção que não se desfaz: exige a password ACTUAL de quem elimina. A ordem é
    404 (a empresa existe?) → password (403/429) → estado (utilizadores só desta
    empresa, 400): sem a password o endpoint não diz nada sobre o estado da empresa.
    """
    company = await db.companies.find_one({"id": company_id})
    if not company:
        company = await db.companies.find_one({"name": company_id})
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    real_id = company.get("id", company_id)
    company_name = company.get("name", company_id)

    await exigir_password_actual(actor, password)

    users_with_this_company = await db.users.find(
        {"company": company_name},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(1000)

    blocked_users = []
    reassigned_users = []

    for u in users_with_this_company:
        other_ucrs = await db.user_company_roles.find({
            "user_id": u["id"],
            "company_id": {"$ne": real_id},
        }).to_list(10)

        if other_ucrs:
            first_other = other_ucrs[0]
            new_company = first_other.get(
                "company_name", first_other.get("company_id", "default"),
            )
            await db.users.update_one(
                {"id": u["id"]},
                {"$set": {"company": new_company}},
            )
            reassigned_users.append({
                "id": u["id"],
                "name": u.get("name", ""),
                "new_company": new_company,
            })
        else:
            blocked_users.append({
                "id": u["id"],
                "name": u.get("name", ""),
                "email": u.get("email", ""),
            })

    if blocked_users:
        names = ", ".join(
            [f"{u['name']} ({u['email']})" for u in blocked_users[:5]]
        )
        suffix = (
            f" e mais {len(blocked_users)-5}" if len(blocked_users) > 5 else ""
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Não é possível eliminar: {len(blocked_users)} utilizador(es) "
                f"têm apenas esta empresa: {names}{suffix}. "
                f"Atribua outra empresa a estes utilizadores primeiro."
            ),
        )

    deleted_ucrs = await db.user_company_roles.delete_many(
        {"company_id": real_id}
    )

    await db.company_email_configs.delete_one({"company_name": company_name})
    await db.user_email_configs.delete_many({"company_id": real_id})

    await db.companies.delete_one({"id": real_id})

    await _registar_rasto(
        actor, "company_deleted", real_id,
        {"company_name": company_name, "network_id": _rede_gravada(company) or None,
         "ucrs_removed": deleted_ucrs.deleted_count, "affected_users": len(reassigned_users)},
    )
    logger.info(
        f"[COMPANIES] Empresa eliminada: {company_name} ({real_id}). "
        f"UCRs removidos: {deleted_ucrs.deleted_count}. "
        f"Users reatribuídos: {len(reassigned_users)}."
    )
    return {
        "detail": "Empresa eliminada com sucesso",
        "affected_users": len(reassigned_users),
        "reassigned_users": reassigned_users,
        "ucrs_removed": deleted_ucrs.deleted_count,
    }
