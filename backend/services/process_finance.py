"""
====================================================================
SERVIÇO DE SNAPSHOT FINANCEIRO DE PROCESSOS - CREDITOIMO
====================================================================
Cria e sincroniza ProcessFinance quando um processo é concluído
ou quando valores financeiros são editados retroativamente.

Extraído de routes/processes.py para aliviar o módulo de rotas
e permitir testes unitários da matemática de comissões.
====================================================================
"""
import uuid
import logging
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)


def _resolve_fee_inputs(process: dict, company_id: str, config_doc: dict | None):
    """
    Resolve valores base e fee types a partir do processo e FinanceConfig.

    Returns:
        dict com re_*/cr_* bases, fees, tax_rate e campos legacy.
    """
    real_estate_data = process.get("real_estate_data") or {}
    credit_data = process.get("credit_data") or {}
    financial_data = process.get("financial_data") or {}

    valor_imovel = real_estate_data.get("valor_imovel")
    loan_amount = credit_data.get("loan_amount") or credit_data.get("requested_amount")

    re_base_value = float(valor_imovel) if valor_imovel else 0.0
    cr_base_value = float(loan_amount) if loan_amount else 0.0
    re_fee_type = None
    re_fee_value = None
    cr_fee_type = None
    cr_fee_value = None
    base_business_value = 0.0
    applied_fee_type = None
    applied_fee_value = None
    tax_rate = 23.0  # IVA português por defeito

    if config_doc:
        fee_type = config_doc.get("fee_type", "percentage")
        default_value = config_doc.get("default_value", 0.0)
        tax_rate = config_doc.get("tax_rate", 23.0)

        re_fee_type = config_doc.get("real_estate_fee_type") or fee_type
        re_fee_value = (
            config_doc.get("real_estate_fee_value")
            or config_doc.get("real_estate_default_value")
            or default_value
        )
        cr_fee_type = config_doc.get("credit_fee_type") or fee_type
        cr_fee_value = (
            config_doc.get("credit_fee_value")
            or config_doc.get("credit_default_value")
            or default_value
        )

        applied_fee_type = fee_type
        applied_fee_value = default_value
        base_business_value = cr_base_value or re_base_value
    else:
        comissao_mediacao = financial_data.get("comissao_mediacao")
        if comissao_mediacao:
            cr_base_value = float(comissao_mediacao)
            cr_fee_type = "fixed"
            cr_fee_value = float(comissao_mediacao)
            applied_fee_type = "fixed"
            applied_fee_value = float(comissao_mediacao)
            base_business_value = float(comissao_mediacao)
        else:
            logger.info(
                f"Sem FinanceConfig nem comissão para processo "
                f"{process.get('id', '')}. Snapshot com valores zero."
            )

    return {
        "re_base_value": re_base_value,
        "cr_base_value": cr_base_value,
        "re_fee_type": re_fee_type,
        "re_fee_value": re_fee_value,
        "cr_fee_type": cr_fee_type,
        "cr_fee_value": cr_fee_value,
        "base_business_value": base_business_value,
        "applied_fee_type": applied_fee_type,
        "applied_fee_value": applied_fee_value,
        "tax_rate": tax_rate,
    }


def _calculate_commissions(fee_inputs: dict) -> dict:
    """Calcula comissões imobiliária/crédito e totais com IVA."""
    from models.finance import FeeType

    re_base_value = fee_inputs["re_base_value"]
    re_fee_type = fee_inputs["re_fee_type"]
    re_fee_value = fee_inputs["re_fee_value"]
    cr_base_value = fee_inputs["cr_base_value"]
    cr_fee_type = fee_inputs["cr_fee_type"]
    cr_fee_value = fee_inputs["cr_fee_value"]
    tax_rate = fee_inputs["tax_rate"]

    if re_fee_type == FeeType.PERCENTAGE.value:
        re_commission = (
            round(re_base_value * (re_fee_value / 100), 2)
            if re_base_value and re_fee_value
            else 0.0
        )
    elif re_fee_type == FeeType.FIXED.value:
        re_commission = re_fee_value or 0.0
    else:
        re_commission = 0.0

    if cr_fee_type == FeeType.PERCENTAGE.value:
        cr_commission = (
            round(cr_base_value * (cr_fee_value / 100), 2)
            if cr_base_value and cr_fee_value
            else 0.0
        )
    elif cr_fee_type == FeeType.FIXED.value:
        cr_commission = cr_fee_value or 0.0
    else:
        cr_commission = 0.0

    expected_commission = round(re_commission + cr_commission, 2)
    tax_amount = round(expected_commission * (tax_rate / 100), 2)
    total_with_tax = round(expected_commission + tax_amount, 2)

    return {
        "re_commission": re_commission,
        "cr_commission": cr_commission,
        "expected_commission": expected_commission,
        "tax_amount": tax_amount,
        "total_with_tax": total_with_tax,
    }


