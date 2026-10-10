"""Os titulares SECUNDÁRIOS na listagem de clientes (Bloco 1, ponto 6).

O DEFEITO
=========
`run_list_clients` constrói a lista a partir dos PROCESSOS e agrupa por
`proc["client_id"]` — só o 1.º titular. Quem é 2.º titular
(`second_client_id`) ou co-titular (`client_ids`) não tem linha por esse
processo, o que dá duas consequências:

1. quem é APENAS 2.º titular não aparece em lista nenhuma;
2. quem é 1.º titular num processo e 2.º noutro desaparece da lista de
   activos quando o de 1.º titular é anulado: o processo de 2.º titular,
   que continua activo, é contado na linha do OUTRO cliente.

COMO SE CORRIGE
===============
Cada processo com titulares secundários contribui com **uma linha por
secundário**, construída a partir do DOCUMENTO DO CLIENTE (nome, contacto,
NIF — os do processo são os do 1.º titular) e entra no MESMO acumulador do
1.º titular: o `client_id` dessa linha é o do secundário. Assim as
contagens, o filtro «tem processo activo» e a fase principal passam a contar
os dois papéis sem código novo, e quem é titular nos dois papéis continua a
ser UMA linha com os dois processos.

AS REGRAS
=========
1. **Os filtros do PROCESSO valem para o processo do secundário** (fase,
   atribuição, indexação, eliminados): o processo é o mesmo.
2. **Os filtros do CLIENTE valem para o cliente secundário** (pesquisa,
   origem/tipo/estado): são sobre quem aparece na linha.
3. **A rede**: o documento do secundário lê-se com a condição de CLIENTES
   do utilizador. Um `second_client_id` que aponte para outra rede não
   gera linha — e o nome dele não sai.
4. **Um cliente eliminado não volta pela porta do 2.º titular.**
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from database import db
from services.tenant_network import com_isolamento
from utils.search_filters import build_multiword_search_filter

logger = logging.getLogger(__name__)

#: Processos que TÊM titulares além do 1.º. `client_ids` inclui sempre o
#: 1.º titular, logo «tem alguém mais» é «tem pelo menos DOIS elementos».
CONDICAO_TEM_TITULAR_SECUNDARIO: dict = {
    "$or": [
        {"second_client_id": {"$nin": [None, ""]}},
        {"client_ids.1": {"$exists": True}},
    ]
}

#: Os campos do cliente que a linha precisa (os mesmos do 1.º titular).
PROJECCAO_DO_CLIENTE: dict = {
    "_id": 0, "id": 1, "nome": 1, "contacto": 1, "dados_pessoais": 1,
    "is_deleted": 1,
}


def ids_dos_titulares_secundarios(processo: dict) -> list[str]:
    """Os clientes de um processo que NÃO são o 1.º titular, sem repetidos."""
    principal = processo.get("client_id")
    candidatos = [processo.get("second_client_id"), *(processo.get("client_ids") or [])]
    vistos: dict[str, None] = {}
    for candidato in candidatos:
        if isinstance(candidato, str) and candidato and candidato != principal:
            vistos[candidato] = None
    return list(vistos)


def titular_do_cliente(processo: dict, client_id: str) -> str:
    """Em que posição o cliente está neste processo."""
    if processo.get("client_id") == client_id:
        return "titular1"
    if processo.get("second_client_id") == client_id:
        return "titular2"
    return "co_titular"


def _condicao_de_pesquisa(search: str) -> dict:
    simples = {"$regex": re.escape(search), "$options": "i"}
    return {
        "$or": [
            build_multiword_search_filter(search, "nome"),
            {"contacto.email": simples},
            {"dados_pessoais.nif": simples},
        ]
    }


async def linhas_dos_titulares_secundarios(
    *,
    tenant_condition_processos: dict,
    tenant_condition_clientes: dict,
    filtros_de_processo: list[dict],
    projeccao_do_processo: dict,
    search: Optional[str] = None,
    ids_permitidos: Optional[list[str]] = None,
) -> list[dict]:
    """Processos «vistos» pelos titulares secundários, prontos para o acumulador.

    Devolve cópias dos processos com `client_id`, `client_name`,
    `client_email`, `client_phone` e `personal_data` TROCADOS pelos do
    secundário, e `titular` a dizer a posição — para o acumulador da
    listagem os tratar como mais um processo desse cliente.

    Nunca levanta: se a pesquisa falhar, a listagem continua sem os
    secundários (com `warning`) — é o degradado que existia antes.
    """
    try:
        condicoes = [CONDICAO_TEM_TITULAR_SECUNDARIO, *filtros_de_processo]
        processos = await db.processes.find(
            com_isolamento(tenant_condition_processos, {"$and": condicoes}),
            {**projeccao_do_processo, "second_client_id": 1, "client_ids": 1},
        ).to_list(length=None)
        if not processos:
            return []

        ids = list(dict.fromkeys(
            cid for p in processos for cid in ids_dos_titulares_secundarios(p)
        ))
        if ids_permitidos is not None:
            ids = [i for i in ids if i in set(ids_permitidos)]
        if not ids:
            return []

        filtros_do_cliente: list[dict] = [
            {"id": {"$in": ids}},
            {"is_deleted": {"$ne": True}},
        ]
        if search:
            filtros_do_cliente.append(_condicao_de_pesquisa(search))
        clientes = await db.clients.find(
            com_isolamento(tenant_condition_clientes, {"$and": filtros_do_cliente}),
            PROJECCAO_DO_CLIENTE,
        ).to_list(length=None)
        por_id = {c["id"]: c for c in clientes if c.get("id")}
    except Exception as exc:
        logger.warning(
            "[CLIENTES] Falha a juntar os titulares secundários à listagem (%s); "
            "a lista segue só com os 1.º titulares.", exc,
        )
        return []

    linhas: list[dict[str, Any]] = []
    for processo in processos:
        for cid in ids_dos_titulares_secundarios(processo):
            cliente = por_id.get(cid)
            if not cliente:
                continue
            contacto = cliente.get("contacto") or {}
            linhas.append({
                **processo,
                "client_id": cid,
                "client_name": cliente.get("nome"),
                "client_email": contacto.get("email"),
                "client_phone": contacto.get("telefone"),
                "personal_data": cliente.get("dados_pessoais") or {},
                "titular": titular_do_cliente(processo, cid),
            })
    return linhas
