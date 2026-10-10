"""
====================================================================
O CLIENTE E A TAREFA PEDIDOS POR ID TÊM DE SER DA REDE DE QUEM PEDE
====================================================================
(D-31, Out 2026 — o que a adenda de RBAC deixou por varrer)

O QUE ESTAVA ABERTO
  As listagens de clientes e de tarefas isolam por rede desde o Lote 4/5;
  o PEDIDO POR ID não. `GET/PUT/DELETE /clients/{id}` e
  `GET/PUT/DELETE /tasks/{id}` (e as acções `complete`, `reopen`, `assign`,
  `link-process`…) faziam `find_one({"id": x})` e mais nada: o
  `get_current_user` da rota autoriza o VERBO, não o OBJECTO. Um
  consultor da Domus (ilha) que soubesse o id de um cliente da Power lia-o
  inteiro — com NIF e telefone já desencriptados — e podia editá-lo ou
  eliminá-lo em cascata.

POR QUE UMA DEPENDÊNCIA DE ROUTER (e não uma chamada em cada serviço)
  É a decisão do `process_scope_guard`: a pergunta «isto é da minha
  rede?» tem a mesma resposta para todas as rotas com o mesmo id no
  caminho, e escrevê-la em cada handler era garantir que o próximo a
  esquece. Como dependência do `APIRouter`, cobre também as rotas que
  alguém acrescente amanhã — e há um teste que falha se ela sair.

REGRAS
  * **404 e nunca 403**, com a MESMA mensagem de «não existe» — distinguir
    os dois confirma o id a quem adivinha;
  * o Master passa sem ler nada (não tem fronteira);
  * um id que não existe NÃO é recusado aqui: o handler responde o seu 404;
  * só actua em rotas com o id no caminho — as restantes (listagens,
    criação) têm as suas condições.

QUANDO UM CLIENTE É «DA MINHA REDE»  (qualquer um dos ramos)
  1. o carimbo do cliente (rede/empresa) cai no meu âmbito — o MESMO
     predicado das listagens (`documento_no_ambito`);
  2. **é da Pool**: sem carimbo nenhum, ainda sem processo e por
     reivindicar. É a regra do *claim-based routing* (`client_registered`):
     um registo público ainda não é de ninguém, e escondê-lo de quem o
     tem de reivindicar faria com que nunca fosse reivindicado;
  3. **é titular de um processo meu**. Este ramo existe porque
     `POST /clients` (criação manual) NÃO carimba o cliente — a ficha
     «Novo Cliente» de um utilizador de uma rede que não seja a de omissão
     nasce por carimbar — e o `ProcessDetails` carrega `GET /clients/{id}`
     do titular do processo. Sem este ramo, o cartão do cliente do próprio
     processo de quem o criou passava a dar 404. Para LER e EDITAR conta
     também o processo partilhado por Via Rápida (D-25: o convidado vê o
     processo, logo vê o titular); para tudo o resto (eliminar, atribuir,
     ligar, criar processo, reenviar acesso) só conta um processo DA MINHA
     rede — um convidado nunca elimina o cliente do dono.

QUANDO UMA TAREFA É «MINHA»  (qualquer um dos ramos)
  1. o carimbo da tarefa cai no meu âmbito;
  2. **atribuída a mim ou criada por mim** — a regra do `run_get_my_tasks`
     (uma tarefa pessoal não tem processo nem empresa, e quem a criou ou a
     recebeu nota-se se deixar de a conseguir abrir);
  3. pertence a um processo que eu vejo (inclui a rede convidada).

TODAS AS PROJECÇÕES LEVEM O CARIMBO
  Um `find_one` que alimente uma verificação de posse e deixe o carimbo de
  fora faz o documento contar como «legado» e a guarda ABRIR em vez de
  fechar (`PROJECCAO_DO_CARIMBO`).
====================================================================
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request

from database import db
from services.auth import get_current_user
from services.role_scope import utilizador_e_global
from services.tenant_network import (
    PROJECCAO_DO_CARIMBO,
    TenantScope,
    build_network_scope_condition,
    build_process_scope_condition,
    com_isolamento,
    documento_no_ambito,
    documento_sem_marca_de_tenant,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

ERRO_CLIENTE_NAO_ENCONTRADO = "Cliente não encontrado"
ERRO_TAREFA_NAO_ENCONTRADA = "Tarefa não encontrada"

PROJECCAO_DO_CLIENTE = {
    "_id": 0, "id": 1, "process_ids": 1, "lead_status": 1, **PROJECCAO_DO_CARIMBO,
}
PROJECCAO_DA_TAREFA = {
    "_id": 0, "id": 1, "process_id": 1, "assigned_to": 1, "created_by": 1,
    **PROJECCAO_DO_CARIMBO,
}

#: Nas rotas de um cliente, estes (método, forma do caminho) são os únicos
#: em que o processo PARTILHADO (rede convidada) basta para abrir o cliente.
#: Tudo o resto — eliminar, atribuir, ligar, criar processo — exige a rede
#: do dono.
_METODOS_QUE_ACEITAM_CONVIDADO = frozenset({"GET", "PUT"})
_CAMINHO_DA_FICHA = "/clients/{client_id}"


def cliente_e_da_pool(cliente: Optional[dict]) -> bool:
    """Registo público por reivindicar: sem carimbo, sem processo, não convertido."""
    cliente = cliente or {}
    if not documento_sem_marca_de_tenant(cliente):
        return False
    if cliente.get("process_ids"):
        return False
    return cliente.get("lead_status") in (None, "", "new")


def _ids(valor) -> set[str]:
    if isinstance(valor, (list, tuple, set)):
        return {str(v) for v in valor if v}
    return {str(valor)} if valor else set()


def tarefa_e_do_utilizador(tarefa: Optional[dict], user_id: str) -> bool:
    """Atribuída a mim ou criada por mim."""
    tarefa = tarefa or {}
    if not user_id:
        return False
    return str(tarefa.get("created_by") or "") == user_id or user_id in _ids(tarefa.get("assigned_to"))


async def _algum_processo_refere_o_cliente(client_id: str) -> bool:
    """Qualquer processo (de qualquer rede) tem este cliente como titular?

    O `process_ids` do cliente nem sempre está mantido — o vínculo vive no
    PROCESSO (`client_id`, `second_client_id`, `client_ids`). Um cliente
    antigo da Power, sem carimbo e sem `process_ids`, parece da Pool a quem
    só olha para o documento do cliente; esta pergunta é o que o impede de
    ser aberto pela Domus.
    """
    return bool(await db.processes.find_one(
        {"$or": [
            {"client_id": client_id},
            {"second_client_id": client_id},
            {"client_ids": client_id},
        ]},
        {"_id": 0, "id": 1},
    ))


async def _titular_de_um_processo_meu(
    client_id: str, scope: TenantScope, *, com_convidados: bool,
) -> bool:
    condicao = (
        build_process_scope_condition(scope) if com_convidados
        else build_network_scope_condition(scope)
    )
    consulta = com_isolamento(
        condicao,
        {"$or": [
            {"client_id": client_id},
            {"second_client_id": client_id},
            {"client_ids": client_id},
        ]},
    )
    return bool(await db.processes.find_one(consulta, {"_id": 0, "id": 1}))


async def cliente_no_ambito(
    client_id: str, user: dict, *, com_convidados: bool = False,
) -> Optional[bool]:
    """O cliente é da rede de quem pede? ``None`` se o id não existe."""
    cliente = await db.clients.find_one({"id": client_id}, PROJECCAO_DO_CLIENTE)
    if not cliente:
        return None
    if utilizador_e_global(user):
        return True

    scope = await resolve_tenant_scope(user)
    if documento_no_ambito(cliente, scope):
        return True
    if await _titular_de_um_processo_meu(client_id, scope, com_convidados=com_convidados):
        return True
    # A Pool é o último ramo: só se pergunta (e só custa uma consulta) para
    # o que não tem carimbo nenhum, e fecha-se se algum processo o refere.
    return cliente_e_da_pool(cliente) and not await _algum_processo_refere_o_cliente(client_id)


async def tarefa_no_ambito(task_id: str, user: dict) -> Optional[bool]:
    """A tarefa é da rede de quem pede? ``None`` se o id não existe."""
    tarefa = await db.tasks.find_one({"id": task_id}, PROJECCAO_DA_TAREFA)
    if not tarefa:
        return None
    if utilizador_e_global(user):
        return True
    if tarefa_e_do_utilizador(tarefa, str((user or {}).get("id") or "")):
        return True

    scope = await resolve_tenant_scope(user)
    if documento_no_ambito(tarefa, scope):
        return True

    process_id = tarefa.get("process_id")
    if process_id:
        visivel = com_isolamento(build_process_scope_condition(scope), {"id": process_id})
        return bool(await db.processes.find_one(visivel, {"_id": 0, "id": 1}))
    return False


def _aceita_convidado(request: Request) -> bool:
    rota = request.scope.get("route")
    caminho = getattr(rota, "path", "") or ""
    return (
        request.method in _METODOS_QUE_ACEITAM_CONVIDADO
        and caminho.endswith(_CAMINHO_DA_FICHA)
    )


async def exigir_cliente_no_ambito(
    request: Request, user: dict = Depends(get_current_user),
) -> None:
    """Dependência do router `/clients`: 404 se o `{client_id}` é de outra rede."""
    client_id = request.path_params.get("client_id")
    if not client_id:
        return
    if await cliente_no_ambito(
        client_id, user, com_convidados=_aceita_convidado(request),
    ) is False:
        logger.warning(
            "[CLIENTES] %s pediu %s %s, fora da sua rede.",
            (user or {}).get("id"), request.method, client_id,
        )
        raise HTTPException(status_code=404, detail=ERRO_CLIENTE_NAO_ENCONTRADO)


async def exigir_tarefa_no_ambito(
    request: Request, user: dict = Depends(get_current_user),
) -> None:
    """Dependência do router `/tasks`: 404 se o `{task_id}` é de outra rede."""
    task_id = request.path_params.get("task_id")
    if not task_id:
        return
    if await tarefa_no_ambito(task_id, user) is False:
        logger.warning(
            "[TAREFAS] %s pediu %s %s, fora da sua rede.",
            (user or {}).get("id"), request.method, task_id,
        )
        raise HTTPException(status_code=404, detail=ERRO_TAREFA_NAO_ENCONTRADA)
