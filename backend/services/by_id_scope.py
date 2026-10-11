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
    CAMPO_REDES_PARCEIRAS,
    PROJECCAO_DO_CARIMBO,
    TenantScope,
    build_network_scope_condition,
    build_process_scope_condition,
    com_isolamento,
    documento_no_ambito,
    documento_sem_marca_de_tenant,
    processo_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

ERRO_CLIENTE_NAO_ENCONTRADO = "Cliente não encontrado"
ERRO_TAREFA_NAO_ENCONTRADA = "Tarefa não encontrada"
ERRO_DOCUMENTO_NAO_ENCONTRADO = "Documento não encontrado"

PROJECCAO_DO_CLIENTE = {
    "_id": 0, "id": 1, "process_ids": 1, "lead_status": 1, **PROJECCAO_DO_CARIMBO,
}
#: O que a pergunta «este processo é meu?» precisa de um processo — o
#: carimbo, as redes convidadas e o `client_id` (para o id flexível).
PROJECCAO_DO_PROCESSO_FLEXIVEL = {
    "_id": 0, "id": 1, "client_id": 1, CAMPO_REDES_PARCEIRAS: 1, **PROJECCAO_DO_CARIMBO,
}
PROJECCAO_DO_DOCUMENTO = {"_id": 0, "id": 1, "process_id": 1, "client_id": 1}
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


# ════════════════════════════════════════════════════════════════════
#  DOCUMENTOS: o `{client_id}` é «flexível» e o `{doc_id}` é um registo
# ════════════════════════════════════════════════════════════════════
async def id_flexivel_no_ambito(flexible_id: str, user: dict) -> Optional[bool]:
    """O `{client_id}` de uma rota de documentos é da minha rede?

    O id é «flexível» (`document_process_resolve.resolve_process_from_flexible_id`):
    pode ser um PROCESSO, um CLIENTE ou o `client_id` de um processo. A ordem
    é a do resolvedor, porque a pergunta é «o que é que o handler vai abrir?».
    ``None`` se nada o identifica — o handler responde o seu 404.

    A rede CONVIDADA conta, tal como na guarda de documentos (D-26): quem vê
    o processo partilhado vê os documentos dele. O que o convidado pode FAZER
    com eles é decidido pelos serviços (`assert_can_upload_to_process`, etc.).
    """
    if not flexible_id:
        return None
    processo = await db.processes.find_one({"id": flexible_id}, PROJECCAO_DO_PROCESSO_FLEXIVEL)
    if processo:
        if utilizador_e_global(user):
            return True
        scope = await resolve_tenant_scope(user)
        return processo_no_ambito(processo, scope)

    cliente = await db.clients.find_one(
        {"id": flexible_id}, {**PROJECCAO_DO_CLIENTE, "process_ids": 1},
    )
    if cliente:
        if utilizador_e_global(user):
            return True
        if await cliente_no_ambito(flexible_id, user, com_convidados=True) is False:
            return False
        # O cliente é meu, mas o handler abre o PROCESSO dele: se for de
        # outra rede (homónimo, vínculo antigo) a resposta é a mesma.
        scope = await resolve_tenant_scope(user)
        ids = [i for i in (cliente.get("process_ids") or [])[:1] if i]
        candidato = None
        if ids:
            candidato = await db.processes.find_one({"id": ids[0]}, PROJECCAO_DO_PROCESSO_FLEXIVEL)
        if candidato is None:
            candidato = await db.processes.find_one(
                {"client_id": flexible_id}, PROJECCAO_DO_PROCESSO_FLEXIVEL,
            )
        return True if candidato is None else processo_no_ambito(candidato, scope)

    por_cliente = await db.processes.find_one(
        {"client_id": flexible_id}, PROJECCAO_DO_PROCESSO_FLEXIVEL,
    )
    if por_cliente:
        if utilizador_e_global(user):
            return True
        return processo_no_ambito(por_cliente, await resolve_tenant_scope(user))
    return None


async def documento_no_ambito_por_id(doc_id: str, user: dict) -> Optional[bool]:
    """O registo de documento `{doc_id}` é de um processo/cliente meu?

    Os registos de revisão da IA vivem em `document_metadata` e as regras de
    validade em `document_expiries`; ambos levam `process_id` e/ou
    `client_id`. **Um registo que não aponta para dono nenhum não se prova
    meu**: falha fechada para quem tem fronteira (o Master passa).
    """
    if not doc_id:
        return None
    registo = await db.document_metadata.find_one(
        {"$or": [{"id": doc_id}, {"doc_id": doc_id}]}, PROJECCAO_DO_DOCUMENTO,
    )
    if registo is None:
        registo = await db.document_expiries.find_one({"id": doc_id}, PROJECCAO_DO_DOCUMENTO)
    if registo is None:
        return None
    if utilizador_e_global(user):
        return True

    for chave in ("process_id", "client_id"):
        dono = registo.get(chave)
        if dono:
            resposta = await id_flexivel_no_ambito(str(dono), user)
            if resposta is not None:
                return resposta
    return False


# ════════════════════════════════════════════════════════════════════
#  O `process_id` que NÃO vem no caminho: corpo JSON e query string
# ════════════════════════════════════════════════════════════════════
ERRO_PROCESSO_NAO_ENCONTRADO = "Processo não encontrado"
ERRO_PROCESS_ID_INVALIDO = "process_id inválido"