async def create_finance_snapshot(process: dict, user: dict):
    """
    Cria um snapshot financeiro (ProcessFinance) quando um processo é concluído.

    Lê dados de real_estate_data (valor_imovel) e credit_data (loan_amount)
    para calcular comissões duais (Imobiliária + Crédito) de forma independente.

    Usa a FinanceConfig da empresa para determinar fee_type/fee_value.
    Se a empresa tiver configs separadas para imobiliária e crédito, usa-as;
    caso contrário, usa a mesma config para ambas.

    Compatibilidade retroactiva:
    - Se não houver FinanceConfig para a empresa, usa os campos legacy
      (base_business_value + applied_fee_type/value) se disponíveis.
    - Se já existir um registo financeiro para este processo, ignora silenciosamente.
    """
    from models.finance import FinanceStatus

    process_id = process.get("id", "")
    company_id = process.get("company_id", "")
    client_id = process.get("client_id", "")

    existing = await db.process_finances.find_one({
        "process_id": process_id,
        "company_id": company_id,
    })
    if existing:
        logger.info(f"Snapshot financeiro já existe para processo {process_id}, a ignorar")
        return

    config_doc = await db.finance_configs.find_one({"company_id": company_id})
    fee_inputs = _resolve_fee_inputs(process, company_id, config_doc)
    commissions = _calculate_commissions(fee_inputs)

    finance_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": finance_id,
        "process_id": process_id,
        "client_id": client_id,
        "company_id": company_id,
        "base_business_value": fee_inputs["base_business_value"],
        "applied_fee_type": fee_inputs["applied_fee_type"],
        "applied_fee_value": fee_inputs["applied_fee_value"],
        "real_estate_base_value": fee_inputs["re_base_value"],
        "real_estate_fee_type": fee_inputs["re_fee_type"],
        "real_estate_fee_value": fee_inputs["re_fee_value"],
        "real_estate_commission": commissions["re_commission"],
        "credit_base_value": fee_inputs["cr_base_value"],
        "credit_fee_type": fee_inputs["cr_fee_type"],
        "credit_fee_value": fee_inputs["cr_fee_value"],
        "credit_commission": commissions["cr_commission"],
        "expected_commission": commissions["expected_commission"],
        "tax_amount": commissions["tax_amount"],
        "total_with_tax": commissions["total_with_tax"],
        "status": FinanceStatus.PENDING.value,
        "invoice_link": None,
        "created_at": now,
        "updated_at": now,
    }

    await db.process_finances.insert_one(doc)

    logger.info(
        f"Snapshot financeiro criado: id={finance_id}, process_id={process_id}, "
        f"re_commission={commissions['re_commission']}, "
        f"cr_commission={commissions['cr_commission']}, "
        f"total={commissions['expected_commission']}"
    )


async def ensure_finance_snapshot(process: dict, user: dict):
    """
    Garante que existe um snapshot financeiro (ProcessFinance) para o processo,
    criando um novo se não existir ou atualizando os valores base se já existir.

    Usado na Sincronização Financeira Retroativa: quando um admin/CEO edita
    um processo concluído/escritura, os valores financeiros (valor_imovel,
    loan_amount) podem ter mudado, e o snapshot precisa de ser recalculado.
    """
    process_id = process.get("id", "")
    company_id = process.get("company_id", "")

    existing = await db.process_finances.find_one({
        "process_id": process_id,
        "company_id": company_id,
    })

    if not existing:
        logger.info(
            f"Nenhum snapshot financeiro encontrado para processo {process_id}. A criar novo."
        )
        await create_finance_snapshot(process, user)
        return

    config_doc = await db.finance_configs.find_one({"company_id": company_id})
    fee_inputs = _resolve_fee_inputs(process, company_id, config_doc)
    commissions = _calculate_commissions(fee_inputs)

    update_fields = {
        "real_estate_base_value": fee_inputs["re_base_value"],
        "real_estate_fee_type": fee_inputs["re_fee_type"],
        "real_estate_fee_value": fee_inputs["re_fee_value"],
        "real_estate_commission": commissions["re_commission"],
        "credit_base_value": fee_inputs["cr_base_value"],
        "credit_fee_type": fee_inputs["cr_fee_type"],
        "credit_fee_value": fee_inputs["cr_fee_value"],
        "credit_commission": commissions["cr_commission"],
        "expected_commission": commissions["expected_commission"],
        "tax_amount": commissions["tax_amount"],
        "total_with_tax": commissions["total_with_tax"],
        "base_business_value": fee_inputs["base_business_value"],
        "applied_fee_type": fee_inputs["applied_fee_type"],
        "applied_fee_value": fee_inputs["applied_fee_value"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.process_finances.update_one(
        {"id": existing["id"]},
        {"$set": update_fields}
    )

    logger.info(
        f"Snapshot financeiro atualizado retroativamente: process_id={process_id}, "
        f"re_commission={commissions['re_commission']}, "
        f"cr_commission={commissions['cr_commission']}, "
        f"total={commissions['expected_commission']}, "
        f"updated_by={user.get('email', 'unknown')}"
    )
