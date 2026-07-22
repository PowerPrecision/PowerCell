"""CRUD de process_finances (registos financeiros de processos).

Extraído de `routes/finance.py`.
Não confundir com `services/process_finance.py` (snapshots / cálculo em processes).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from models.finance import (
    ProcessFinanceCreate,
    ProcessFinanceUpdate,
    ProcessFinanceSummary,
    FeeType,
    FinanceStatus,
)
from services.finance_helpers import _safe_float

logger = logging.getLogger(__name__)

def _doc_to_process_finance_response(doc: dict) -> dict:
    """Converte documento MongoDB para resposta ProcessFinance (remove _id).

    Garante que os campos de comissão dual estão presentes, mesmo em
    documentos antigos que não os tinham (compatibilidade retroactiva).
    """
    if doc is None:
        return {}
    doc.pop("_id", None)
    # Garantir campos de comissão dual com defaults para documentos antigos
    doc.setdefault("real_estate_base_value", 0.0)
    doc.setdefault("real_estate_fee_type", None)
    doc.setdefault("real_estate_fee_value", None)
    doc.setdefault("real_estate_commission", 0.0)
    doc.setdefault("credit_base_value", 0.0)
    doc.setdefault("credit_fee_type", None)
    doc.setdefault("credit_fee_value", None)
    doc.setdefault("credit_commission", 0.0)
    return doc



async def run_get_process_finance_summary(
    company_id: str,
    user: dict,
):
    """
    Resumo financeiro agregado dos registos ProcessFinance.

    Agrega totais por status para uma empresa.

    Permissões: todos os roles de leitura financeira.
    """
    # Pipeline de agregação por status (inclui comissões duais)
    pipeline = [
        {"$match": {"company_id": company_id}},
        {"$group": {
            "_id": "$status",
            "total_commission": {"$sum": "$expected_commission"},
            "total_with_tax": {"$sum": "$total_with_tax"},
            "total_real_estate_commission": {"$sum": {"$ifNull": ["$real_estate_commission", 0]}},
            "total_credit_commission": {"$sum": {"$ifNull": ["$credit_commission", 0]}},
            "count": {"$sum": 1},
        }},
    ]

    results = await db.process_finances.aggregate(pipeline).to_list(100)

    # Inicializar resumo com zeros
    summary = ProcessFinanceSummary()

    status_map = {
        FinanceStatus.PENDING.value: "pending",
        FinanceStatus.INVOICED.value: "invoiced",
        FinanceStatus.PAID.value: "paid",
        FinanceStatus.CANCELLED.value: "cancelled",
    }

    for row in results:
        status_key = row["_id"]
        total_commission = _safe_float(row.get("total_commission"))
        total_tax = _safe_float(row.get("total_with_tax"))
        total_re_commission = _safe_float(row.get("total_real_estate_commission"))
        total_cr_commission = _safe_float(row.get("total_credit_commission"))
        count = row.get("count", 0)

        if status_key == FinanceStatus.PENDING.value:
            summary.total_pending = round(total_commission, 2)
            summary.count_pending = count
        elif status_key == FinanceStatus.INVOICED.value:
            summary.total_invoiced = round(total_commission, 2)
            summary.count_invoiced = count
        elif status_key == FinanceStatus.PAID.value:
            summary.total_paid = round(total_commission, 2)
            summary.count_paid = count
        elif status_key == FinanceStatus.CANCELLED.value:
            summary.total_cancelled = round(total_commission, 2)
            summary.count_cancelled = count

    # Totais de registos activos (não cancelados) — inclui comissões duais
    active_statuses = FinanceStatus.active_statuses()
    active_pipeline = [
        {"$match": {"company_id": company_id, "status": {"$in": active_statuses}}},
        {"$group": {
            "_id": None,
            "total_expected": {"$sum": "$expected_commission"},
            "total_with_tax": {"$sum": "$total_with_tax"},
            "total_real_estate_commission": {"$sum": {"$ifNull": ["$real_estate_commission", 0]}},
            "total_credit_commission": {"$sum": {"$ifNull": ["$credit_commission", 0]}},
        }},
    ]
    active_results = await db.process_finances.aggregate(active_pipeline).to_list(1)

    if active_results:
        summary.total_expected = round(_safe_float(active_results[0].get("total_expected")), 2)
        summary.total_with_tax = round(_safe_float(active_results[0].get("total_with_tax")), 2)
        summary.total_real_estate_commission = round(_safe_float(active_results[0].get("total_real_estate_commission")), 2)
        summary.total_credit_commission = round(_safe_float(active_results[0].get("total_credit_commission")), 2)

    return summary.model_dump()



async def run_create_process_finance(
    body: ProcessFinanceCreate,
    user: dict,
):
    """
    Cria um registo financeiro para um processo.

    Calcula automaticamente expected_commission, tax_amount e total_with_tax
    usando ProcessFinanceCreate.compute_finance(), a menos que os valores
    sejam fornecidos explicitamente.

    Permissões: Admin, CEO e Diretor.
    """
    # Verificar se já existe registo financeiro para este processo
    existing = await db.process_finances.find_one({
        "process_id": body.process_id,
        "company_id": body.company_id,
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um registo financeiro para o processo '{body.process_id}' "
                   f"na empresa '{body.company_id}'.",
        )

    # Calcular valores financeiros automáticos (inclui comissões duais)
    computed = body.compute_finance()

    finance_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": finance_id,
        "process_id": body.process_id,
        "client_id": body.client_id,
        "company_id": body.company_id,
        # Campos legacy (comissão única — compatibilidade retroactiva)
        "base_business_value": body.base_business_value,
        "applied_fee_type": body.applied_fee_type,
        "applied_fee_value": body.applied_fee_value,
        # Comissão Imobiliária (Real Estate)
        "real_estate_base_value": body.real_estate_base_value or 0.0,
        "real_estate_fee_type": body.real_estate_fee_type,
        "real_estate_fee_value": body.real_estate_fee_value,
        "real_estate_commission": computed.get("real_estate_commission", 0.0),
        # Comissão de Crédito (Credit)
        "credit_base_value": body.credit_base_value or body.base_business_value or 0.0,
        "credit_fee_type": body.credit_fee_type or body.applied_fee_type,
        "credit_fee_value": body.credit_fee_value or body.applied_fee_value,
        "credit_commission": computed.get("credit_commission", 0.0),
        # Totais
        "expected_commission": computed["expected_commission"],
        "tax_amount": computed["tax_amount"],
        "total_with_tax": computed["total_with_tax"],
        "status": body.status or FinanceStatus.PENDING.value,
        "invoice_link": body.invoice_link,
        "created_at": now,
        "updated_at": now,
    }

    await db.process_finances.insert_one(doc)

    logger.info(
        f"ProcessFinance criado: id={finance_id}, process_id={body.process_id}, "
        f"company_id={body.company_id}, commission={computed['expected_commission']}, "
        f"re_commission={computed.get('real_estate_commission', 0.0)}, "
        f"cr_commission={computed.get('credit_commission', 0.0)}, "
        f"por {user.get('email', 'unknown')}"
    )

    return _doc_to_process_finance_response(doc)



async def run_list_process_finances(
    company_id: Optional[str],
    process_id: Optional[str],
    client_id: Optional[str],
    status: Optional[str],
    user: dict,
):
    """
    Lista registos financeiros de processos, com filtros opcionais.

    Filtros disponíveis: company_id, process_id, client_id, status.

    Permissões: todos os roles de leitura financeira.
    """
    query = {}
    if company_id:
        query["company_id"] = company_id
    if process_id:
        query["process_id"] = process_id
    if client_id:
        query["client_id"] = client_id
    if status:
        if status not in FinanceStatus.all_values():
            raise HTTPException(
                status_code=400,
                detail=f"Status inválido: '{status}'. Valores permitidos: {FinanceStatus.all_values()}",
            )
        query["status"] = status

    finances = await db.process_finances.find(query, {"_id": 0}).to_list(1000)
    return {"finances": finances, "total": len(finances)}



async def run_get_process_finance_by_id(
    finance_id: str,
    user: dict,
):
    """
    Obtém um registo financeiro de processo específico por ID.

    Permissões: todos os roles de leitura financeira.
    """
    doc = await db.process_finances.find_one({"id": finance_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Registo financeiro não encontrado")
    return doc



async def run_update_process_finance(
    finance_id: str,
    body: ProcessFinanceUpdate,
    user: dict,
):
    """
    Actualiza um registo financeiro de processo.

    Apenas os campos fornecidos no body serão actualizados.
    Se campos financeiros forem alterados, recalcular valores derivados.

    Permissões: Admin, CEO e Diretor.
    """
    existing = await db.process_finances.find_one({"id": finance_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registo financeiro não encontrado")

    update_fields = body.model_dump(exclude_none=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo fornecido para actualização")

    # Se campos de comissão dual foram alterados, recalcular comissão total e impostos
    dual_commission_fields_changed = any(
        f in update_fields
        for f in [
            "real_estate_base_value", "real_estate_fee_type", "real_estate_fee_value", "real_estate_commission",
            "credit_base_value", "credit_fee_type", "credit_fee_value", "credit_commission",
        ]
    )

    # Se campos financeiros legacy foram alterados, recalcular (compatibilidade retroactiva)
    financial_fields_changed = any(
        f in update_fields
        for f in ["base_business_value", "applied_fee_type", "applied_fee_value"]
    )

    if dual_commission_fields_changed:
        # Obter valores actuais + updates para recalcular comissão imobiliária
        re_base = _safe_float(update_fields.get("real_estate_base_value", existing.get("real_estate_base_value", 0.0)))
        re_fee_type = update_fields.get("real_estate_fee_type", existing.get("real_estate_fee_type"))
        re_fee_value = _safe_float(update_fields.get("real_estate_fee_value", existing.get("real_estate_fee_value", 0.0)))

        # Recalcular comissão imobiliária
        if "real_estate_commission" not in update_fields:
            if re_fee_type == FeeType.PERCENTAGE.value:
                update_fields["real_estate_commission"] = round(re_base * (re_fee_value / 100), 2)
            elif re_fee_type == FeeType.FIXED.value:
                update_fields["real_estate_commission"] = re_fee_value
            # Se não houver fee_type, manter o valor existente

        # Obter valores actuais + updates para recalcular comissão de crédito
        cr_base = _safe_float(update_fields.get("credit_base_value", existing.get("credit_base_value", 0.0)))
        cr_fee_type = update_fields.get("credit_fee_type", existing.get("credit_fee_type"))
        cr_fee_value = _safe_float(update_fields.get("credit_fee_value", existing.get("credit_fee_value", 0.0)))

        # Recalcular comissão de crédito
        if "credit_commission" not in update_fields:
            if cr_fee_type == FeeType.PERCENTAGE.value:
                update_fields["credit_commission"] = round(cr_base * (cr_fee_value / 100), 2)
            elif cr_fee_type == FeeType.FIXED.value:
                update_fields["credit_commission"] = cr_fee_value
            # Se não houver fee_type, manter o valor existente

        # Recalcular expected_commission = real_estate_commission + credit_commission
        re_commission = _safe_float(update_fields.get("real_estate_commission", existing.get("real_estate_commission", 0.0)))
        cr_commission = _safe_float(update_fields.get("credit_commission", existing.get("credit_commission", 0.0)))
        expected_commission = round(re_commission + cr_commission, 2)

        if "expected_commission" not in update_fields:
            update_fields["expected_commission"] = expected_commission

        # Recalcular tax_amount e total_with_tax
        tax_rate = _safe_float(existing.get("tax_rate", 23.0))
        ec = update_fields.get("expected_commission", expected_commission)
        if "tax_amount" not in update_fields:
            update_fields["tax_amount"] = round(_safe_float(ec) * (tax_rate / 100), 2)
        if "total_with_tax" not in update_fields:
            ta = update_fields.get("tax_amount", update_fields["tax_amount"])
            update_fields["total_with_tax"] = round(_safe_float(ec) + _safe_float(ta), 2)

    elif financial_fields_changed:
        # Compatibilidade retroactiva: recalcular usando lógica legacy
        base = _safe_float(update_fields.get("base_business_value", existing.get("base_business_value")))
        fee_type = update_fields.get("applied_fee_type", existing.get("applied_fee_type"))
        fee_value = _safe_float(update_fields.get("applied_fee_value", existing.get("applied_fee_value")))
        tax_rate = _safe_float(existing.get("tax_rate", 23.0))

        # Recalcular expected_commission
        if fee_type == FeeType.PERCENTAGE.value:
            expected_commission = round(base * (fee_value / 100), 2)
        else:
            expected_commission = fee_value

        # Recalcular tax_amount e total_with_tax (se não fornecidos explicitamente)
        if "expected_commission" not in update_fields:
            update_fields["expected_commission"] = expected_commission
        if "tax_amount" not in update_fields:
            update_fields["tax_amount"] = round(update_fields.get("expected_commission", expected_commission) * (tax_rate / 100), 2)
        if "total_with_tax" not in update_fields:
            ec = update_fields.get("expected_commission", expected_commission)
            ta = update_fields.get("tax_amount", update_fields["tax_amount"])
            update_fields["total_with_tax"] = round(ec + ta, 2)

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.process_finances.update_one(
        {"id": finance_id},
        {"$set": update_fields},
    )

    # Buscar documento actualizado
    updated = await db.process_finances.find_one({"id": finance_id}, {"_id": 0})

    logger.info(
        f"ProcessFinance actualizado: id={finance_id}, campos={list(update_fields.keys())}, "
        f"por {user.get('email', 'unknown')}"
    )

    return updated



async def run_update_process_finance_status(
    finance_id: str,
    status: str,
    user: dict,
):
    """
    Actualiza apenas o status de um registo financeiro.

    Útil para marcações rápidas (ex: marcar como pago).

    Permissões: Admin, CEO e Diretor.
    """
    if status not in FinanceStatus.all_values():
        raise HTTPException(
            status_code=400,
            detail=f"Status inválido: '{status}'. Valores permitidos: {FinanceStatus.all_values()}",
        )

    existing = await db.process_finances.find_one({"id": finance_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registo financeiro não encontrado")

    now = datetime.now(timezone.utc).isoformat()
    await db.process_finances.update_one(
        {"id": finance_id},
        {"$set": {"status": status, "updated_at": now}},
    )

    logger.info(
        f"ProcessFinance status actualizado: id={finance_id}, "
        f"status={existing.get('status')} → {status}, "
        f"por {user.get('email', 'unknown')}"
    )

    return {
        "id": finance_id,
        "previous_status": existing.get("status"),
        "new_status": status,
        "updated_at": now,
    }



async def run_delete_process_finance(
    finance_id: str,
    user: dict,
):
    """
    Elimina um registo financeiro de processo.

    Permissões: apenas Admin e CEO.
    """
    existing = await db.process_finances.find_one({"id": finance_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Registo financeiro não encontrado")

    await db.process_finances.delete_one({"id": finance_id})

    logger.info(
        f"ProcessFinance eliminado: id={finance_id}, process_id={existing.get('process_id')}, "
        f"company_id={existing.get('company_id')}, por {user.get('email', 'unknown')}"
    )

    return {"success": True, "message": "Registo financeiro eliminado com sucesso"}

