"""Quando o Portal do Cliente está BLOQUEADO — ponto único (Bloco 3, ponto 14).

A REGRA (decisão do dono do produto)
  «Se o estado de um processo passar a Inativo no CRM, o Portal do Cliente
  correspondente tem de ficar imediatamente bloqueado.» «Inativo» não é um
  estado com nome próprio: é qualquer FASE TERMINAL do motor de workflow
  (`is_active: False` — concluído, desistência, cancelado, arquivo…). Voltar a
  uma fase activa reactiva o Portal sozinho: nada aqui se grava.
  O bloqueio é TOTAL — o cliente não entra, e uma sessão já aberta deixa de
  funcionar no pedido seguinte.

A AUTORIDADE É A FASE GRAVADA, NÃO A FLAG DO PROCESSO
  `processes.is_active` é DERIVADA (o Kanban escreve-a ao mover) e já se
  desfasou da fase em dados reais — existe um endpoint de manutenção só para
  a recalcular. Decidir por ela bloqueava um cliente por uma flag velha, ou
  deixava passar quem devia estar bloqueado. Decide-se pelo `status` lido
  pelo motor (`workflow_phases`): resolve gralhas e aliases, e os nomes
  legados que não são fases (`cancelado`, `arquivo`) contam como terminais.

POR QUE NA `get_current_client`
  Todas as rotas autenticadas do Portal passam por essa dependência. Pô-la
  lá, e não em cada rota, é o que impede uma rota nova de esquecer a guarda
  («menu e rotas têm de concordar»); `tests/unit/test_portal_inativo.py`
  inventaria por AST as rotas do Portal e falha por omissão para qualquer uma
  que não use a dependência. Os pontos que EMITEM tokens (login por código,
  verificação por NIF, link curto) recusam logo, para o cliente ver o aviso
  em vez de entrar num ecrã vazio — mas a defesa é a guarda, não a emissão.

DUAS DECISÕES QUE NÃO SE PODEM PERDER
  1. **Credencial primeiro, estado depois.** Quem não provou ser o cliente
     recebe a mesma resposta de sempre (401). Responder «este processo está
     inativo» antes de validar o NIF/código seria um oráculo sobre o estado
     do processo de quem se adivinha (a ordem do Incidente P0 do Portal).
  2. **Um cliente com vários processos usa o activo.** O token sem processo
     (`no_process`) e o login por código escolhiam «o primeiro não eliminado»;
     se esse fosse um processo concluído, o cliente ficava bloqueado com outro
     processo em curso. Prefere-se o activo; só quando TODOS os processos do
     cliente estão inativos é que se bloqueia. Um token que nomeia um processo
     (`sub`) continua a ser desse processo.

«VER COMO CLIENTE» TAMBÉM VÊ O BLOQUEIO
  O JWT de impersonação não distingue o staff do cliente (a marca vive no
  documento do link, não nas claims), e é a vista certa: o consultor vê
  exactamente o que o cliente vê.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from fastapi import HTTPException

from services.workflow_phases import carregar_fases, nomes_terminais, resolver_nome

logger = logging.getLogger(__name__)

CODIGO_PORTAL_INATIVO = "portal_inativo"
MENSAGEM_PORTAL_INATIVO = (
    "O acesso ao Portal está suspenso porque este processo se encontra inativo. "
    "Contacte o seu consultor."
)


def estado_e_terminal(status: Optional[str], fases: Iterable[dict]) -> bool:
    """O `status` gravado é uma fase terminal do motor?

    Pura. Um processo SEM fase (lead, `None`) não é terminal. Uma fase que o
    motor não conhece e não está na lista legada também não: bloquear um
    cliente por um nome que ninguém sabe classificar seria o erro contrário
    (o Portal não deve fechar por dados sujos).
    """
    if not status:
        return False
    fases = list(fases)
    terminais = set(nomes_terminais(fases))
    if status in terminais:
        return True
    resolucao = resolver_nome(status, fases)
    return bool(resolucao.resolvida and resolucao.fase in terminais)


async def processo_esta_inativo(processo: Optional[dict]) -> bool:
    """O processo está numa fase terminal? (`None` → não está inativo.)"""
    if not processo:
        return False
    return estado_e_terminal(processo.get("status"), await carregar_fases())


def erro_portal_inativo() -> HTTPException:
    """403 com código estável — o ecrã decide pelo CÓDIGO, não pelo texto."""
    return HTTPException(
        status_code=403,
        detail={"codigo": CODIGO_PORTAL_INATIVO, "mensagem": MENSAGEM_PORTAL_INATIVO},
    )


async def exigir_processo_activo(processo: Optional[dict]) -> None:
    """Levanta o 403 do Portal inativo. `None` passa (não há o que bloquear)."""
    if await processo_esta_inativo(processo):
        logger.info(
            "[PORTAL-ESTADO] Processo %s em fase terminal (%s) — acesso recusado",
            (processo or {}).get("id"), (processo or {}).get("status"),
        )
        raise erro_portal_inativo()


async def escolher_processo_do_cliente(processos: Iterable[dict]) -> Optional[dict]:
    """Entre os processos (não eliminados) de um cliente, o que o Portal serve.

    Prefere o primeiro ACTIVO. Se nenhum for activo, bloqueia (levanta o 403):
    o cliente só fica sem Portal quando não tem nenhum processo em curso.
    Lista vazia → `None` (sem processo ainda: é o fluxo do onboarding).
    """
    processos = [p for p in processos if p]
    if not processos:
        return None
    fases = await carregar_fases()
    for processo in processos:
        if not estado_e_terminal(processo.get("status"), fases):
            return processo
    logger.info(
        "[PORTAL-ESTADO] Os %d processos do cliente estão em fase terminal — acesso recusado",
        len(processos),
    )
    raise erro_portal_inativo()


async def cortar_sessoes_em_tempo_real(process_id: str) -> int:
    """Fecha os WebSockets do Portal deste processo (4002, sem reconexão).

    Chamado pelo gancho de mudança de fase quando o processo passa a inativo.
    Corta NESTE worker; os outros descobrem no batimento seguinte do socket
    (`websocket_api_portal`), por isso não é a única defesa nem tem de ser.
    Nunca levanta: a mudança de fase já aconteceu.
    """
    try:
        from services.websocket_manager import manager
        from services.ws_client_identity import identidade_de_socket_do_cliente

        identidade = identidade_de_socket_do_cliente(process_id)
        sockets = list(manager.active_connections.get(identidade, ()))
        for socket in sockets:
            try:
                await socket.close(code=4002, reason="Processo inativo")
            except Exception as e:  # o cliente já se foi — não é um erro
                logger.debug("[PORTAL-ESTADO] close falhou: %s", e)
            manager.disconnect(socket)
        return len(sockets)
    except Exception as e:
        logger.warning(
            "[PORTAL-ESTADO] Não foi possível cortar os sockets do processo %s: %s",
            process_id, e,
        )
        return 0
