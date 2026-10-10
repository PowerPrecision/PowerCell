"""«Este cliente já tem um processo activo?» — o aviso de duplicação.

O PEDIDO (Bloco 1, ponto 5)
===========================
Ao adicionar um cliente a um processo, verificar se esse cliente já tem
algum processo activo associado e mostrar uma caixa de aviso/confirmação a
perguntar se quer continuar. O aviso é do ecrã; esta é a pergunta que ele
faz ao servidor.

AS TRÊS REGRAS
==============
1. **«Activo» é o do motor.** `nomes_terminais(carregar_fases())` — o que o
   administrador marcou como fase terminal — e não uma lista escrita à mão
   (D-6). Um processo `is_deleted` também não conta;
2. **O cliente está em TRÊS sítios do processo**: `client_id` (1.º
   titular), `second_client_id` (2.º) e `client_ids` (co-titulares N:M);
   mais os `clients.process_ids` do `link-process`. Procurar só no primeiro
   é o defeito do ponto 6 do mesmo bloco;
3. **A resposta respeita a rede.** O cliente tem de ser do âmbito de quem
   pergunta (senão 404, o MESMO de «não existe»: distinguir confirmava o
   id) e só se contam processos do âmbito — o de PROCESSOS, com a rede
   convidada de uma partilha. Um «já tem um processo activo» que
   atravesse redes confirma a existência de um cliente na ilha ao lado.

O QUE SAI
=========
Só o que o aviso precisa para dizer QUAL processo: número, fase (com o
rótulo do motor), em que posição o cliente está, o responsável e a data.
Nunca o documento — NIF, telefone, IBAN, palavras-passe de portais.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request

from database import db
from services.tenant_network import (
    build_tenant_condition,
    build_tenant_process_condition,
    com_isolamento,
)
from services.workflow_phases import carregar_fases, nomes_terminais

logger = logging.getLogger(__name__)

ERRO_CLIENTE_NAO_ENCONTRADO = "Cliente não encontrado"

#: Quantos processos se listam no aviso. O `total` é sempre o real.
LIMITE_DO_AVISO = 20

PROJECCAO = {
    "_id": 0,
    "id": 1,
    "process_number": 1,
    "status": 1,
    "client_id": 1,
    "second_client_id": 1,
    "client_ids": 1,
    "consultor_names": 1,
    "created_at": 1,
}


def _titular(processo: dict, client_id: str) -> str:
    """Em que posição este cliente está neste processo."""
    if processo.get("client_id") == client_id:
        return "titular1"
    if processo.get("second_client_id") == client_id:
        return "titular2"
    return "co_titular"


def _rotulos(fases: list[dict]) -> dict[str, str]:
    return {
        f["name"]: (f.get("label") or f["name"])
        for f in fases
        if isinstance(f, dict) and f.get("name")
    }


async def processos_activos_do_cliente(
    client_id: str,
    user: dict,
    request: Optional[Request] = None,
    *,
    exclude_process_id: Optional[str] = None,
    limite: int = LIMITE_DO_AVISO,
) -> dict:
    """Os processos activos de um cliente, dentro do âmbito de quem pergunta."""
    cliente = await db.clients.find_one(
        com_isolamento(await build_tenant_condition(user), {"id": client_id}),
        {"_id": 0, "id": 1, "nome": 1, "process_ids": 1},
    )
    if not cliente:
        raise HTTPException(status_code=404, detail=ERRO_CLIENTE_NAO_ENCONTRADO)

    vinculos: list[dict] = [
        {"client_id": client_id},
        {"second_client_id": client_id},
        {"client_ids": client_id},
    ]
    ligados = [p for p in (cliente.get("process_ids") or []) if isinstance(p, str) and p]
    if ligados:
        vinculos.append({"id": {"$in": ligados}})

    fases = await carregar_fases()
    condicoes: list[dict] = [
        {"$or": vinculos},
        {"status": {"$nin": nomes_terminais(fases)}},
        {"is_deleted": {"$ne": True}},
    ]
    if exclude_process_id:
        condicoes.append({"id": {"$ne": exclude_process_id}})

    consulta = com_isolamento(
        await build_tenant_process_condition(user), {"$and": condicoes},
    )

    total = await db.processes.count_documents(consulta)
    linhas = await (
        db.processes.find(consulta, PROJECCAO).sort("created_at", -1).limit(limite).to_list(limite)
    )

    rotulos = _rotulos(fases)
    processos = [
        {
            "id": p.get("id"),
            "process_number": p.get("process_number"),
            "status": p.get("status"),
            "status_label": rotulos.get(p.get("status")) or p.get("status"),
            "titular": _titular(p, client_id),
            "consultor_names": p.get("consultor_names") or [],
            "created_at": p.get("created_at"),
        }
        for p in linhas
    ]
    return {
        "client_id": client_id,
        "client_name": cliente.get("nome"),
        "total": total,
        "processos": processos,
    }


async def run_get_client_active_processes(
    client_id: str,
    user: dict,
    request: Optional[Request] = None,
    *,
    exclude_process_id: Optional[str] = None,
) -> dict:
    """Entrada da rota `GET /clients/{id}/active-processes`."""
    return await processos_activos_do_cliente(
        client_id, user, request, exclude_process_id=exclude_process_id,
    )
