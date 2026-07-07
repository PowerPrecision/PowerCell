"""
SERVIÇO DE ONBOARDING — Validação e Criação Automática de Processos
===================================================================

Motor de validação (Event-Driven) para onboarding de novos clientes.

Quando um cliente faz upload de documentos pelo Portal, este serviço
verifica se todos os documentos obrigatórios foram submetidos. Se sim,
cria automaticamente um Process e ancora os documentos no processo.

Regras de Validação (Regra de Ouro):
- tipo_contrato "Efetivo" ou "Termo Certo":
  → Precisa de: Cartão de Cidadão, Extratos, Recibos, Declaração Patronal
- Qualquer outro tipo de contrato (ou sem tipo):
  → Precisa de: Cartão de Cidadão, Extratos

Mapeamento de Categorias:
- "Cartão de Cidadão" → Cartao_Cidadao
- "Extratos"          → Comprovativo_IBAN, extrato_bancario, Financeiros
- "Recibos"           → Recibo_Vencimento, IRS
- "Declaração Patronal" → Atestado_Trabalho, Declaracao_Imposto_Renda

Gatilho: Após confirm-upload no Portal (POST /portal/confirm-upload)
"""
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from database import db

logger = logging.getLogger(__name__)


# ====================================================================
# MAPEAMENTO DE CATEGORIAS — O que conta como cada documento obrigatório
# ====================================================================

# Cada "grupo obrigatório" mapeia para uma lista de categorias na BD
# que satisfazem esse requisito. Qualquer uma delas conta como preenchida.
DOCUMENT_REQUIREMENT_MAP = {
    "Cartão de Cidadão": [
        "Cartao_Cidadao",
        "cartao_cidadao",
        "CC",
    ],
    "Extratos": [
        "Comprovativo_IBAN",
        "comprovativo_iban",
        "extrato_bancario",
        "Financeiros",
        "financeiros",
    ],
    "Recibos": [
        "Recibo_Vencimento",
        "recibo_vencimento",
        "IRS",
        "irs",
    ],
    "Declaração Patronal": [
        "Atestado_Trabalho",
        "atestado_trabalho",
        "Declaracao_Imposto_Renda",
        "declaracao_imposto_renda",
    ],
}

# Categorias exigidas por tipo de contrato
REQUIREMENTS_BY_CONTRACT_TYPE = {
    "efetivo": ["Cartão de Cidadão", "Extratos", "Recibos", "Declaração Patronal"],
    "termo_certo": ["Cartão de Cidadão", "Extratos", "Recibos", "Declaração Patronal"],
    "cdi": ["Cartão de Cidadão", "Extratos", "Recibos", "Declaração Patronal"],
    "cdd": ["Cartão de Cidadão", "Extratos", "Recibos", "Declaração Patronal"],
    "termo": ["Cartão de Cidadão", "Extratos", "Recibos", "Declaração Patronal"],
    # Default: outros tipos ou sem tipo
    "default": ["Cartão de Cidadão", "Extratos"],
}

# Normalizações para comparação case-insensitive
CONTRACT_TYPE_NORMALIZE = {
    "efetivo": "efetivo",
    "termo_certo": "termo_certo",
    "termo certo": "termo_certo",
    "cdi": "cdi",
    "cdd": "cdd",
    "contrato a termo": "termo_certo",
    "termo resolutivo": "termo_certo",
    "termo indeterminado": "efetivo",
    "sem termo": "efetivo",
    "permanente": "efetivo",
    "permanent": "efetivo",
}


# ====================================================================
# FUNÇÃO PRINCIPAL — Verificar e completar onboarding
# ====================================================================

