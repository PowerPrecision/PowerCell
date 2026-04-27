"""
Serviço de Audit Trail - Registo detalhado de alterações no sistema.
Captura IP, origem da alteração, aprovações de IA e justificações.
"""
import uuid
import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import db

logger = logging.getLogger(__name__)


async def check_audit_enabled() -> bool:
    """Verificar se o sistema de auditoria está activo via configuração."""
    try:
        config_doc = await db.system_config.find_one({"_id": "main"})
        if config_doc:
            audit_cfg = config_doc.get("audit_trail", {})
            return audit_cfg.get("enabled", True)
    except Exception:
        pass
    return True  # Activar por defeito


async def get_audit_config() -> Dict[str, Any]:
    """Obter configuração actual do audit trail."""
    try:
        config_doc = await db.system_config.find_one({"_id": "main"})
        if config_doc:
            return config_doc.get("audit_trail", {
                "enabled": True,
                "log_ip_address": True,
                "log_ai_approvals": True,
                "require_reason_for_critical_fields": True,
                "critical_fields": ["financial_data", "credit_data", "status"],
                "retention_days": 365,
            })
    except Exception:
        pass
    return {
        "enabled": True,
        "log_ip_address": True,
        "log_ai_approvals": True,
        "require_reason_for_critical_fields": True,
        "critical_fields": ["financial_data", "credit_data", "status"],
        "retention_days": 365,
    }


