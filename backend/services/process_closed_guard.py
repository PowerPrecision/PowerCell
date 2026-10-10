"""
====================================================================
UM PROCESSO FECHADO NÃO SE ALTERA — A EQUIPA TEM DE O REABRIR
====================================================================
(Out 2026 — o outro lado do bloqueio do Portal)

O QUE ESTAVA ABERTO
  O Portal do Cliente já fecha quando o processo está numa fase terminal
  (`portal_estado`). O CRM não: o único bloqueio era no `PUT /processes/{id}`,
  e tinha três defeitos —
    1. corria DEPOIS de gravar os dados do cliente e a troca de titular
       (`apply_client_personal_updates_from_process_put`), pelo que o 403
       chegava com a ficha do cliente já alterada;
    2. Master/Admin/CEO passavam por cima, enquanto o ecrã tratava toda a
       gente por igual (o produto a contradizer-se);
    3. o resto do CRM nem perguntava: atribuições, notas, titulares,
       uploads, mover/renomear/eliminar/categorizar documentos, pedidos ao
       Portal, ligações de pastas, notas de voz… tudo escrevia num processo
       «Concluído» ou «Cancelado» sem ninguém reparar.

A REGRA (decisão do dono do produto)
  Num processo em fase terminal a equipa NÃO altera campos nem carrega
  ficheiros (403). Para mexer, o consultor «Reabre» primeiro (volta a uma
  fase activa) e só depois edita. Não há excepção por cargo: o Master e o
  Admin reabrem como os outros — um bypass no servidor que o ecrã não tem
  é o «menu e rotas têm de concordar» ao contrário.

COMO SE APLICA  (duas camadas, e a segunda não é redundante)
  1. `exigir_processo_editavel` — dependência dos ROUTERS que escrevem num
     processo (`/processes`, `/documents`, `/onedrive`, `/storage`, notas de
     voz): qualquer verbo de escrita com `{process_id}` no caminho. Cobre
     também a rota que alguém acrescente amanhã. É a decisão do
     `process_scope_guard`; um inventário por AST falha se um router sair.
  2. `exigir_processo_aberto` — chamada pelos serviços cujo processo NÃO vem
     no caminho (o upload manda o `process_id` no corpo ou resolve-o a
     partir do cliente): `assert_can_upload_to_process`, a eliminação de
     ficheiros e o `PUT /processes/{id}` (que tem de recusar ANTES de gravar
     o que quer que seja).

O QUE FICA DE FORA, de propósito  (`ROTAS_QUE_FUNCIONAM_COM_O_PROCESSO_FECHADO`)
  Cada entrada tem o motivo escrito: reabrir, mover no Kanban (é como se
  reabre arrastando), eliminar o processo, falar com o cliente, gerar o
  acesso ao Portal e os registos de contabilidade interna (origem financeira,
  serviço pago pelo parceiro, revogar uma partilha) — não alteram os dados do
  processo e acontecem, legitimamente, depois de ele fechar.

SEM ORÁCULO
  Um processo de OUTRA rede não responde «está fechado»: a dependência só
  decide quando o processo é visível a quem pede; senão deixa o handler (ou
  o `process_scope_guard`) dar a resposta de sempre.

A AUTORIDADE É A FASE GRAVADA, a mesma do Portal (`portal_estado`): resolve
gralhas e aliases e conta os nomes legados (`cancelado`, `arquivo`).
====================================================================
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request

from database import db
from services.auth import get_current_user
from services.portal_estado import estado_e_terminal
from services.role_scope import utilizador_e_global
from services.tenant_network import (
    CAMPO_REDES_PARCEIRAS,
    PROJECCAO_DO_CARIMBO,
    processo_no_ambito,
    resolve_tenant_scope,
)
from services.workflow_phases import carregar_fases

logger = logging.getLogger(__name__)

CODIGO_PROCESSO_FECHADO = "processo_fechado"
METODOS_DE_LEITURA = frozenset({"GET", "HEAD", "OPTIONS"})

#: (método, caminho completo da rota) → porquê pode escrever-se num processo
#: fechado. O caminho é o TEMPLATE da rota, tal como o FastAPI o regista
#: (com o prefixo do router); a comparação é por fim de caminho.
ROTAS_QUE_FUNCIONAM_COM_O_PROCESSO_FECHADO: dict[tuple[str, str], str] = {
    ("POST", "/processes/{process_id}/reopen"):
        "É a própria saída: reabrir tem de funcionar num processo fechado.",
    ("PUT", "/processes/kanban/{process_id}/move"):
        "Arrastar para uma fase activa é reabrir; o movimento não edita campos.",
    ("DELETE", "/processes/{process_id}"):
        "Eliminar não é editar — tem a sua permissão e o seu rasto.",
    ("POST", "/processes/{process_id}/portal-messages"):
        "Comunicar com o cliente não altera os dados do processo.",
    ("POST", "/processes/{process_id}/generate-magic-link"):
        "Dá acesso ao Portal; o Portal fechado recusa-o por si.",
    ("POST", "/processes/{process_id}/generate-magic-link/send"):
        "Idem: envia o acesso ao Portal, que o recusa se estiver fechado.",
    ("PUT", "/processes/{process_id}/origem-financeira"):
        "Contabilidade interna (coleção própria); acontece depois de fechar.",
    ("PUT", "/processes/{process_id}/partner-service"):
        "O pagamento do parceiro é registado depois do serviço concluído.",
    ("DELETE", "/processes/{process_id}/partners/{company_id}"):
        "Revogar uma partilha é limpeza de acesso, não edição do processo.",
}

PROJECCAO_DO_PROCESSO_FECHADO = {
    "_id": 0, "id": 1, "status": 1, CAMPO_REDES_PARCEIRAS: 1, **PROJECCAO_DO_CARIMBO,
}


def mensagem_de_processo_fechado(status: Optional[str]) -> str:
    return (
        f"Este processo está fechado (fase «{status}»). "
        "Reabra-o para o poder alterar."
    )


async def processo_esta_fechado(processo: Optional[dict]) -> bool:
    """O processo está numa fase terminal? `None` ou sem fase → não."""
    if not processo or not processo.get("status"):
        return False
    return estado_e_terminal(processo.get("status"), await carregar_fases())


async def exigir_processo_aberto(processo: Optional[dict]) -> None:
    """403 se o processo está numa fase terminal; `None` passa (não há o que fechar)."""
    if await processo_esta_fechado(processo):
        logger.info(
            "[PROCESSO-FECHADO] Escrita recusada no processo %s (fase %s)",
            (processo or {}).get("id"), (processo or {}).get("status"),
        )
        raise HTTPException(
            status_code=403,
            detail=mensagem_de_processo_fechado((processo or {}).get("status")),
        )


def _rota_permitida(request: Request) -> bool:
    rota = request.scope.get("route")
    caminho = getattr(rota, "path", "") or ""
    return any(
        request.method == metodo and caminho.endswith(sufixo)
        for (metodo, sufixo) in ROTAS_QUE_FUNCIONAM_COM_O_PROCESSO_FECHADO
    )


async def exigir_processo_editavel(
    request: Request, user: dict = Depends(get_current_user),
) -> None:
    """Dependência de router: 403 se o `{process_id}` do caminho está fechado.

    Só actua em verbos de escrita com `process_id` no caminho. Um id que não
    existe, ou que é de outra rede, passa — a resposta é a do handler.
    """
    if request.method in METODOS_DE_LEITURA:
        return
    process_id = request.path_params.get("process_id")
    if not process_id or _rota_permitida(request):
        return

    processo = await db.processes.find_one({"id": process_id}, PROJECCAO_DO_PROCESSO_FECHADO)
    if not processo:
        return
    if not utilizador_e_global(user):
        scope = await resolve_tenant_scope(user)
        if not processo_no_ambito(processo, scope):
            return
    await exigir_processo_aberto(processo)
