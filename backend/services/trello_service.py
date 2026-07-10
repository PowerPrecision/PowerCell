"""
====================================================================
TRELLO MIRROR SERVICE — PowerCell CRM (Pacote CW)
====================================================================
Serviço de sincronização automática UNIDIRECIONAL (CRM → Trello) para
que o Trello funcione como backup estrutural e visual em tempo real.

CONFIGURAÇÃO (variáveis de ambiente):
    TRELLO_API_KEY   — API key da aplicação Trello (trello.com/power-ups-up)
    TRELLO_TOKEN     — Token de autorização do utilizador
    TRELLO_BOARD_ID  — ID do quadro Trello onde espelhar os processos

Se alguma variável faltar, o serviço desliga-se silenciosamente (todas
as funções retornam None sem erro) — o CRM funciona sem Trello.

FUNÇÕES PÚBLICAS:
    get_or_create_trello_list(list_name) -> str|None
        Procura ou cria uma coluna no quadro Trello. Retorna o list ID.

    sync_process_to_trello(process, action='create'|'move'|'update') -> None
        - create: cria cartão na lista correta, guarda trello_card_id
        - move:   move cartão para a nova lista
        - update: atualiza a descrição do cartão com dados úteis (IA)

COMO É CHAMADO:
    Em routes/processes.py, via asyncio.create_task(sync_process_to_trello(...))
    — fire-and-forget, não atrasa a UI do CRM.

MAPA STATUS → COLUNA:
    O nome da coluna Trello vem da coleção `workflow_statuses` (campo
    `label`). Ex: status="pre_registo" → label="Pré-Registo" → coluna
    "Pré-Registo" no Trello. Se a coluna não existir, é criada.
====================================================================
"""
import os
import logging
import httpx
from typing import Optional, Dict, Any

from database import db

logger = logging.getLogger(__name__)

# ── Configuração (lida 1x na importação) ─────────────────────────────
TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY", "")
TRELLO_TOKEN = os.environ.get("TRELLO_TOKEN", "")
TRELLO_BOARD_ID = os.environ.get("TRELLO_BOARD_ID", "")

TRELLO_BASE_URL = "https://api.trello.com/1"
TRELLO_TIMEOUT = 15.0  # segundos

# Cache em memória: {list_name: trello_list_id} — evita queries repetidas
_list_cache: Dict[str, str] = {}


def is_configured() -> bool:
    """True se as 3 variáveis do Trello estão configuradas."""
    return bool(TRELLO_API_KEY and TRELLO_TOKEN and TRELLO_BOARD_ID)


def _auth_params() -> Dict[str, str]:
    """Parâmetros de autenticação comuns a todos os requests Trello."""
    return {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}


def _build_card_description(process: Dict[str, Any]) -> str:
    """Constrói a descrição do cartão Trello com dados úteis do processo.

    Inclui dados extraídos pela IA / preenchidos pelo Consultor:
    NIF, Salário, Valor do Imóvel, Valor a Financiar, etc.
    """
    lines = ["📋 DADOS DO PROCESSO (CRM → Trello Mirror)", ""]

    # Cliente
    client_name = process.get("client_name") or "—"
    client_email = process.get("client_email") or ""
    client_phone = process.get("client_phone") or ""
    lines.append(f"👤 Cliente: {client_name}")
    if client_email:
        lines.append(f"   ✉️ {client_email}")
    if client_phone:
        lines.append(f"   📞 {client_phone}")

    # Dados pessoais (NIF, CC) — podem estar em personal_data ou dados_pessoais
    personal = process.get("personal_data") or {}
    nif = personal.get("nif") or "—"
    doc_id = personal.get("documento_id") or "—"
    lines.append(f"🆔 NIF: {nif}")
    lines.append(f"   CC: {doc_id}")

    # Dados financeiros (salário, valor a financiar)
    financial = process.get("financial_data") or {}
    salary = financial.get("monthly_income") or financial.get("salario_bruto") or financial.get("salario_liquido") or "—"
    valor_financiado = financial.get("valor_financiado") or "—"
    capital_proprio = financial.get("capital_proprio") or "—"
    lines.append(f"💰 Salário: {salary}")
    lines.append(f"   Valor a Financiar: {valor_financiado}")
    lines.append(f"   Capital Próprio: {capital_proprio}")

    # Dados do imóvel
    real_estate = process.get("real_estate_data") or {}
    valor_imovel = real_estate.get("valor_imovel") or "—"
    tipologia = real_estate.get("tipologia") or "—"
    localizacao = real_estate.get("localidade") or real_estate.get("concelho") or "—"
    lines.append(f"🏠 Valor do Imóvel: {valor_imovel}")
    lines.append(f"   Tipologia: {tipologia}")
    lines.append(f"   Localização: {localizacao}")

    # Dados do crédito
    credit = process.get("credit_data") or {}
    requested = credit.get("requested_amount") or "—"
    interest = credit.get("interest_rate") or "—"
    monthly_payment = credit.get("monthly_payment") or "—"
    bank = credit.get("bank_name") or "—"
    lines.append(f"🏦 Valor do Empréstimo: {requested}")
    lines.append(f"   Taxa de Juro: {interest}%")
    lines.append(f"   Prestação Mensal: {monthly_payment}")
    lines.append(f"   Banco: {bank}")

    # Metadados do processo
    process_number = process.get("process_number") or "—"
    status = process.get("status") or "—"
    prioridade = process.get("prioridade") or "—"
    lines.append("")
    lines.append(f"🔢 Nº Processo: {process_number}")
    lines.append(f"📌 Estado: {status}")
    lines.append(f"⚡ Prioridade: {prioridade}")

    # Proveniência de dados (Pacote CS/CT) — resumo de campos preenchidos por IA
    fm = process.get("field_metadata") or {}
    ai_fields = [k for k, v in fm.items() if isinstance(v, dict) and v.get("source") == "ai"]
    if ai_fields:
        lines.append("")
        lines.append(f"🤖 Campos preenchidos pela IA: {len(ai_fields)}")

    return "\n".join(lines)