async def log_audit_event(
    process_id: str,
    user: dict,
    action: str,
    field: str = None,
    old_value: Any = None,
    new_value: Any = None,
    request: Any = None,
    source: str = "web",
    audit_reason: str = None,
    ai_suggested: bool = False,
    ai_approved_by: str = None,
    metadata: dict = None,
) -> Optional[str]:
    """
    Registar um evento de auditoria com dados enriquecidos.
    
    Args:
        process_id: ID do processo afectado
        user: Dicionário do utilizador autenticado
        action: Descrição da acção realizada
        field: Campo alterado (opcional)
        old_value: Valor anterior do campo
        new_value: Novo valor do campo
        request: Objecto Request do FastAPI (para extrair IP)
        source: Origem da alteração (web, api, ai_automation, email)
        audit_reason: Justificação opcional para a alteração
        ai_suggested: Se a alteração foi sugerida por IA
        ai_approved_by: ID do utilizador que aprovou a sugestão de IA
        metadata: Dicionário com contexto extra
    
    Returns:
        ID do registo criado ou None em caso de erro
    """
    if not await check_audit_enabled():
        return None

    try:
        config = await get_audit_config()

        # Extrair IP do request (se configurado e disponível)
        ip_address = None
        if config.get("log_ip_address", True) and request:
            ip_address = (
                request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or request.headers.get("X-Real-IP")
                or (request.client.host if request.client else None)
            )

        audit_doc = {
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "user_id": user.get("id") if user else None,
            "user_name": user.get("name") if user else "Sistema",
            "user_email": user.get("email") if user else None,
            "user_role": user.get("role") if user else None,
            "action": action,
            "field": field,
            "old_value": str(old_value) if old_value is not None else None,
            "new_value": str(new_value) if new_value is not None else None,
            "ip_address": ip_address,
            "source": source,
            "audit_reason": audit_reason,
            "ai_suggested": ai_suggested,
            "ai_approved_by": ai_approved_by,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await db.audit_trail.insert_one(audit_doc)
        logger.debug(f"Audit trail registado: {action} - {field} por {audit_doc['user_name']}")
        return audit_doc["id"]

    except Exception as e:
        # Não falhar a operação principal se o registo de auditoria falhar
        logger.warning(f"Erro ao registar audit trail: {e}")
        return None


async def log_ai_approval(
    process_id: str,
    user: dict,
    suggestion_type: str,
    field: str,
    suggested_value: Any,
    approved: bool,
    approval_reason: str = None,
    request: Any = None,
    metadata: dict = None,
) -> Optional[str]:
    """
    Registar aprovação/rejeição de sugestão de IA.
    
    Args:
        process_id: ID do processo
        user: Utilizador que aprovou/rejeitou
        suggestion_type: Tipo de sugestão (ex: document_analysis, field_suggestion)
        field: Campo sugerido
        suggested_value: Valor sugerido pela IA
        approved: Se foi aprovado (True) ou rejeitado (False)
        approval_reason: Motivo da decisão
        request: Objecto Request do FastAPI
        metadata: Contexto extra
    
    Returns:
        ID do registo criado
    """
    if not await check_audit_enabled():
        return None

    action = f"Aprovou sugestão IA ({suggestion_type})" if approved else f"Rejeitou sugestão IA ({suggestion_type})"

    return await log_audit_event(
        process_id=process_id,
        user=user,
        action=action,
        field=field,
        old_value=None,
        new_value=str(suggested_value) if suggested_value else None,
        request=request,
        source="web",
        audit_reason=approval_reason,
        ai_suggested=True,
        ai_approved_by=user.get("id") if user and approved else None,
        metadata=metadata,
    )


async def get_audit_trail(
    process_id: str = None,
    user_id: str = None,
    action_type: str = None,
    source: str = None,
    date_from: str = None,
    date_to: str = None,
    ai_suggested: bool = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """
    Consultar registos de auditoria com filtros e paginação.
    
    Args:
        process_id: Filtrar por processo
        user_id: Filtrar por utilizador
        action_type: Filtrar por tipo de acção (texto parcial)
        source: Filtrar por origem (web, api, ai_automation, email)
        date_from: Data inicial (ISO 8601)
        date_to: Data final (ISO 8601)
        ai_suggested: Filtrar apenas alterações sugeridas por IA
        page: Número da página (1-based)
        page_size: Tamanho da página
    
    Returns:
        Dicionário com items, total, page, page_size
    """
    query = {}

    if process_id:
        query["process_id"] = process_id
    if user_id:
        query["user_id"] = user_id
    if action_type:
        query["action"] = {"$regex": action_type, "$options": "i"}
    if source:
        query["source"] = source
    if ai_suggested is not None:
        query["ai_suggested"] = ai_suggested
    if date_from or date_to:
        date_filter = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        query["created_at"] = date_filter

    skip = (page - 1) * page_size

    total = await db.audit_trail.count_documents(query)
    items = await db.audit_trail.find(query).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)

    # Converter ObjectId para string e limpar dados sensíveis
    for item in items:
        item.pop("_id", None)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


async def get_audit_stats() -> Dict[str, Any]:
    """
    Obter estatísticas de auditoria para o dashboard.
    
    Returns:
        Dicionário com diversas métricas agregadas
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Total de alterações hoje
    total_today = await db.audit_trail.count_documents({"created_at": {"$gte": today_start}})

    # Total de alterações esta semana
    total_week = await db.audit_trail.count_documents({"created_at": {"$gte": week_start}})

    # Aprovações de IA (total e esta semana)
    ai_approvals_total = await db.audit_trail.count_documents({"ai_suggested": True})
    ai_approvals_week = await db.audit_trail.count_documents({
        "ai_suggested": True,
        "created_at": {"$gte": week_start},
    })

    # Alterações de campos críticos esta semana
    config = await get_audit_config()
    critical_fields = config.get("critical_fields", ["financial_data", "credit_data", "status"])

    critical_changes_week = await db.audit_trail.count_documents({
        "field": {"$in": critical_fields},
        "created_at": {"$gte": week_start},
    })

    # Alterações por utilizador (top 10 esta semana)
    pipeline_users = [
        {"$match": {"created_at": {"$gte": week_start}}},
        {"$group": {"_id": "$user_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    changes_by_user = await db.audit_trail.aggregate(pipeline_users).to_list(10)

    # Alterações por dia (últimos 7 dias)
    pipeline_daily = [
        {"$match": {"created_at": {"$gte": week_start}}},
        {"$group": {
            "_id": {"$dateFromString": {"dateString": "$created_at"}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    changes_by_day = await db.audit_trail.aggregate(pipeline_daily).to_list(10)

    # Campos mais alterados (últimos 7 dias)
    pipeline_fields = [
        {"$match": {"created_at": {"$gte": week_start}, "field": {"$ne": None}}},
        {"$group": {"_id": "$field", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    most_changed_fields = await db.audit_trail.aggregate(pipeline_fields).to_list(10)

    # Alterações por origem (últimos 7 dias)
    pipeline_source = [
        {"$match": {"created_at": {"$gte": week_start}}},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    changes_by_source = await db.audit_trail.aggregate(pipeline_source).to_list(10)

    # Formatar datas para ISO string
    for day in changes_by_day:
        day["date"] = day.pop("_id").strftime("%Y-%m-%d") if hasattr(day["_id"], "strftime") else str(day["_id"])[:10]

    return {
        "total_today": total_today,
        "total_week": total_week,
        "ai_approvals_total": ai_approvals_total,
        "ai_approvals_week": ai_approvals_week,
        "critical_changes_week": critical_changes_week,
        "changes_by_user": [{"user": u["_id"], "count": u["count"]} for u in changes_by_user],
        "changes_by_day": changes_by_day,
        "most_changed_fields": [{"field": f["_id"], "count": f["count"]} for f in most_changed_fields],
        "changes_by_source": [{"source": s["_id"], "count": s["count"]} for s in changes_by_source],
    }


async def export_audit_trail(
    process_id: str = None,
    user_id: str = None,
    source: str = None,
    date_from: str = None,
    date_to: str = None,
) -> str:
    """
    Exportar registos de auditoria para CSV.
    
    Returns:
        Conteúdo CSV como string
    """
    result = await get_audit_trail(
        process_id=process_id,
        user_id=user_id,
        source=source,
        date_from=date_from,
        date_to=date_to,
        page=1,
        page_size=10000,  # Máximo 10.000 registos
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Cabeçalho
    writer.writerow([
        "Data/Hora", "Utilizador", "Email", "Função", "Acção",
        "Campo", "Valor Anterior", "Novo Valor", "Origem",
        "Endereço IP", "Justificação", "Sugerido por IA",
        "Aprovado por", "ID Processo",
    ])

    # Dados
    for item in result.get("items", []):
        writer.writerow([
            item.get("created_at", ""),
            item.get("user_name", ""),
            item.get("user_email", ""),
            item.get("user_role", ""),
            item.get("action", ""),
            item.get("field", ""),
            item.get("old_value", ""),
            item.get("new_value", ""),
            item.get("source", ""),
            item.get("ip_address", ""),
            item.get("audit_reason", ""),
            "Sim" if item.get("ai_suggested") else "Não",
            item.get("ai_approved_by", ""),
            item.get("process_id", ""),
        ])

    return output.getvalue()


async def cleanup_old_records(days: int = None) -> int:
    """
    Eliminar registos de auditoria mais antigos que o período de retenção.
    
    Args:
        days: Número de dias de retenção (usa config se não especificado)
    
    Returns:
        Número de registos eliminados
    """
    if days is None:
        config = await get_audit_config()
        days = config.get("retention_days", 365)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    result = await db.audit_trail.delete_many({"created_at": {"$lt": cutoff_iso}})
    deleted_count = result.deleted_count

    if deleted_count > 0:
        logger.info(f"Cleanup de audit trail: {deleted_count} registos eliminados (anteriores a {cutoff_iso})")

    return deleted_count
