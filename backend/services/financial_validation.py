"""
====================================================================
VALIDAÇÃO FINANCEIRA — um AVISO, nunca um travão (Out 2026)
====================================================================
O PEDIDO
  Quando uma lead de parceiro entra com o comprovativo de pagamento fica
  a aguardar uma «Validação Financeira». CEO, Diretor e Administrativo
  podem **Validar** ou **Rejeitar**.

  * **Rejeitar:** a lead (ou o processo) é devolvida e sai da vista do
    Index; o parceiro é avisado do motivo.
  * **Não validado NÃO bloqueia nada.** A equipa (Index, consultores)
    trabalha a documentação e avança o processo por todas as fases até ao
    fim. O sistema só mostra, no processo, o selo vermelho
    «⚠️ Processo Não Validado» — para a equipa saber o risco de estar a
    trabalhar sem viabilidade confirmada.

POR ISTO ESTE MÓDULO NÃO TEM PORTA NO MOTOR DE FASES
  Nenhuma guarda do sistema lê `validacao_financeira`. É deliberado, e há
  um teste que o afirma: `process_closed_guard`, o Kanban, o Index, a
  atribuição e os documentos não importam nada daqui. Um aviso que se
  torna travão é um segundo estado de fase escrito às escondidas.

ONDE VIVE O ESTADO
  `validacao_financeira` no CLIENTE (lead) e, quando nasce o processo, no
  PROCESSO (copiado por `partner_attribution`). Estados:
  ``pendente`` → ``validado`` | ``rejeitado``. O estado do processo é o que
  o selo lê; o do cliente é espelhado em cada decisão.

QUEM DECIDE
  Só o perfil EFECTIVO CEO, Diretor ou Administrativo, e só sobre o que
  está no seu âmbito de rede (**404 e nunca 403** para o resto — um 403
  confirmava que o id existe). O Master e o Admin não decidem: é uma
  decisão de negócio da casa, não de infraestrutura.
====================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request

from database import db
from services.partner_drafts import CAMPO_VALIDACAO, devolver_ao_parceiro
from services.phase_automation import ORIGEM_MOVIMENTO, ao_entrar_na_fase_sem_falhar
from services.tenant_network import (
    documento_no_ambito,
    processo_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

PAPEIS_QUE_VALIDAM = ("ceo", "diretor", "administrativo")

ESTADO_PENDENTE = "pendente"
ESTADO_VALIDADO = "validado"
ESTADO_REJEITADO = "rejeitado"
ESTADOS = (ESTADO_PENDENTE, ESTADO_VALIDADO, ESTADO_REJEITADO)

DECISAO_VALIDAR = "validate"
DECISAO_REJEITAR = "reject"

TIPOS = ("process", "lead")

MOTIVO_MINIMO = 3
MOTIVO_MAXIMO = 500

ERRO_SEM_PERMISSAO = "Apenas CEO, Diretor ou Administrativo podem decidir a validação financeira."
ERRO_NAO_ENCONTRADO = "Não encontrado."


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


# ════════════════════════════════════════════════════════════════════
#  PURAS
# ════════════════════════════════════════════════════════════════════
def pode_decidir(papel_efectivo: Any) -> bool:
    return _texto(papel_efectivo).lower() in PAPEIS_QUE_VALIDAM


def estado_da_validacao(doc: Optional[dict]) -> Optional[str]:
    """O estado, ou ``None`` quando o documento não passa por validação
    (processos que não vieram de um parceiro)."""
    validacao = (doc or {}).get(CAMPO_VALIDACAO)
    if not isinstance(validacao, dict):
        return None
    estado = _texto(validacao.get("estado"))
    return estado if estado in ESTADOS else None


def esta_por_validar(doc: Optional[dict]) -> bool:
    """O selo vermelho: tem validação e ainda não foi validada.

    «Rejeitado» também é não validado — um processo rejeitado que a equipa
    reabriu continua a precisar do aviso.
    """
    estado = estado_da_validacao(doc)
    return estado is not None and estado != ESTADO_VALIDADO


def validar_motivo(motivo: Any) -> str:
    texto = _texto(motivo)
    if len(texto) < MOTIVO_MINIMO:
        raise HTTPException(status_code=400, detail="Indique o motivo da rejeição (é enviado ao parceiro).")
    if len(texto) > MOTIVO_MAXIMO:
        raise HTTPException(status_code=400, detail=f"O motivo não pode ter mais de {MOTIVO_MAXIMO} caracteres.")
    return texto


def _novo_estado(anterior: Optional[dict], estado: str, *, utilizador: dict, motivo: Optional[str]) -> dict:
    novo = dict(anterior or {})
    novo.update({
        "estado": estado,
        "decidido_em": _agora(),
        "decidido_por": _texto(utilizador.get("id")),
        "decidido_por_nome": _texto(utilizador.get("name")),
    })
    if motivo:
        novo["motivo"] = motivo
    else:
        novo.pop("motivo", None)
    return novo


# ════════════════════════════════════════════════════════════════════
#  CARREGAR (com a fronteira de rede)
# ════════════════════════════════════════════════════════════════════
async def _carregar(tipo: str, item_id: str, utilizador: dict) -> dict:
    if tipo not in TIPOS:
        raise HTTPException(status_code=404, detail=ERRO_NAO_ENCONTRADO)
    scope = await resolve_tenant_scope(utilizador)

    if tipo == "process":
        doc = await db.processes.find_one({"id": item_id}, {"_id": 0})
        if not doc or doc.get("is_deleted") or not processo_no_ambito(doc, scope):
            raise HTTPException(status_code=404, detail=ERRO_NAO_ENCONTRADO)
        return doc

    doc = await db.clients.find_one({"id": item_id}, {"_id": 0})
    if not doc or doc.get("is_deleted") or not documento_no_ambito(doc, scope):
        raise HTTPException(status_code=404, detail=ERRO_NAO_ENCONTRADO)
    return doc


async def _exigir_papel(request: Optional[Request], utilizador: dict) -> str:
    from services.auth import get_effective_role_async

    papel = await get_effective_role_async(request, utilizador) if request is not None else _texto(utilizador.get("role"))
    if not pode_decidir(papel):
        raise HTTPException(status_code=403, detail=ERRO_SEM_PERMISSAO)
    return papel


# ════════════════════════════════════════════════════════════════════
#  DECIDIR
# ════════════════════════════════════════════════════════════════════
async def run_decidir(
    tipo: str,
    item_id: str,
    decisao: str,
    motivo: Optional[str],
    utilizador: dict,
    *,
    request: Optional[Request] = None,
) -> dict:
    """Valida ou rejeita. Idempotente por estado: repetir é 409."""
    # Primeiro a existência/âmbito (404), depois o papel (403)? Não: o
    # papel primeiro — quem não decide nem deve saber se o id existe.
    await _exigir_papel(request, utilizador)
    if decisao not in (DECISAO_VALIDAR, DECISAO_REJEITAR):
        raise HTTPException(status_code=400, detail="Decisão inválida.")
    motivo_validado = validar_motivo(motivo) if decisao == DECISAO_REJEITAR else None

    doc = await _carregar(tipo, item_id, utilizador)
    atual = estado_da_validacao(doc)
    if atual is None:
        raise HTTPException(status_code=400, detail="Este registo não tem validação financeira.")

    alvo = ESTADO_VALIDADO if decisao == DECISAO_VALIDAR else ESTADO_REJEITADO
    if atual == alvo:
        raise HTTPException(status_code=409, detail="Esta decisão já foi tomada.")

    novo = _novo_estado(doc.get(CAMPO_VALIDACAO), alvo, utilizador=utilizador, motivo=motivo_validado)

    if decisao == DECISAO_VALIDAR:
        await _gravar(tipo, doc, novo)
        await _historico(tipo, doc, utilizador, "Validação financeira: processo validado", ESTADO_VALIDADO)
        return {"success": True, "estado": ESTADO_VALIDADO, "devolvida": False}

    # REJEITAR
    devolvida = False
    if tipo == "lead":
        # Ainda não há processo: a lead volta ao parceiro e sai de tudo o
        # que é da equipa (incluindo a fila do Index).
        if (doc.get("process_ids") or []):
            raise HTTPException(
                status_code=409,
                detail="A lead já tem processo — rejeite o processo.",
            )
        await db.clients.update_one({"id": item_id}, {"$set": {CAMPO_VALIDACAO: novo}})
        rascunho = await devolver_ao_parceiro(item_id, motivo=motivo_validado or "", por=utilizador)
        devolvida = rascunho is not None
    else:
        await _gravar(tipo, doc, novo)
        await _tirar_da_operacao(doc)

    await _historico(
        tipo, doc, utilizador,
        f"Validação financeira: rejeitada — {motivo_validado}", ESTADO_REJEITADO,
    )
    await _avisar_parceiro(doc, motivo_validado or "")
    return {"success": True, "estado": ESTADO_REJEITADO, "devolvida": devolvida}


async def _gravar(tipo: str, doc: dict, novo: dict) -> None:
    """Grava o estado no registo decidido e espelha-o no cliente/processo
    irmão, para o selo e a lista nunca discordarem."""
    if tipo == "process":
        await db.processes.update_one(
            {"id": doc["id"]}, {"$set": {CAMPO_VALIDACAO: novo, "updated_at": _agora()}},
        )
        for client_id in _clientes_do_processo(doc):
            await db.clients.update_one({"id": client_id, CAMPO_VALIDACAO: {"$exists": True}},
                                        {"$set": {CAMPO_VALIDACAO: novo}})
        return
    await db.clients.update_one({"id": doc["id"]}, {"$set": {CAMPO_VALIDACAO: novo}})
    for process_id in doc.get("process_ids") or []:
        await db.processes.update_one({"id": process_id}, {"$set": {CAMPO_VALIDACAO: novo}})


def _clientes_do_processo(processo: dict) -> list[str]:
    ids = [processo.get("client_id"), processo.get("second_client_id"), *(processo.get("client_ids") or [])]
    return list(dict.fromkeys(_texto(i) for i in ids if _texto(i)))


async def _tirar_da_operacao(processo: dict) -> None:
    """Um processo rejeitado sai das vistas activas (Index incluído).

    Move-o para a fase de «perdido» do motor (ou a primeira terminal). Fica
    fechado — só leitura — e a equipa pode reabri-lo (`/processes/{id}/reopen`).
    Se o motor não tem fase terminal nenhuma, não se inventa uma: o processo
    fica como está, rejeitado e com o aviso.
    """
    try:
        from services.process_phase_clock import montar_update, transicao_de_fase
        from services.workflow_phases import carregar_fases, nomes_por_macro, nomes_terminais

        fases = await carregar_fases()
        terminais = set(nomes_terminais(fases))
        destino = next(
            (n for n in nomes_por_macro(fases, "perdido") if n in terminais),
            next(iter(sorted(terminais)), None),
        )
        if not destino or destino == processo.get("status"):
            return
        transicao = await transicao_de_fase(processo, destino)
        await db.processes.update_one(
            {"id": processo["id"]},
            montar_update({"status": destino, "updated_at": _agora(), "assigned_indexacao_id": None,
                           "indexacao_name": None}, transicao),
        )
        # Fase terminal: o gancho corta as sessões do Portal do cliente (processo
        # inativo) e nunca atribui nem cria trabalho. Não propaga.
        await ao_entrar_na_fase_sem_falhar(processo["id"], destino, origem=ORIGEM_MOVIMENTO)
    except Exception as exc:  # noqa: BLE001 — a rejeição já está gravada
        logger.warning("[VALIDACAO] Falha a fechar o processo rejeitado %s: %s", processo.get("id"), exc)


async def _historico(tipo: str, doc: dict, utilizador: dict, acao: str, estado: str) -> None:
    """Histórico do processo (honra o interruptor de rasto). Nunca propaga."""
    try:
        from services.history import log_history

        process_id = doc.get("id") if tipo == "process" else None
        if not process_id:
            return
        await log_history(
            process_id=process_id, user=utilizador, action=acao,
            field=CAMPO_VALIDACAO, old_value=None, new_value=estado,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VALIDACAO] Falha a registar no histórico: %s", exc)


async def _avisar_parceiro(doc: dict, motivo: str) -> None:
    """Email ao parceiro com o motivo. Nunca bloqueia nem propaga."""
    try:
        partner_id = _texto(doc.get("submitted_by_partner_id") or doc.get("assigned_parceiro_id"))
        if not partner_id:
            return
        from services.partner_accounts import contacto_do_parceiro

        parceiro = await contacto_do_parceiro(partner_id)
        if not parceiro:
            return
        from services.background_tasks import spawn_background_task

        spawn_background_task(
            _enviar_email_de_rejeicao(parceiro, doc, motivo), name=f"partner-reject:{doc.get('id')}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VALIDACAO] Falha a avisar o parceiro: %s", exc)


async def _enviar_email_de_rejeicao(parceiro: dict, doc: dict, motivo: str) -> None:
    try:
        from services.email_service import send_email

        cliente = doc.get("nome") or doc.get("client_name") or "o cliente"
        corpo = (
            f"Olá {parceiro.get('name') or ''},\n\n"
            f"A validação financeira do caso de {cliente} foi rejeitada.\n\n"
            f"Motivo: {motivo}\n\n"
            "O caso foi devolvido. Aceda ao Portal do Parceiro para ver os detalhes "
            "e, se aplicável, submeter novamente."
        )
        await send_email(
            account_name="power", to_emails=[parceiro["email"]],
            subject="Validação financeira rejeitada", body=corpo,
            force_system=True, system_purpose="NOTIFICATIONS",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VALIDACAO] Falha a enviar o email de rejeição: %s", exc)


# ════════════════════════════════════════════════════════════════════
#  O COMPROVATIVO (para quem valida)
# ════════════════════════════════════════════════════════════════════
VALIDADE_DO_URL_SEGUNDOS = 900


async def run_url_do_comprovativo(
    tipo: str, item_id: str, utilizador: dict, *, request: Optional[Request] = None,
) -> dict:
    """URL pré-assinado (15 min) do comprovativo, para quem valida.

    A chave sai do registo gravado (nunca do pedido) e passa pela MESMA
    guarda de posse do Portal: um registo com a chave envenenada não abre
    o bucket.
    """
    import asyncio

    from services.partner_drafts import comprovativo_do_caso
    from services.portal_upload_ops import assert_portal_file_key_e_do_cliente
    from services.s3_storage import s3_service

    await _exigir_papel(request, utilizador)
    doc = await _carregar(tipo, item_id, utilizador)
    if estado_da_validacao(doc) is None:
        raise HTTPException(status_code=404, detail=ERRO_NAO_ENCONTRADO)

    client_id = doc.get("id") if tipo == "lead" else doc.get("client_id")
    comprovativo = await comprovativo_do_caso(_texto(client_id)) if client_id else None
    if not comprovativo:
        raise HTTPException(status_code=404, detail="Sem comprovativo.")

    assert_portal_file_key_e_do_cliente(
        comprovativo["s3_path"],
        process=doc if tipo == "process" else None,
        client=doc if tipo == "lead" else {"id": client_id},
    )
    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="Serviço de armazenamento indisponível.")
    if not await asyncio.to_thread(s3_service.file_exists, comprovativo["s3_path"]):
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado.")
    url = s3_service.get_presigned_url(comprovativo["s3_path"], expiration=VALIDADE_DO_URL_SEGUNDOS)
    if not url:
        raise HTTPException(status_code=500, detail="Erro ao gerar o link de descarga.")
    return {
        "success": True, "url": url, "filename": comprovativo.get("filename"),
        "expires_in": VALIDADE_DO_URL_SEGUNDOS,
    }


__all__ = [
    "DECISAO_REJEITAR",
    "DECISAO_VALIDAR",
    "ESTADOS",
    "ESTADO_PENDENTE",
    "ESTADO_REJEITADO",
    "ESTADO_VALIDADO",
    "PAPEIS_QUE_VALIDAM",
    "estado_da_validacao",
    "esta_por_validar",
    "pode_decidir",
    "run_decidir",
    "run_url_do_comprovativo",
    "validar_motivo",
]
