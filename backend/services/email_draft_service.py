"""
====================================================================
EMAIL DRAFT SERVICE - PowerCell
====================================================================
Serviço para geração automática de rascunhos de e-mails por IA.

Funcionalidades:
- Gerar rascunhos personalizados quando documentos em falta são detetados
- Deduplicação (não gera rascunho duplicado para mesmo processo + tipo de doc)
- Integração com system_config para toggle on/off
- Configuração de prompt base e tipos de documentos elegíveis
====================================================================
"""

import logging
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from database import db
from services.ai_document_analyzer import get_openai_client

logger = logging.getLogger(__name__)


def is_draft_status(status) -> bool:
    """True if status is the draft enum or the string 'draft'."""
    if status is None:
        return False
    value = status.value if hasattr(status, "value") else status
    return str(value).lower() == "draft"


def stamp_draft_ttl_fields(
    target: dict,
    *,
    now: datetime | None = None,
    include_created: bool = True,
) -> datetime:
    """Stamp native BSON Date fields required by ttl_email_drafts.

    MongoDB TTL indexes ignore ISO strings — they need datetime objects.
    """
    now = now or datetime.now(timezone.utc)
    if include_created:
        target["created_at_dt"] = now
    target["updated_at_dt"] = now
    return now


# Prompt base para geração de rascunhos
DEFAULT_DRAFT_PROMPT = """Escreve um e-mail profissional em português (pt-PT) para um cliente de crédito habitação.

Contexto:
- Nome do cliente: {client_name}
- Tipo de documento em falta: {document_type}
- Número de processo: {process_number}
- Empresa: {company_name}

Regras:
1. Tom profissional mas amigável
2. Explicar brevemente porque o documento é necessário
3. Prazo de entrega: 5 dias úteis
4. Oferecer ajuda para questões
5. Não usar linguagem excessivamente formal
6. Incluir saudação e despedida apropriadas

Gera:
1. Um assunto (subject) conciso e claro
2. O corpo do email (body) em texto plano

Retorna APENAS JSON válido:
{
    "subject": "...",
    "body": "..."
}"""

# Tipos de documento que geram rascunhos automáticos (por omissão)
DEFAULT_ELIGIBLE_DOC_TYPES = [
    "irs",
    "recibo_vencimento",
    "declaracao_irs",
    "extrato_bancario",
    "mapa_responsabilidades",
    "comprovativo_morada",
    "cc",
    "caderneta_predial",
    "certidao_teor",
    "licenca_habitacao",
]

# Mapeamento de tipos de documento para nomes amigáveis
DOC_TYPE_LABELS = {
    "irs": "IRS (Declaração de Rendimentos)",
    "recibo_vencimento": "Recibo de Vencimento",
    "declaracao_irs": "Declaração de IRS",
    "extrato_bancario": "Extrato Bancário",
    "mapa_responsabilidades": "Mapa de Responsabilidades",
    "comprovativo_morada": "Comprovativo de Morada",
    "cc": "Cartão de Cidadão / BI",
    "caderneta_predial": "Caderneta Predial",
    "certidao_teor": "Certidão de Teor",
    "licenca_habitacao": "Licença de Habitação",
}


async def get_auto_draft_config() -> Dict[str, Any]:
    """Obter configuração de rascunhos automáticos."""
    from services.system_config import get_system_config
    config = await get_system_config()

    # Verificar se a secção auto_draft existe na config
    auto_draft = getattr(config, "auto_draft", None)
    if not auto_draft:
        return {
            "enabled": False,
            "base_prompt": DEFAULT_DRAFT_PROMPT,
            "eligible_doc_types": DEFAULT_ELIGIBLE_DOC_TYPES,
        }

    return {
        "enabled": getattr(auto_draft, "enabled", False),
        "base_prompt": getattr(auto_draft, "base_prompt", DEFAULT_DRAFT_PROMPT),
        "eligible_doc_types": getattr(auto_draft, "eligible_doc_types", DEFAULT_ELIGIBLE_DOC_TYPES),
    }