async def _get_status_label(status: str) -> str:
    """Lê o label humano do status na coleção workflow_statuses.

    Retorna o próprio status se não encontrar (fallback).
    """
    if not status:
        return "Sem Estado"
    try:
        doc = await db.workflow_statuses.find_one({"name": status}, {"_id": 0})
        if doc and doc.get("label"):
            return doc["label"]
    except Exception as e:
        logger.warning(f"[Trello] Erro ao ler workflow_statuses para '{status}': {e}")
    return status


async def get_or_create_trello_list(list_name: str) -> Optional[str]:
    """Procura ou cria uma coluna no quadro Trello.

    Usa cache em memória para evitar queries repetidas.
    Retorna o list ID do Trello, ou None se falhar.
    """
    if not is_configured():
        return None

    if not list_name:
        return None

    # Cache hit
    if list_name in _list_cache:
        return _list_cache[list_name]

    try:
        async with httpx.AsyncClient(timeout=TRELLO_TIMEOUT) as client:
            # 1. Procurar lista existente
            resp = await client.get(
                f"{TRELLO_BASE_URL}/boards/{TRELLO_BOARD_ID}/lists",
                params={**_auth_params(), "fields": "id,name"}
            )
            resp.raise_for_status()
            lists = resp.json()

            for lst in lists:
                if lst.get("name", "").strip().lower() == list_name.strip().lower():
                    list_id = lst["id"]
                    _list_cache[list_name] = list_id
                    logger.info(f"[Trello] Lista encontrada: '{list_name}' → {list_id}")
                    return list_id

            # 2. Criar nova lista (no fim do quadro)
            resp = await client.post(
                f"{TRELLO_BASE_URL}/lists",
                params={**_auth_params(),
                        "name": list_name,
                        "idBoard": TRELLO_BOARD_ID,
                        "pos": "bottom"}
            )
            resp.raise_for_status()
            new_list = resp.json()
            list_id = new_list["id"]
            _list_cache[list_name] = list_id
            logger.info(f"[Trello] Lista criada: '{list_name}' → {list_id}")
            return list_id

    except httpx.HTTPStatusError as e:
        logger.error(f"[Trello] Erro HTTP ao procurar/criar lista '{list_name}': "
                     f"{e.response.status_code} {e.response.text[:200]}")
    except Exception as e:
        logger.error(f"[Trello] Erro ao procurar/criar lista '{list_name}': {e}")
    return None


async def _create_card(list_id: str, name: str, description: str) -> Optional[str]:
    """Cria um cartão Trello numa lista. Retorna o card ID ou None."""
    try:
        async with httpx.AsyncClient(timeout=TRELLO_TIMEOUT) as client:
            resp = await client.post(
                f"{TRELLO_BASE_URL}/cards",
                params={**_auth_params(),
                        "idList": list_id,
                        "name": name,
                        "desc": description,
                        "pos": "top"}
            )
            resp.raise_for_status()
            card = resp.json()
            return card.get("id")
    except httpx.HTTPStatusError as e:
        logger.error(f"[Trello] Erro HTTP ao criar cartão: "
                     f"{e.response.status_code} {e.response.text[:200]}")
    except Exception as e:
        logger.error(f"[Trello] Erro ao criar cartão: {e}")
    return None


async def _move_card(card_id: str, list_id: str) -> bool:
    """Move um cartão Trello para outra lista. Retorna True se sucesso."""
    try:
        async with httpx.AsyncClient(timeout=TRELLO_TIMEOUT) as client:
            resp = await client.put(
                f"{TRELLO_BASE_URL}/cards/{card_id}",
                params={**_auth_params(), "idList": list_id}
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"[Trello] Erro HTTP ao mover cartão {card_id}: "
                     f"{e.response.status_code} {e.response.text[:200]}")
    except Exception as e:
        logger.error(f"[Trello] Erro ao mover cartão {card_id}: {e}")
    return False