#: Quantos processos do âmbito se enumeram para recortar uma pesquisa sem
#: `process_id`. Cortar errado é FECHADO (vê-se menos, nunca mais): o mesmo
#: tecto do `run_get_document_expiries`.
LIMITE_DE_PROCESSOS_NO_AMBITO = 5000

_METODOS_COM_CORPO = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def _process_id_do_corpo(request: Request):
    """O `process_id` do corpo JSON, ou ``None`` se não há corpo JSON.

    Só lê JSON: o upload multipart não pode ser carregado para memória por
    uma guarda (o ficheiro inteiro ficava em RAM antes do handler). Um corpo
    ilegível passa — o FastAPI responde o 422 dele.
    """
    if request.method not in _METODOS_COM_CORPO:
        return None
    if "json" not in (request.headers.get("content-type") or "").lower():
        return None
    try:
        corpo = await request.json()
    except Exception:  # noqa: BLE001 — corpo ilegível: o 422 é do FastAPI
        return None
    return corpo.get("process_id") if isinstance(corpo, dict) else None


async def exigir_process_id_do_pedido_no_ambito(
    request: Request, user: dict = Depends(get_current_user),
) -> None:
    """Dependência do router `/documents`: o `process_id` do CORPO ou da QUERY.

    O `{process_id}` do caminho tem a sua (`exigir_processo_no_ambito`); estas
    rotas — `search`, `confirm-upload`, `generate-upload-url`,
    `check-move-conflict`, `check-upload-conflict`, `expiry`, `categories` —
    levam o id noutro sítio e passavam por baixo de qualquer dependência de
    caminho. 404 igual ao de «não existe»; id inexistente passa (o handler
    responde o seu 404).

    **Um `process_id` que não é texto é recusado (400)**, não ignorado: os
    handlers fazem `find_one({"id": process_id})` e um `{"$ne": null}`
    devolvia o primeiro processo de QUALQUER rede — a guarda a ignorar o
    valor era a porta aberta para a contornar.
    """
    candidatos = [request.query_params.get("process_id"), await _process_id_do_corpo(request)]
    for process_id in candidatos:
        if process_id is None or process_id == "":
            continue
        if not isinstance(process_id, str):
            raise HTTPException(status_code=400, detail=ERRO_PROCESS_ID_INVALIDO)
        if await id_flexivel_no_ambito(process_id, user) is False:
            logger.warning(
                "[DOCUMENTOS] %s pediu %s %s (process_id %s no pedido), fora da sua rede.",
                (user or {}).get("id"), request.method, request.url.path, process_id,
            )
            raise HTTPException(status_code=404, detail=ERRO_PROCESSO_NAO_ENCONTRADO)


async def ids_de_processos_no_ambito(user: dict) -> Optional[list[str]]:
    """Os ids dos processos que `user` vê — ``None`` para o Master (sem fronteira).

    Serve as pesquisas que não trazem `process_id`: sem este recorte
    percorriam os metadados de documentos de TODAS as redes (e devolviam
    URLs pré-assinados). Conta a rede convidada. Um utilizador sem âmbito
    determinável recebe ``[]`` — nada, nunca «tudo».
    """
    if utilizador_e_global(user):
        return None
    scope = await resolve_tenant_scope(user)
    visiveis = await db.processes.find(
        build_process_scope_condition(scope), {"_id": 0, "id": 1},
    ).to_list(LIMITE_DE_PROCESSOS_NO_AMBITO)
    if len(visiveis) >= LIMITE_DE_PROCESSOS_NO_AMBITO:
        logger.warning(
            "[DOCUMENTOS] âmbito de %s cortado nos %d processos.",
            (user or {}).get("id"), LIMITE_DE_PROCESSOS_NO_AMBITO,
        )
    return [p["id"] for p in visiveis if p.get("id")]


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


async def exigir_alvo_do_documento_no_ambito(
    request: Request, user: dict = Depends(get_current_user),
) -> None:
    """Dependência do router `/documents`: 404 se o `{client_id}` ou o
    `{doc_id}` do caminho é de outra rede.

    O `{process_id}` do caminho tem a sua dependência (`exigir_processo_no_ambito`).
    Um id que não existe passa: o handler responde o seu 404. A resposta é
    sempre a de «não existe» — o 403 antigo das rotas de leitura confirmava
    que o cliente existia.
    """
    client_id = request.path_params.get("client_id")
    if client_id and await id_flexivel_no_ambito(client_id, user) is False:
        logger.warning(
            "[DOCUMENTOS] %s pediu %s %s (cliente/processo %s), fora da sua rede.",
            (user or {}).get("id"), request.method, request.url.path, client_id,
        )
        raise HTTPException(status_code=404, detail=ERRO_CLIENTE_NAO_ENCONTRADO)

    doc_id = request.path_params.get("doc_id")
    if doc_id and await documento_no_ambito_por_id(doc_id, user) is False:
        logger.warning(
            "[DOCUMENTOS] %s pediu %s %s (documento %s), fora da sua rede.",
            (user or {}).get("id"), request.method, request.url.path, doc_id,
        )
        raise HTTPException(status_code=404, detail=ERRO_DOCUMENTO_NAO_ENCONTRADO)