async def create_missing_doc_draft(
    process_id: str,
    client_name: str,
    missing_doc_type: str,
    process_number: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Criar rascunho automático para documento em falta.

    Args:
        process_id: ID do processo
        client_name: Nome do cliente
        missing_doc_type: Tipo de documento em falta
        process_number: Número do processo (opcional)
        company_name: Nome da empresa (opcional)

    Returns:
        Dict com resultado da operação
    """
    try:
        # 1. Verificar se a funcionalidade está activa
        config = await get_auto_draft_config()
        if not config["enabled"]:
            logger.debug("Auto-draft desactivado nas configurações")
            return {"success": False, "reason": "disabled"}

        # 2. Verificar se o tipo de documento é elegível
        eligible_types = config["eligible_doc_types"]
        if missing_doc_type.lower() not in [t.lower() for t in eligible_types]:
            logger.debug(f"Tipo de documento '{missing_doc_type}' não é elegível para auto-draft")
            return {"success": False, "reason": "not_eligible"}

        # 3. Verificar deduplicação - já existe rascunho para este processo + tipo?
        existing_draft = await db.emails.find_one({
            "process_id": process_id,
            "is_auto_draft": True,
            "status": "draft",
            "auto_draft_doc_type": missing_doc_type.lower(),
        })

        if existing_draft:
            logger.info(f"Rascunho duplicado ignorado para processo {process_id}, doc {missing_doc_type}")
            return {
                "success": False,
                "reason": "duplicate",
                "existing_draft_id": existing_draft.get("id"),
            }

        # 4. Obter email do cliente
        process = await db.processes.find_one(
            {"id": process_id},
            {"_id": 0, "client_email": 1, "process_number": 1}
        )
        client_email = process.get("client_email", "") if process else ""
        if not process_number:
            process_number = process.get("process_number", "") if process else ""

        if not client_email:
            logger.warning(f"Cliente sem email para processo {process_id}, rascunho não criado")
            return {"success": False, "reason": "no_client_email"}

        # 5. Gerar rascunho com IA
        doc_label = DOC_TYPE_LABELS.get(missing_doc_type.lower(), missing_doc_type)
        prompt = config["base_prompt"]
        if not company_name:
            company_name = "Power Real Estate & Precision Crédito"

        # Substituir variáveis no prompt
        prompt_filled = prompt.format(
            client_name=client_name,
            document_type=doc_label,
            process_number=process_number or "N/A",
            company_name=company_name,
        )

        client = get_openai_client()
        if not client:
            logger.error("OpenAI client não disponível para gerar rascunho")
            return {"success": False, "reason": "no_ai_client"}

        import json
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "És um especialista em comunicação com clientes de crédito habitação. Gera e-mails profissionais e personalizados. Retorna APENAS JSON válido, sem texto adicional."},
                {"role": "user", "content": prompt_filled},
            ],
            max_tokens=1000,
            temperature=0.7,
            response_format={"type": "json_object"}
        )

        response_text = response.choices[0].message.content

        # Parse robusto da resposta JSON
        from services.ai_document_analyzer import _parse_json_response
        draft_content = _parse_json_response(response_text)
        if not draft_content:
            logger.error(f"Resposta da IA não contém JSON válido: {response_text[:200]}")
            return {"success": False, "reason": "invalid_ai_response"}

        subject = draft_content.get("subject", f"Documento necessário: {doc_label}")
        body = draft_content.get("body", f"Caro(a) {client_name},\n\nPrecisamos do documento: {doc_label}.")

        # 6. Guardar rascunho na BD
        now = datetime.now(timezone.utc)
        draft_id = str(uuid.uuid4())

        draft_doc = {
            "id": draft_id,
            "process_id": process_id,
            "direction": "sent",
            "from_email": "sistema@powercell.pt",
            "to_emails": [client_email] if client_email else [],
            "subject": subject,
            "body": body,
            "status": "draft",
            "is_auto_draft": True,
            "auto_draft_doc_type": missing_doc_type.lower(),
            "auto_draft_doc_label": doc_label,
            # Campos ISO string (compatibilidade com código existente)
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "is_important": False,
            "is_read": True,
            "is_starred": False,
            "is_archived": False,
            "labels": ["auto-draft"],
        }
        stamp_draft_ttl_fields(draft_doc, now=now)

        await db.emails.insert_one(draft_doc)

        logger.info(
            f"Rascunho automático criado: {draft_id} para processo {process_id} "
            f"(doc: {missing_doc_type}, cliente: {client_name})"
        )

        return {
            "success": True,
            "draft_id": draft_id,
            "subject": subject,
            "document_type": missing_doc_type,
            "client_name": client_name,
        }

    except Exception as e:
        logger.error(f"Erro ao criar rascunho automático: {e}", exc_info=True)
        return {"success": False, "reason": "error", "error": str(e)}


async def get_pending_drafts(
    user_id: str,
    user_role: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Obter rascunhos pendentes para o utilizador.

    Args:
        user_id: ID do utilizador
        user_role: Role do utilizador (admin/ceo veem todos)
        limit: Número máximo de resultados

    Returns:
        Lista de rascunhos pendentes
    """
    query = {
        "is_auto_draft": True,
        "status": "draft",
    }

    # Filtro por acesso - admin/ceo veem todos, outros só os seus processos
    if user_role not in ["admin", "ceo"]:
        process_ids = await db.processes.distinct(
            "id", {"assigned_to": user_id}
        )
        query["process_id"] = {"$in": process_ids}

    drafts = await db.emails.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    # Enriquecer com dados do processo/cliente
    for draft in drafts:
        if draft.get("process_id"):
            process = await db.processes.find_one(
                {"id": draft["process_id"]},
                {"_id": 0, "client_name": 1, "process_number": 1}
            )
            if process:
                draft["client_name"] = process.get("client_name", "")
                draft["process_number"] = process.get("process_number", "")

    return drafts


async def get_draft_stats(user_id: str, user_role: str) -> Dict[str, Any]:
    """
    Obter estatísticas de rascunhos pendentes.

    Returns:
        Dict com total e contagem por tipo de documento
    """
    query = {
        "is_auto_draft": True,
        "status": "draft",
    }

    if user_role not in ["admin", "ceo"]:
        process_ids = await db.processes.distinct(
            "id", {"assigned_to": user_id}
        )
        query["process_id"] = {"$in": process_ids}

    total = await db.emails.count_documents(query)

    # Agrupar por tipo de documento
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$auto_draft_doc_type",
            "count": {"$sum": 1},
            "label": {"$first": "$auto_draft_doc_label"},
        }}
    ]

    by_type = await db.emails.aggregate(pipeline).to_list(50)

    return {
        "total": total,
        "by_type": [
            {
                "doc_type": item["_id"],
                "label": item.get("label", item["_id"]),
                "count": item["count"],
            }
            for item in by_type
        ],
    }


