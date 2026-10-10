"""
====================================================================
O PROCESSO PEDIDO POR ID TEM DE SER DA REDE DE QUEM PEDE
====================================================================
(adenda de RBAC, Out 2026 — achado a verificar a fronteira do Admin)

O QUE ESTAVA ABERTO
  As listagens de processos isolam por rede desde o Lote 4, mas o
  PEDIDO POR ID não: `GET /processes/{id}` carregava o documento e
  perguntava `can_view_process(user, process)`, que responde **sim a
  qualquer staff** («Todos os staff podem ver todos os processos»). O
  mesmo para `PUT /processes/{id}`, a mudança de fase, a atribuição, as
  notas, as mensagens do Portal, o `generate-magic-link`… — nenhum dos
  ~40 handlers de `routes/processes.py` perguntava a que rede o processo
  pertence. Um consultor da Domus que soubesse (ou adivinhasse) o id de
  um processo da Power abria-o inteiro: dados pessoais desencriptados,
  finanças, documentos.

  É a lição de sempre desta casa: `require_roles` autoriza o VERBO, não o
  OBJECTO — e um ponto único para a CONDIÇÃO das listagens não chega, é
  preciso inventariar quem LÊ por id.

POR QUE UMA DEPENDÊNCIA DE ROUTER E NÃO 40 CHAMADAS
  Os handlers são stubs finos que delegam em serviços; a pergunta «este
  processo é da minha rede?» tem a mesma resposta para todos, e escrevê-la
  em cada um era garantir que o quadragésimo primeiro a esquece. Como
  dependência do `APIRouter`, cobre também as rotas que alguém acrescente
  amanhã — e há um teste que falha se a dependência sair do router.

REGRAS
  * **404 e nunca 403**, com a MESMA mensagem de «não existe» — distinguir
    os dois confirma o id a quem adivinha;
  * a rede convidada conta (`processo_no_ambito`): um processo partilhado
    por Via Rápida abre ao parceiro;
  * o Master passa sem ler nada (não tem fronteira);
  * um id que não existe NÃO é recusado aqui: o handler responde o seu 404;
  * só actua em rotas com `{process_id}` no caminho — as restantes passam
    (listagens, criação, kanban), que têm as suas condições.
====================================================================
"""
from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request

from database import db
from services.auth import get_current_user
from services.role_scope import utilizador_e_global
from services.tenant_network import (
    CAMPO_REDES_PARCEIRAS,
    PROJECCAO_DO_CARIMBO,
    processo_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

ERRO_PROCESSO_NAO_ENCONTRADO = "Processo não encontrado"

PROJECCAO_DE_POSSE = {"_id": 0, "id": 1, CAMPO_REDES_PARCEIRAS: 1, **PROJECCAO_DO_CARIMBO}


async def exigir_processo_no_ambito(
    request: Request,
    user: dict = Depends(get_current_user),
) -> None:
    """Dependência do router: 404 se o `{process_id}` do caminho é de outra rede."""
    process_id = request.path_params.get("process_id")
    if not process_id:
        return
    if utilizador_e_global(user):
        return

    processo = await db.processes.find_one({"id": process_id}, PROJECCAO_DE_POSSE)
    if not processo:
        # O handler responde o 404 dele; aqui não se confirma nada.
        return

    scope = await resolve_tenant_scope(user)
    if not processo_no_ambito(processo, scope):
        logger.warning(
            "[PROCESSOS] %s pediu o processo %s, fora da sua rede.",
            (user or {}).get("id"), process_id,
        )
        raise HTTPException(status_code=404, detail=ERRO_PROCESSO_NAO_ENCONTRADO)