async def check_onboarding_completion(client_id: str) -> Dict[str, Any]:
    """
    Verifica se o cliente completou o onboarding de documentos e,
    se sim, cria automaticamente um Process e ancora os documentos.

    Fluxo:
    1. Buscar o cliente e os seus documentos sem processo (process_id NULL)
    2. Determinar o tipo de contrato (do último documento ou do cliente)
    3. Verificar quais grupos obrigatórios estão satisfeitos
    4. Se todos satisfeitos (Semáforo Verde):
       a) Criar um novo Process para este cliente
       b) Ancorar todos os documentos (definir process_id)
       c) Retornar sucesso com dados do processo criado
    5. Se não, retornar estado actual (quais faltam)

    Args:
        client_id: ID do cliente (UUID string)

    Returns:
        Dict com:
        - completed: bool — se o onboarding está completo
        - process_id: str | None — ID do processo criado (ou None)
        - missing: list — grupos de documentos em falta
        - satisfied: list — grupos de documentos satisfeitos
        - contract_type: str — tipo de contrato detectado
    """
    # ── 1. Buscar cliente ──
    client = await db.clients.find_one({"id": client_id})
    if not client:
        logger.warning(f"[ONBOARDING] Cliente não encontrado: {client_id}")
        return {
            "completed": False,
            "process_id": None,
            "missing": [],
            "satisfied": [],
            "contract_type": "unknown",
            "error": "Cliente não encontrado",
        }

    # ── 2. Buscar documentos do cliente sem processo ──
    # Critério: documentos que pertencem a este cliente e:
    #   - Não têm process_id (órfãos)
    #   - OU têm process_id mas o processo não existe (órfãos de processo eliminado)
    # Também considerar documentos com status RECEIVED (não pendentes)
    orphan_docs_cursor = db.documents.find(
        {
            "$or": [
                {"process_id": None},
                {"process_id": ""},
                {"process_id": {"$exists": False}},
            ],
            "source": "client_portal",
            "status": {"$in": ["RECEIVED", "UPLOADED", "SUBMITTED", "received", "uploaded", "submitted"]},
        }
    )

    # Filtro adicional: se o documento tem client_id associado, deve ser deste cliente
    # Como documentos órfãos podem não ter client_id, verificamos por outras formas
    orphan_docs = []
    async for doc in orphan_docs_cursor:
        # Verificar se o documento pertence a este cliente
        # (por client_id directo ou por S3 path que contenha o client_id)
        doc_client_id = doc.get("client_id")
        s3_path = doc.get("s3_path", "")
        if doc_client_id == client_id:
            orphan_docs.append(doc)
        elif client_id in s3_path:
            orphan_docs.append(doc)
        elif not doc_client_id and not s3_path:
            # Sem forma de determinar o dono — ignorar por segurança
            pass

    # Se não há documentos órfãos, não há nada para validar
    if not orphan_docs:
        return {
            "completed": False,
            "process_id": None,
            "missing": _get_required_groups("default"),
            "satisfied": [],
            "contract_type": "default",
            "orphan_docs_count": 0,
        }

    # ── 3. Determinar tipo de contrato ──
    contract_type = await _detect_contract_type(client_id, client, orphan_docs)
    normalized_contract = CONTRACT_TYPE_NORMALIZE.get(contract_type.lower().strip(), contract_type.lower().strip()) if contract_type else "default"
    required_groups = REQUIREMENTS_BY_CONTRACT_TYPE.get(normalized_contract, REQUIREMENTS_BY_CONTRACT_TYPE["default"])

    # ── 4. Verificar grupos obrigatórios satisfeitos ──
    satisfied_groups = []
    missing_groups = []

    # Recolher todas as categorias dos documentos órfãos
    uploaded_categories = set()
    for doc in orphan_docs:
        cat = doc.get("category", "")
        if isinstance(cat, dict):
            cat = cat.get("value", cat.get("label", ""))
        cat_str = str(cat).strip()
        if cat_str:
            uploaded_categories.add(cat_str)

    # Verificar cada grupo obrigatório
    for group_name in required_groups:
        acceptable_cats = DOCUMENT_REQUIREMENT_MAP.get(group_name, [])
        # Um grupo é satisfeito se pelo menos uma das categorias aceitáveis
        # está presente nos documentos uploaded
        is_satisfied = any(
            acc_cat in uploaded_categories or acc_cat.lower() in {c.lower() for c in uploaded_categories}
            for acc_cat in acceptable_cats
        )

        if is_satisfied:
            satisfied_groups.append(group_name)
        else:
            missing_groups.append(group_name)

    # ── 5. Semáforo: Verde (completo) ou Vermelho (falta docs) ──
    is_complete = len(missing_groups) == 0

    if not is_complete:
        logger.info(
            f"[ONBOARDING] Cliente {client_id} — semáforo VERMELHO. "
            f"Faltam: {missing_groups}. Satisfeitos: {satisfied_groups}. "
            f"Tipo contrato: {contract_type} ({normalized_contract})"
        )
        return {
            "completed": False,
            "process_id": None,
            "missing": missing_groups,
            "satisfied": satisfied_groups,
            "contract_type": contract_type or "default",
            "orphan_docs_count": len(orphan_docs),
        }

    # ── 6. Semáforo Verde — Criar Processo e ancorar documentos ──
    logger.info(
        f"[ONBOARDING] Cliente {client_id} — semáforo VERDE! "
        f"Criando processo automático. "
        f"Tipo contrato: {contract_type} ({normalized_contract})"
    )

    try:
        process_result = await _create_process_and_anchor(client_id, client, orphan_docs)
        return {
            "completed": True,
            "process_id": process_result["process_id"],
            "process_number": process_result["process_number"],
            "missing": [],
            "satisfied": satisfied_groups,
            "contract_type": contract_type or "default",
            "orphan_docs_count": len(orphan_docs),
            "anchored_docs": process_result["anchored_count"],
        }
    except Exception as e:
        logger.error(f"[ONBOARDING] Erro ao criar processo para {client_id}: {e}")
        return {
            "completed": False,
            "process_id": None,
            "missing": missing_groups,
            "satisfied": satisfied_groups,
            "contract_type": contract_type or "default",
            "error": str(e),
        }