async def update_draft(draft_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Atualizar um rascunho (editar antes de enviar).

    Args:
        draft_id: ID do rascunho
        update_data: Campos a atualizar (subject, body, to_emails)

    Returns:
        Dict com resultado
    """
    draft = await db.emails.find_one({"id": draft_id, "is_auto_draft": True})
    if not draft:
        return {"success": False, "error": "Rascunho não encontrado"}

    allowed_fields = {"subject", "body", "to_emails", "cc_emails"}
    now = datetime.now(timezone.utc)
    updates = {k: v for k, v in update_data.items() if k in allowed_fields}
    # Campos ISO string (compatibilidade)
    updates["updated_at"] = now.isoformat()
    stamp_draft_ttl_fields(updates, now=now, include_created=False)

    if updates:
        await db.emails.update_one(
            {"id": draft_id},
            {"$set": updates}
        )

    return {"success": True, "draft_id": draft_id}


async def send_draft(
    draft_id: str,
    user_id: str,
    account: str = "power",
) -> Dict[str, Any]:
    """
    Enviar um rascunho de e-mail.

    Args:
        draft_id: ID do rascunho
        user_id: ID do utilizador que envia
        account: Conta de email a usar (power/precision)

    Returns:
        Dict com resultado do envio
    """
    draft = await db.emails.find_one({"id": draft_id, "is_auto_draft": True})
    if not draft:
        return {"success": False, "error": "Rascunho não encontrado"}

    if draft.get("status") != "draft":
        return {"success": False, "error": "Rascunho já foi enviado ou descartado"}

    to_emails = draft.get("to_emails", [])
    if not to_emails:
        return {"success": False, "error": "Rascunho sem destinatário"}

    try:
        from services.email_service import send_email

        result = await send_email(
            account_name=account,
            to_emails=to_emails,
            subject=draft.get("subject", ""),
            body=draft.get("body", ""),
            process_id=draft.get("process_id"),
            created_by=user_id,
        )

        if result.get("success"):
            # Marcar rascunho como enviado
            await db.emails.update_one(
                {"id": draft_id},
                {"$set": {
                    "status": "sent",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": user_id,
                }}
            )

            logger.info(f"Rascunho {draft_id} enviado com sucesso para {to_emails}")
            return {"success": True, "draft_id": draft_id}
        else:
            return {"success": False, "error": result.get("error", "Erro ao enviar")}

    except Exception as e:
        logger.error(f"Erro ao enviar rascunho {draft_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def discard_draft(draft_id: str) -> Dict[str, Any]:
    """
    Descartar (eliminar) um rascunho.

    Args:
        draft_id: ID do rascunho

    Returns:
        Dict com resultado
    """
    result = await db.emails.delete_one({"id": draft_id, "is_auto_draft": True})

    if result.deleted_count == 0:
        return {"success": False, "error": "Rascunho não encontrado"}

    logger.info(f"Rascunho {draft_id} descartado")
    return {"success": True, "draft_id": draft_id}


async def batch_create_missing_doc_drafts(
    process_id: str,
    missing_doc_types: List[str],
    client_name: str,
    process_number: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Criar rascunhos para múltiplos documentos em falta de uma vez.

    Args:
        process_id: ID do processo
        missing_doc_types: Lista de tipos de documentos em falta
        client_name: Nome do cliente
        process_number: Número do processo

    Returns:
        Dict com resultados para cada tipo
    """
    results = {"created": [], "skipped": [], "errors": []}

    for doc_type in missing_doc_types:
        try:
            result = await create_missing_doc_draft(
                process_id=process_id,
                client_name=client_name,
                missing_doc_type=doc_type,
                process_number=process_number,
            )

            if result.get("success"):
                results["created"].append({
                    "doc_type": doc_type,
                    "draft_id": result.get("draft_id"),
                })
            elif result.get("reason") == "duplicate":
                results["skipped"].append({
                    "doc_type": doc_type,
                    "reason": "duplicado",
                    "existing_draft_id": result.get("existing_draft_id"),
                })
            else:
                results["skipped"].append({
                    "doc_type": doc_type,
                    "reason": result.get("reason", "desconhecido"),
                })
        except Exception as e:
            results["errors"].append({
                "doc_type": doc_type,
                "error": str(e),
            })

    logger.info(
        f"Batch draft creation for {process_id}: "
        f"{len(results['created'])} created, "
        f"{len(results['skipped'])} skipped, "
        f"{len(results['errors'])} errors"
    )

    return results
