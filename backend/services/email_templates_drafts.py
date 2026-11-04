"""Templates de resposta, notificações unread e auto-drafts.

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from database import db
from models.email import EmailTemplateCreate, EmailTemplateResponse
from services.email_draft_service import (
    get_pending_drafts,
    get_draft_stats,
    update_draft,
    send_draft,
    discard_draft,
    create_missing_doc_draft,
)
from utils.input_sanitization import sanitize_string, sanitize_email, sanitize_multiline_text, sanitize_single_line_text

logger = logging.getLogger(__name__)

# ==== MODELOS DE EMAIL (Flavio, 2026-11-04, pergunta 5a) ====
# Os modelos são POR EMPRESA: cada um vê os da empresa activa e os modelos gerais antigos (sem
# empresa). Só Master, Admin, CEO e Diretor criam, alteram ou apagam, e só os da empresa activa
# (o Master, global, qualquer um). Apagar é lógico (`is_deleted`), nunca físico. Antes não havia
# filtro nem permissão: qualquer utilizador alterava ou apagava os modelos de outra empresa, e
# sem empresa activa a listagem devolvia os de todas.

#: Quem altera modelos.
PAPEIS_QUE_GEREM_MODELOS = frozenset({"master", "admin", "ceo", "diretor"})

#: O que conta como «modelo geral» (sem empresa) — os antigos e os criados sem empresa activa.
_SEM_EMPRESA = [
    {"company_id": {"$exists": False}},
    {"company_id": None},
    {"company_id": ""},
    {"company_id": "default"},
]


def condicao_dos_modelos_visiveis(company_id: Optional[str]) -> dict:
    """A consulta dos modelos que se vêem com esta empresa activa. PURA."""
    ramos = list(_SEM_EMPRESA)
    if company_id:
        ramos.insert(0, {"company_id": company_id})
    return {"$and": [{"is_deleted": {"$ne": True}}, {"$or": ramos}]}


def _papel(current_user: dict) -> str:
    from services.role_scope import papel_concreto_do_utilizador

    return papel_concreto_do_utilizador(current_user) or ""


def exigir_quem_gere_modelos(current_user: dict) -> None:
    if _papel(current_user) not in PAPEIS_QUE_GEREM_MODELOS:
        raise HTTPException(
            status_code=403,
            detail="Só Master, Admin, CEO e Diretor podem alterar modelos de email.",
        )


async def _empresa_activa(request: Optional[Request], current_user: dict) -> Optional[str]:
    if request is None:
        return None
    from services.auth import get_active_company_id_async

    try:
        return await get_active_company_id_async(request, current_user)
    except Exception:
        return None


async def _modelo_alteravel(template_id: str, request: Optional[Request], current_user: dict) -> dict:
    """O modelo, se existe, não está apagado e é da empresa activa (Master: qualquer). Senão 404."""
    exigir_quem_gere_modelos(current_user)
    existente = await db.email_templates.find_one(
        {"id": template_id, "is_deleted": {"$ne": True}}, {"_id": 0}
    )
    if not existente:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    if _papel(current_user) == "master":
        return existente
    company_id = await _empresa_activa(request, current_user)
    if not company_id or existente.get("company_id") != company_id:
        # A mesma resposta de «não existe»: não se confirma o modelo de outra empresa.
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return existente


async def run_get_email_templates(request: Request, current_user: dict, category: Optional[str] = None):
    """Listar modelos: os da empresa activa + os gerais (sem empresa)."""
    company_id = await _empresa_activa(request, current_user)
    query = condicao_dos_modelos_visiveis(company_id)
    if category:
        query["$and"].append({"category": category})

    templates = await db.email_templates.find(
        query,
        {"_id": 0}
    ).sort("usage_count", -1).to_list(50)

    return templates


async def run_create_email_template(template: EmailTemplateCreate, request: Request, current_user: dict):
    """Criar novo modelo (na empresa activa)."""
    exigir_quem_gere_modelos(current_user)

    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    company_id = await _empresa_activa(request, current_user) or "default"

    template_doc = {
        "id": template_id,
        "name": sanitize_string(template.name, max_length=200),
        "subject": sanitize_single_line_text(template.subject, max_length=300),
        "body": sanitize_multiline_text(template.body, max_length=10000),
        "category": template.category,
        "is_default": template.is_default,
        "company_id": company_id,  # MULTI-EMPRESA
        "created_by": current_user["id"],
        "created_at": now,
        "usage_count": 0
    }

    # Se for default, remover default dos outros DA MESMA EMPRESA
    if template.is_default:
        await db.email_templates.update_many(
            {"category": template.category, "company_id": company_id},
            {"$set": {"is_default": False}}
        )

    await db.email_templates.insert_one(template_doc)

    return EmailTemplateResponse(**template_doc)


async def run_update_email_template(template_id: str, template: EmailTemplateCreate, current_user: dict, request: Optional[Request] = None):
    """Actualizar modelo (só quem gere modelos, só da empresa activa)."""
    await _modelo_alteravel(template_id, request, current_user)

    update_data = {
        "name": sanitize_string(template.name, max_length=200),
        "subject": sanitize_single_line_text(template.subject, max_length=300),
        "body": sanitize_multiline_text(template.body, max_length=10000),
        "category": template.category,
        "is_default": template.is_default,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.email_templates.update_one(
        {"id": template_id},
        {"$set": update_data}
    )

    updated = await db.email_templates.find_one({"id": template_id}, {"_id": 0})
    return EmailTemplateResponse(**updated)


async def run_delete_email_template(template_id: str, current_user: dict, request: Optional[Request] = None):
    """Apagar modelo — lógico (`is_deleted`), só quem gere modelos, só da empresa activa."""
    await _modelo_alteravel(template_id, request, current_user)
    await db.email_templates.update_one(
        {"id": template_id},
        {"$set": {
            "is_deleted": True,
            "status": "eliminado",
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": current_user.get("id"),
        }},
    )
    return {"success": True}


def preencher_modelo(texto: str, variaveis: dict) -> str:
    """Substitui `{variavel}` pelos dados do processo. PURA.

    Aceita `{cliente}`/`{email_cliente}` (os nomes antigos) e qualquer chave de
    `_extract_email_variables` (`{p1_nif}`, `{banco_atual}`, `{process_number}`...). Uma chave
    desconhecida fica como está (o utilizador vê que falta e corrige).
    """
    texto = str(texto or "")
    for chave, valor in variaveis.items():
        texto = texto.replace("{" + str(chave) + "}", "" if valor is None else str(valor))
    return texto


async def run_use_template(template_id: str, process_id: str, current_user: dict, request: Optional[Request] = None):
    """Aplicar um modelo a um processo: devolve assunto e corpo preenchidos."""
    from services.email_template_vars import _extract_email_variables

    company_id = await _empresa_activa(request, current_user)
    template = await db.email_templates.find_one(
        {"$and": [{"id": template_id}, condicao_dos_modelos_visiveis(company_id)]},
        {"_id": 0},
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    await db.email_templates.update_one(
        {"id": template_id},
        {"$inc": {"usage_count": 1}}
    )

    body = template.get("body", "")
    subject = template.get("subject", "")

    process = await db.processes.find_one({"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if process:
        variaveis = _extract_email_variables(process, current_user, "")
        variaveis["cliente"] = variaveis.get("client_name") or ""
        variaveis["email_cliente"] = variaveis.get("p1_email") or ""
        body = preencher_modelo(body, variaveis)
        subject = preencher_modelo(subject, variaveis)

    return {
        "subject": subject,
        "body": body
    }


async def run_get_unread_notifications(current_user: dict):
    """
    Obter contagem de emails não lidos por processo.
    Para mostrar badges de notificação.
    """
    # Obter processos do utilizador
    user_email = current_user.get("email", "").lower()
    
    # Admin/CEO veem todos (DA SUA REDE — Bloco A), outros só os seus
    from services.tenant_network import build_tenant_process_condition, com_isolamento
    tenant = await build_tenant_process_condition(current_user)
    if current_user["role"] in ["master", "admin", "ceo"]:
        processes = await db.processes.find(
            com_isolamento(tenant, {}), {"_id": 0, "id": 1, "client_name": 1}
        ).to_list(1000)
    else:
        processes = await db.processes.find(
            com_isolamento(tenant, {"assigned_to": current_user["id"]}),
            {"_id": 0, "id": 1, "client_name": 1}
        ).to_list(1000)
    
    process_ids = [p["id"] for p in processes]
    
    # Contar emails não lidos por processo
    pipeline = [
        {"$match": {
            "process_id": {"$in": process_ids},
            "is_read": False,
            "is_archived": {"$ne": True}
        }},
        {"$group": {
            "_id": "$process_id",
            "count": {"$sum": 1},
            "latest": {"$max": "$sent_at"}
        }}
    ]
    
    unread_counts = await db.emails.aggregate(pipeline).to_list(1000)
    
    # Mapear para resposta
    result = {}
    for item in unread_counts:
        process_id = item["_id"]
        process = next((p for p in processes if p["id"] == process_id), None)
        if process:
            result[process_id] = {
                "count": item["count"],
                "latest": item["latest"],
                "client_name": process.get("client_name", "")
            }
    
    total_unread = sum(r["count"] for r in result.values())
    
    return {
        "total_unread": total_unread,
        "by_process": result
    }


def _papel_efectivo(current_user: dict) -> str:
    """O cargo EFECTIVO (perfil activo), não o do JWT."""
    return str(current_user.get("effective_role") or current_user.get("role") or "")


async def _exigir_rascunho_legivel(draft_id: str, current_user: dict) -> None:
    """D-31: editar, enviar ou descartar um rascunho exige poder LÊ-LO.

    Estas três rotas recebiam só o id do rascunho: qualquer sessão de staff
    enviava (do seu servidor de email) ou apagava o rascunho de um cliente de
    outra rede. **404 e nunca 403** — distinguir «não existe» de «não é teu»
    confirma o id a quem o adivinha.
    """
    from services.email_access import pode_ler_email

    rascunho = await db.emails.find_one({"id": draft_id, "is_auto_draft": True}, {"_id": 0})
    if not rascunho or not await pode_ler_email(rascunho, current_user):
        raise HTTPException(status_code=404, detail="Rascunho não encontrado")


async def _exigir_processo_do_rascunho_aberto(draft_id: str, current_user: dict) -> None:
    """D-34: o rascunho de um processo FECHADO não se envia (reabrir primeiro).

    Só o ENVIO: descartar continua a ser possível — é a saída de quem não
    quer que o rascunho fique pendente. Corre depois da visibilidade, para
    «fechado» não ser um oráculo sobre outra rede.
    """
    from services.process_closed_guard import exigir_processo_aberto_por_id

    rascunho = await db.emails.find_one({"id": draft_id}, {"_id": 0, "process_id": 1})
    await exigir_processo_aberto_por_id((rascunho or {}).get("process_id") or "", current_user)


async def run_list_auto_drafts(current_user: dict, limit: int = 20):
    """
    Listar rascunhos automáticos pendentes — os da rede do utilizador.
    Gestão e administrativo vêem todos os da rede; os outros, os dos seus processos.
    """
    drafts = await get_pending_drafts(
        user_id=current_user["id"],
        user_role=_papel_efectivo(current_user),
        limit=limit,
        user=current_user,
    )
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=_papel_efectivo(current_user),
        user=current_user,
    )
    return {"drafts": drafts, "stats": stats}


async def run_auto_drafts_stats(current_user: dict):
    """Obter estatísticas de rascunhos automáticos pendentes."""
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=_papel_efectivo(current_user),
        user=current_user,
    )
    return stats


async def run_edit_auto_draft(draft_id: str, data: dict, current_user: dict):
    """Editar um rascunho automático (subject, body, to_emails)."""
    await _exigir_rascunho_legivel(draft_id, current_user)
    # Sanitize user inputs before passing to service
    if "subject" in data and data["subject"]:
        data["subject"] = sanitize_single_line_text(data["subject"], max_length=300)
    if "body" in data and data["body"]:
        data["body"] = sanitize_multiline_text(data["body"], max_length=10000)
    if "to_emails" in data and data["to_emails"]:
        data["to_emails"] = [e for e in (sanitize_email(e) for e in data["to_emails"]) if e]

    result = await update_draft(draft_id, data)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Erro ao atualizar"))
    return result


async def run_send_auto_draft(draft_id: str, current_user: dict, account: str = "power"):
    """Enviar um rascunho automático."""
    await _exigir_rascunho_legivel(draft_id, current_user)
    await _exigir_processo_do_rascunho_aberto(draft_id, current_user)
    result = await send_draft(
        draft_id=draft_id,
        user_id=current_user["id"],
        account=account,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao enviar"))
    return result


async def run_delete_auto_draft(draft_id: str, current_user: dict):
    """Descartar (eliminar) um rascunho automático."""
    await _exigir_rascunho_legivel(draft_id, current_user)
    result = await discard_draft(draft_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Rascunho não encontrado"))
    return result


async def run_manually_create_draft(data: dict, current_user: dict):
    """
    Criar manualmente um rascunho automático para um documento em falta.
    Útil quando o admin quer gerar um rascunho para um processo específico.
    """
    process_id = data.get("process_id")
    doc_type = data.get("doc_type")

    if not process_id or not doc_type:
        raise HTTPException(status_code=400, detail="process_id e doc_type são obrigatórios")

    # D-31: criar um rascunho NUM processo exige poder vê-lo (rede incluída).
    from services.email_access import exigir_processo_legivel

    await exigir_processo_legivel(process_id, current_user)

    # D-34: criar um rascunho de email NUM processo fechado também exige reabrir.
    from services.process_closed_guard import exigir_processo_aberto_por_id

    await exigir_processo_aberto_por_id(process_id, current_user)

    # Obter dados do processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    result = await create_missing_doc_draft(
        process_id=process_id,
        client_name=process.get("client_name", ""),
        missing_doc_type=doc_type,
        process_number=process.get("process_number", ""),
    )

    return result