# ====================================================================
# DETECÇÃO DE TIPO DE CONTRATO
# ====================================================================

async def _detect_contract_type(client_id: str, client: dict, orphan_docs: list) -> str:
    """
    Detecta o tipo de contrato do cliente para determinar os requisitos.

    Prioridade:
    1. financial_data.tipo_contrato no documento do processo (se existe processo)
    2. Dados do cliente (dados_financeiros.tipo_contrato)
    3. Dados extraídos por IA de recibos/contratos nos documentos órfãos
    4. Default: "default" (requisitos mínimos)
    """
    # 1. Verificar dados financeiros do cliente
    financial_data = client.get("dados_financeiros") or client.get("financial_data") or {}
    if isinstance(financial_data, dict):
        tipo = financial_data.get("tipo_contrato")
        if tipo:
            return tipo

    # 2. Verificar processo existente (se o cliente já tem processo)
    process_ids = client.get("process_ids", [])
    if process_ids:
        process = await db.processes.find_one(
            {"id": {"$in": process_ids}},
            {"_id": 0, "financial_data": 1}
        )
        if process:
            pf = process.get("financial_data", {})
            if isinstance(pf, dict):
                tipo = pf.get("tipo_contrato")
                if tipo:
                    return tipo

    # 3. Verificar metadados de documentos (extraído por IA)
    for doc in orphan_docs:
        ai_data = doc.get("ai_extracted_data") or doc.get("extracted_data") or {}
        if isinstance(ai_data, dict):
            tipo = ai_data.get("tipo_contrato")
            if tipo:
                return tipo

    # 4. Verificar document_metadata (sistema de IA)
    for doc in orphan_docs:
        doc_id = doc.get("id")
        if doc_id:
            metadata = await db.document_metadata.find_one(
                {"document_id": doc_id},
                {"_id": 0, "ai_tags": 1, "ai_subcategory": 1}
            )
            if metadata:
                tags = metadata.get("ai_tags", [])
                subcat = metadata.get("ai_subcategory", "")
                # Procurar tipo de contrato nos tags ou subcategoria
                for tag in (tags + [subcat]):
                    tag_lower = (tag or "").lower().strip()
                    if tag_lower in CONTRACT_TYPE_NORMALIZE:
                        return tag_lower

    # 5. Default
    return "default"


# ====================================================================
# CRIAÇÃO DE PROCESSO E ANCORAGEM DE DOCUMENTOS
# ====================================================================