async def _update_card(card_id: str, description: str, name: Optional[str] = None) -> bool:
    """Atualiza a descrição (e opcionalmente o nome) de um cartão Trello."""
    try:
        params = {**_auth_params(), "desc": description}
        if name:
            params["name"] = name
        async with httpx.AsyncClient(timeout=TRELLO_TIMEOUT) as client:
            resp = await client.put(
                f"{TRELLO_BASE_URL}/cards/{card_id}",
                params=params
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"[Trello] Erro HTTP ao atualizar cartão {card_id}: "
                     f"{e.response.status_code} {e.response.text[:200]}")
    except Exception as e:
        logger.error(f"[Trello] Erro ao atualizar cartão {card_id}: {e}")
    return False


async def sync_process_to_trello(
    process: Dict[str, Any],
    action: str = "create",
    new_status: Optional[str] = None,
) -> None:
    """Sincroniza um processo do CRM para o Trello.

    Args:
        process: Documento do processo (deve ter pelo menos 'id' e 'status').
                 Se for uma string, trata-se de um process_id e é buscado à BD.
        action: 'create' | 'move' | 'update'
        new_status: (opcional, para 'move') Novo status destino.
                    Se None, usa process['status'].

    Ações:
        - create: Cria cartão na lista correta, guarda trello_card_id no processo.
        - move:   Move cartão para a nova lista (usa trello_card_id existente).
        - update: Atualiza a descrição do cartão com dados úteis (IA).
    """
    if not is_configured():
        logger.debug("[Trello] Não configurado — sync ignorada.")
        return

    # Se receber um process_id (string), buscar o processo à BD
    if isinstance(process, str):
        try:
            process = await db.processes.find_one({"id": process}, {"_id": 0})
        except Exception as e:
            logger.error(f"[Trello] Erro ao buscar processo '{process}': {e}")
            return
        if not process:
            logger.warning("[Trello] Processo não encontrado para sync.")
            return

    process_id = process.get("id")
    if not process_id:
        logger.warning("[Trello] Processo sem ID — sync ignorada.")
        return

    # Determinar status alvo
    target_status = new_status or process.get("status")
    if not target_status:
        logger.warning(f"[Trello] Processo {process_id} sem status — sync ignorada.")
        return

    # Resolver nome da coluna (label humana do workflow_statuses)
    list_name = await _get_status_label(target_status)
    list_id = await get_or_create_trello_list(list_name)
    if not list_id:
        logger.error(f"[Trello] Não foi possível obter/criar lista '{list_name}' "
                     f"para processo {process_id}.")
        return

    trello_card_id = process.get("trello_card_id")
    card_name = process.get("client_name") or process.get("process_number") or f"Processo {process_id[:8]}"

    try:
        if action == "create":
            # Criar cartão + guardar trello_card_id
            if trello_card_id:
                logger.info(f"[Trello] Processo {process_id} já tem cartão {trello_card_id} — "
                            f"action='create' convertida para 'move'.")
                await _move_card(trello_card_id, list_id)
                return

            description = _build_card_description(process)
            card_id = await _create_card(list_id, card_name, description)
            if card_id:
                await db.processes.update_one(
                    {"id": process_id},
                    {"$set": {"trello_card_id": card_id,
                              "trello_synced_at": _now_iso()}}
                )
                logger.info(f"[Trello] Cartão criado para processo {process_id} → {card_id}")

        elif action == "move":
            if not trello_card_id:
                # Sem cartão existente — criar em vez de mover
                logger.info(f"[Trello] Processo {process_id} sem trello_card_id — "
                            f"action='move' convertida para 'create'.")
                description = _build_card_description(process)
                card_id = await _create_card(list_id, card_name, description)
                if card_id:
                    await db.processes.update_one(
                        {"id": process_id},
                        {"$set": {"trello_card_id": card_id,
                                  "trello_synced_at": _now_iso()}}
                    )
                return

            await _move_card(trello_card_id, list_id)
            logger.info(f"[Trello] Cartão {trello_card_id} movido para '{list_name}' "
                        f"(processo {process_id}).")

        elif action == "update":
            if not trello_card_id:
                # Sem cartão — criar em vez de atualizar
                logger.info(f"[Trello] Processo {process_id} sem trello_card_id — "
                            f"action='update' convertida para 'create'.")
                description = _build_card_description(process)
                card_id = await _create_card(list_id, card_name, description)
                if card_id:
                    await db.processes.update_one(
                        {"id": process_id},
                        {"$set": {"trello_card_id": card_id,
                                  "trello_synced_at": _now_iso()}}
                    )
                return

            description = _build_card_description(process)
            await _update_card(trello_card_id, description, name=card_name)
            await db.processes.update_one(
                {"id": process_id},
                {"$set": {"trello_synced_at": _now_iso()}}
            )
            logger.info(f"[Trello] Cartão {trello_card_id} atualizado (processo {process_id}).")

        else:
            logger.warning(f"[Trello] Ação desconhecida '{action}' para processo {process_id}.")

    except Exception as e:
        # Fire-and-forget: nunca propagar exceções (não pode rebentar o CRM)
        logger.error(f"[Trello] Erro inesperado no sync do processo {process_id} "
                     f"(action={action}): {e}")


def _now_iso() -> str:
    """Data ISO 8601 atual em UTC."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
