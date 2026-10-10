"""
====================================================================
PORTAL DO PARCEIRO — SUBMETER UMA LEAD (V1)
====================================================================
O parceiro submete os dados de um cliente. É uma ESCRITA de um agente
externo na base de dados, por isso nada do que ele escolhe decide onde o
registo aterra nem de quem é.

O QUE O SERVIDOR DECIDE (nunca o corpo do pedido)
  * a rede e a empresa — das ligações activas do parceiro autenticado;
    o corpo só pode ESCOLHER entre elas (e só quando há mais do que uma);
  * `submitted_by_partner_id/name` — o parceiro autenticado;
  * a fase e a triagem — `lead_status: "new"`, sem processo: o registo cai
    na Sala de Triagem como o do formulário público, e o processo só nasce
    quando a equipa o decide;
  * a origem (`fonte: "partner_portal"`) e o consentimento.

  O corpo é um modelo `extra="forbid"`: um `network_id`, `assigned_to` ou
  `lead_status` a mais é 422, não é ignorado em silêncio.

O QUE NÃO SE FAZ, DE PROPÓSITO
  * **Nada de «find-or-create» por email/NIF.** O registo público reaproveita
    um cliente existente e actualiza-o com o que vem do formulário; aqui
    isso seria um agente externo a ESCREVER num cliente que não é seu
    (incluindo de outra rede) e a descobrir que ele existe. Cada submissão
    cria um registo novo. Se já havia um cliente igual DENTRO DA MESMA REDE,
    o registo novo leva `possible_duplicate_of` — informação para a
    triagem da equipa, que o parceiro nunca vê — e a resposta é igual em
    ambos os casos (sem oráculo).
  * A única resposta diferente é a do **duplo clique do próprio parceiro**:
    a mesma lead, pelo mesmo parceiro, nos últimos minutos devolve a que já
    existe. É um registo SEU, não revela nada de ninguém.

CONSENTIMENTO
  O parceiro tem de confirmar que tem autorização do cliente para partilhar
  os dados (`consent_confirmed`); fica gravado com data, parceiro e versão
  dos termos aceites. Quando é o próprio cliente a preencher, o caminho é
  o do referral (futuro) — a melhor base legal.
====================================================================
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import db
from models.client import generate_portal_access_code
from models.enums import ProcessType
from services.encryption import (
    encrypt_client_data,
    generate_email_hash,
    generate_nif_hash,
)
from services.partner_accounts import VERSAO_DOS_TERMOS
from services.partner_security import redes_activas
from services.partner_visibility import scope_do_parceiro
from services.tenant_network import build_network_scope_condition
from utils.input_sanitization import (
    sanitize_email,
    sanitize_name,
    sanitize_nif,
    sanitize_phone,
    sanitize_string,
)

logger = logging.getLogger(__name__)

#: Um tecto por dia, por parceiro. Um parceiro a sério submete dezenas; um
#: script (ou uma conta comprometida) submete milhares, e cada lead
#: acorda a gestão da rede com uma notificação.
LIMITE_DE_LEADS_POR_DIA = 50
#: Janela do duplo clique.
JANELA_DO_DUPLO_CLIQUE_MINUTOS = 10

TIPOS_DE_PROCESSO = tuple(t.value for t in ProcessType)
TIPO_POR_OMISSAO = ProcessType.CREDITO_HABITACAO.value


class PartnerLeadIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=120)
    #: Obrigatório: o Portal do Cliente e a criação do processo exigem email.
    email: str = Field(..., min_length=3, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    nif: Optional[str] = Field(None, max_length=20)
    process_type: Optional[str] = Field(None, max_length=40)
    has_property: bool = False
    notes: Optional[str] = Field(None, max_length=1000)
    #: Só para escolher ENTRE as redes do próprio parceiro.
    network_id: Optional[str] = Field(None, max_length=80)
    consent_confirmed: bool = False


# ════════════════════════════════════════════════════════════════════
#  PURAS
# ════════════════════════════════════════════════════════════════════
def escolher_ligacao(partner: dict, network_id: Optional[str]) -> dict:
    """A ligação (rede + empresa) onde a lead aterra. 400 se ambígua.

    Uma rede pedida que não é das suas ligações activas é um 404 igual ao
    de «não existe»: o corpo não pode nomear a rede de outrem.
    """
    activas = redes_activas(partner)
    if not activas:
        raise HTTPException(status_code=403, detail="Conta indisponível. Contacte o seu consultor.")
    if network_id:
        escolhida = next((r for r in activas if str(r.get("network_id")) == network_id.strip()), None)
        if not escolhida:
            raise HTTPException(status_code=404, detail="Rede não encontrada.")
        return escolhida
    if len(activas) > 1:
        raise HTTPException(status_code=400, detail="Indique a rede a que esta lead se destina.")
    return activas[0]


def montar_cliente(
    *,
    partner: dict,
    ligacao: dict,
    nome: str,
    email: str,
    telefone: Optional[str],
    nif: Optional[str],
    tipo: str,
    has_property: bool,
    notas: Optional[str],
    agora: str,
    client_id: Optional[str] = None,
) -> dict:
    """O documento do cliente, no mesmo formato do registo público."""
    dados = {"nome": nome, "email": email, "telefone": telefone}
    if nif:
        dados["nif"] = nif
    doc = {
        "id": client_id or str(uuid.uuid4()),
        "nome": nome,
        "contacto": {"email": email, "telefone": telefone},
        "dados_pessoais": dados,
        "dados_financeiros": {},
        "dados_imobiliarios": {},
        "process_ids": [],
        "portal_access_code": generate_portal_access_code(),
        "fonte": "partner_portal",
        "has_property": bool(has_property),
        "idade_menos_35": False,
        "created_at": agora,
        "updated_at": agora,
        "registration_completed": True,
        "assigned_to": None,
        "assigned_at": None,
        "lead_status": "new",
        "pending_process_type": tipo,
        "titular2_data": {},
        "custom_fields": {},
        # ── quem trouxe, e com que consentimento ──
        "submitted_by_partner_id": partner["id"],
        "submitted_by_partner_name": partner.get("name"),
        "partner_consent": {
            "confirmed": True,
            "at": agora,
            "partner_id": partner["id"],
            "terms_version": VERSAO_DOS_TERMOS,
        },
        # ── o carimbo: SÓ das ligações do parceiro ──
        "network_id": ligacao["network_id"],
        "company_id": ligacao.get("company_id"),
        "company_name": ligacao.get("company_name"),
    }
    if notas:
        doc["notas_do_parceiro"] = notas
    return {k: v for k, v in doc.items() if v is not None or k in ("assigned_to", "assigned_at")}


# ════════════════════════════════════════════════════════════════════
#  SUBMETER
# ════════════════════════════════════════════════════════════════════
def _resposta(client: dict, *, repetida: bool = False) -> dict:
    return {
        "success": True,
        "id": client["id"],
        "kind": "lead",
        "client_name": client.get("nome"),
        "created_at": client.get("created_at"),
        "repetida": repetida,
    }


async def _contar_leads_recentes(partner_id: str, desde: str) -> int:
    return await db.clients.count_documents(
        {"submitted_by_partner_id": partner_id, "created_at": {"$gte": desde}}
    )


async def _candidatos_a_duplicado(scope, email_hash: Optional[str], nif_hash: Optional[str]) -> list[str]:
    """Clientes IGUAIS dentro da mesma rede — para a triagem, nunca para o parceiro."""
    ramos = []
    if email_hash:
        ramos.append({"contacto.email_hash": email_hash})
    if nif_hash:
        ramos.append({"dados_pessoais.nif_hash": nif_hash})
    if not ramos:
        return []
    achados = await db.clients.find(
        {"$and": [{"$or": ramos}, build_network_scope_condition(scope), {"is_deleted": {"$ne": True}}]},
        {"_id": 0, "id": 1},
    ).to_list(5)
    return [c["id"] for c in achados if c.get("id")]


async def run_submit_lead(partner: dict, data: PartnerLeadIn) -> dict:
    if not data.consent_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirme que tem autorização do cliente para partilhar estes dados.",
        )

    email = sanitize_email(data.email)
    nome = sanitize_name(data.name)
    if not email:
        raise HTTPException(status_code=400, detail="Email inválido.")
    if len(nome) < 2:
        raise HTTPException(status_code=400, detail="Nome inválido.")
    telefone = sanitize_phone(data.phone) if data.phone else None
    nif = None
    if data.nif:
        nif = sanitize_nif(data.nif)
        if not nif:
            raise HTTPException(status_code=400, detail="NIF inválido.")
    tipo = (data.process_type or TIPO_POR_OMISSAO).strip()
    if tipo not in TIPOS_DE_PROCESSO:
        raise HTTPException(status_code=400, detail="Tipo de processo inválido.")
    notas = sanitize_string(data.notes, max_length=1000) if data.notes else None

    ligacao = escolher_ligacao(partner, data.network_id)
    agora_dt = datetime.now(timezone.utc)
    agora = agora_dt.isoformat()

    # 1. O duplo clique do próprio parceiro: devolve o que já existe.
    email_hash = generate_email_hash(email)
    if email_hash:
        recente = await db.clients.find_one(
            {
                "submitted_by_partner_id": partner["id"],
                "contacto.email_hash": email_hash,
                "created_at": {"$gte": (agora_dt - timedelta(minutes=JANELA_DO_DUPLO_CLIQUE_MINUTOS)).isoformat()},
            },
            {"_id": 0, "id": 1, "nome": 1, "created_at": 1},
        )
        if recente:
            return _resposta(recente, repetida=True)

    # 2. O tecto diário.
    if await _contar_leads_recentes(partner["id"], (agora_dt - timedelta(days=1)).isoformat()) >= LIMITE_DE_LEADS_POR_DIA:
        raise HTTPException(
            status_code=429,
            detail="Atingiu o limite diário de leads. Tente novamente amanhã ou contacte o seu consultor.",
        )

    # 3. Construir, marcar possíveis duplicados (só para a equipa) e gravar.
    cliente = montar_cliente(
        partner=partner, ligacao=ligacao, nome=nome, email=email, telefone=telefone,
        nif=nif, tipo=tipo, has_property=data.has_property, notas=notas, agora=agora,
    )
    duplicados = await _candidatos_a_duplicado(
        scope_do_parceiro({**partner, "redes": [ligacao]}),
        email_hash,
        generate_nif_hash(nif) if nif else None,
    )
    if duplicados:
        cliente["possible_duplicate_of"] = duplicados

    try:
        cifrado = encrypt_client_data(cliente)
    except Exception as exc:  # noqa: BLE001 — sem cifra não se grava PII em claro
        logger.error("[PARCEIRO] Falha a cifrar a lead de %s: %s", partner["id"], exc)
        raise HTTPException(status_code=500, detail="Não foi possível guardar a lead. Tente novamente.")
    await db.clients.insert_one(dict(cifrado))

    _depois_de_gravar(partner, cliente, ligacao)
    return _resposta(cliente)


def _depois_de_gravar(partner: dict, cliente: dict, ligacao: dict) -> None:
    """Pedidos da checklist e aviso à gestão da rede, em segundo plano.

    Nunca bloqueiam nem fazem falhar a submissão: o registo já está
    gravado. `spawn_background_task` guarda a referência forte (uma task
    solta pode ser recolhida pelo GC e o aviso perde-se sem erro).
    """
    from services.background_tasks import spawn_background_task

    spawn_background_task(_pedir_checklist(partner, cliente), name=f"partner-lead-checklist:{cliente['id']}")
    spawn_background_task(_avisar_a_gestao(partner, cliente, ligacao), name=f"partner-lead-alert:{cliente['id']}")


async def _pedir_checklist(partner: dict, cliente: dict) -> None:
    """Os pedidos obrigatórios, ligados ao CLIENTE (ainda não há processo):
    é por eles que o parceiro e a equipa falam sobre o que falta."""
    try:
        from services.portal_documents_notify import generate_mandatory_document_requests

        await generate_mandatory_document_requests(
            process_id=None,
            client_id=cliente["id"],
            company_id=cliente.get("company_id"),
            requested_by="partner_portal",
            requested_by_name=partner.get("name") or "Parceiro",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO] Falha a gerar a checklist da lead %s: %s", cliente.get("id"), exc)


async def _avisar_a_gestao(partner: dict, cliente: dict, ligacao: dict) -> None:
    try:
        from services.alerts import notify_new_client_registration

        await notify_new_client_registration(
            {
                "id": cliente["id"],
                "client_id": cliente["id"],
                "client_name": cliente.get("nome"),
                "client_email": (cliente.get("contacto") or {}).get("email"),
                "client_phone": (cliente.get("contacto") or {}).get("telefone"),
                "process_type": cliente.get("pending_process_type"),
                # O carimbo é o que escolhe A GESTÃO DESTINATÁRIA — da rede
                # do parceiro, nunca a de todas.
                "network_id": ligacao["network_id"],
                "company_id": ligacao.get("company_id"),
                "company_name": ligacao.get("company_name"),
            },
            has_property=bool(cliente.get("has_property")),
            origem=f"Parceiro {partner.get('name') or ''}".strip(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO] Falha a avisar a gestão da lead %s: %s", cliente.get("id"), exc)


__all__ = [
    "JANELA_DO_DUPLO_CLIQUE_MINUTOS",
    "LIMITE_DE_LEADS_POR_DIA",
    "PartnerLeadIn",
    "TIPOS_DE_PROCESSO",
    "escolher_ligacao",
    "montar_cliente",
    "run_submit_lead",
]