async def _create_process_and_anchor(
    client_id: str,
    client: dict,
    orphan_docs: list,
) -> Dict[str, Any]:
    """
    Cria um novo Process para o cliente e ancora todos os documentos
    órfãos (define process_id no documento).

    Args:
        client_id: ID do cliente
        client: Documento do cliente da BD
        orphan_docs: Lista de documentos sem processo

    Returns:
        Dict com process_id, process_number, anchored_count
    """
    now = datetime.now(timezone.utc).isoformat()
    process_id = str(uuid.uuid4())

    # Obter próximo número de processo
    last_process = await db.processes.find_one(
        {},
        sort=[("process_number", -1)],
        projection={"process_number": 1}
    )
    next_number = (last_process.get("process_number", 0) if last_process else 0) + 1

    # PACOTE DB — O processo é criado com status VAZIO (Lead). Só transita
    # para a 1ª fase real do Kanban via _auto_advance_from_pre_registo
    # (portal.py), que é invocado logo após esta criação quando os docs
    # obrigatórios já estão todos submetidos.

    # Dados do cliente
    client_name = client.get("nome", "Cliente")
    client_email = ""
    client_phone = ""
    contacto = client.get("contacto", {})
    if isinstance(contacto, dict):
        client_email = contacto.get("email", "")
        client_phone = contacto.get("telefone", "")

    # Preparar personal_data
    personal_data = {}
    dados_pessoais = client.get("dados_pessoais", {})
    if isinstance(dados_pessoais, dict):
        personal_data = dados_pessoais.copy()
    if client_email and not personal_data.get("email"):
        personal_data["email"] = client_email
    if client_phone and not personal_data.get("telefone"):
        personal_data["telefone"] = client_phone
    if client_name and not personal_data.get("nome"):
        personal_data["nome"] = client_name

    # Criar pasta S3 se necessário
    s3_folder = client.get("s3_folder")
    if not s3_folder:
        try:
            from services.s3_storage import s3_service
            result = await asyncio.to_thread(
                s3_service.initialize_client_folders,
                client_id,
                client_name,
                None
            )
            if result and len(result) == 2 and result[0]:
                s3_folder = result[1]
                await db.clients.update_one(
                    {"id": client_id},
                    {"$set": {"s3_folder": s3_folder}}
                )
        except Exception as e:
            logger.warning(f"[ONBOARDING] Erro ao criar pasta S3: {e}")

    # ── Criar documento do processo ──
    new_process = {
        "id": process_id,
        "process_number": next_number,
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "process_type": "credito_habitacao",  # Default — pode ser alterado pelo staff
        # PACOTE DB — status VAZIO (Lead); transita para 1ª fase real via
        # _auto_advance_from_pre_registo (portal.py) após criação.
        "status": None,
        "workflow_step": None,
        "personal_data": personal_data,
        "financial_data": client.get("dados_financeiros", {}),
        "real_estate_data": {},
        "credit_data": {},
        "co_buyers": client.get("co_buyers", []),
        "co_applicants": client.get("co_applicants", []),
        "s3_folder": s3_folder,
        "created_at": now,
        "updated_at": now,
        "created_by": "onboarding_auto",
        "source": "onboarding_auto",
    }

    await db.processes.insert_one(new_process)

    # ── Ancorar documentos órfãos no processo ──
    anchored_count = 0
    for doc in orphan_docs:
        doc_id = doc.get("id")
        if not doc_id:
            continue
        try:
            await db.documents.update_one(
                {"id": doc_id},
                {
                    "$set": {
                        "process_id": process_id,
                        "updated_at": now,
                    }
                }
            )
            anchored_count += 1
        except Exception as e:
            logger.warning(f"[ONBOARDING] Erro ao ancorar doc {doc_id}: {e}")

    # ── Actualizar cliente com o novo processo ──
    await db.clients.update_one(
        {"id": client_id},
        {
            "$addToSet": {"process_ids": process_id},
            "$set": {
                "updated_at": now,
                "lead_status": "converted",  # Cliente passou de lead a processo
            }
        }
    )

    # ── Log de histórico ──
    try:
        from services.history import log_history
        await log_history(
            process_id,
            user={"id": None, "name": "Sistema de Onboarding", "role": "system"},
            action="PROCESS_CREATED_BY_ONBOARDING",
            field="onboarding",
            old_value=None,
            new_value=f"Processo #{next_number} criado automaticamente após validação de documentos. {anchored_count} documentos ancorados."
        )
    except Exception as e:
        logger.warning(f"[ONBOARDING] Erro ao registar histórico: {e}")

    logger.info(
        f"[ONBOARDING] Processo #{next_number} ({process_id}) criado para "
        f"cliente {client_id} com {anchored_count} documentos ancorados"
    )

    return {
        "process_id": process_id,
        "process_number": next_number,
        "anchored_count": anchored_count,
    }


# ====================================================================
# HELPERS
# ====================================================================

def _get_required_groups(contract_type: str) -> List[str]:
    """Retorna os grupos obrigatórios para o tipo de contrato."""
    normalized = CONTRACT_TYPE_NORMALIZE.get(contract_type.lower().strip(), contract_type.lower().strip())
    return REQUIREMENTS_BY_CONTRACT_TYPE.get(normalized, REQUIREMENTS_BY_CONTRACT_TYPE["default"])


def get_onboarding_status(client_id: str) -> Dict[str, Any]:
    """
    Versão síncrona para consultar o estado do onboarding (sem criar processo).
    Útil para mostrar o progresso no frontend.
    """
    # NOTA: Esta função é um placeholder — a lógica real é assíncrona
    # e deve ser chamada via check_onboarding_completion()
    return {
        "client_id": client_id,
        "status": "pending_check",
    }
