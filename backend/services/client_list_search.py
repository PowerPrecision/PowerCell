"""GET /clients/search + GET /clients — pesquisa e listagem de clientes.

Extraído de `routes/clients.py`.
"""
from __future__ import annotations

import uuid
import logging
import asyncio
import copy
import re
import os
import unicodedata
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from database import db
from services.workflow_phases import fases_do_utilizador
from models.client import (
    Client, ClientCreate, ClientUpdate,
    ClientContact, ClientPersonalData,
    find_or_create_client_key,
    generate_portal_access_code,
)
from services.auth import get_effective_role
from models.auth import UserRole
from services.encryption import (
    encryption_service,
    encrypt_client_data,
    decrypt_client_data,
    decrypt_clients_list,
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
)
from services.process_service import get_next_process_number
from services.process_status import DELETED_STATUS_VALUES, INACTIVE_STATUSES
from services.s3_storage import s3_service
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, sanitize_url, log_sanitization_rejection,
)
from utils.search_filters import create_accent_insensitive_regex, build_multiword_search_filter
from services.tenant_network import (
    PROJECCAO_DO_CARIMBO,
    build_tenant_condition,
    com_isolamento,
)
from services.client_list_filters import (
    build_client_entity_query,
    client_doc_to_list_item,
)
from services.client_list_titulares import linhas_dos_titulares_secundarios
from services.client_window import so_o_que_a_janela_deixa_ver

logger = logging.getLogger(__name__)


#: O que a listagem precisa de cada processo. Uma só lista: os titulares
#: secundários (Bloco 1, ponto 6) leem o MESMO conjunto de campos.
PROJECCAO_DOS_PROCESSOS_DA_LISTAGEM = {
    "_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1,
    "personal_data": 1, "status": 1, "process_number": 1, "client_id": 1,
    "assigned_consultor_id": 1, "assigned_mediador_id": 1,
    "consultor_name": 1, "mediador_name": 1, "is_active": 1, "is_deleted": 1, "created_at": 1,
    "updated_at": 1, "prioridade": 1, "priority": 1,
    # A rede DONA decide o que é "terminado" (workflow por rede, D-6): o carimbo
    # vem do ponto único, não escrito à mão.
    **PROJECCAO_DO_CARIMBO,
    # Lote 7.2: a janela do visitante pergunta pelas redes convidadas de cada processo.
    "partner_network_ids": 1,
}


#: A mesma projecção SEM `personal_data`: ver `run_list_clients` (os dados pessoais só se lêem para a página).
PROJECCAO_LEVE_DOS_PROCESSOS_DA_LISTAGEM = {
    chave: valor for chave, valor in PROJECCAO_DOS_PROCESSOS_DA_LISTAGEM.items() if chave != "personal_data"
}


def _por_nome_do_cliente(processo: dict):
    """A ordem do `sort("client_name", 1)` do Mongo: sem nome primeiro, depois por ordem binária."""
    nome = processo.get("client_name")
    return (nome is not None, nome if isinstance(nome, str) else "")


#: Marca de trabalho numa linha: o processo cujos dados pessoais ainda estão por ler. Nunca sai da função.
CHAVE_DO_PROCESSO_DOS_DADOS = "_processo_dos_dados_pessoais"


async def _preencher_dados_pessoais(clients: list) -> list:
    """Lê os dados pessoais (UMA consulta) só dos processos de que as linhas da PÁGINA ainda precisam.

    Equivale ao que a linha sempre levou — o `personal_data` do primeiro processo do cliente —, mas
    sem trazer da base de dados o de todos os outros. As linhas com os dados já presentes (titulares
    secundários, que vêm do documento do cliente) não passam por aqui. Tira a marca de trabalho.
    """
    pendentes = {c[CHAVE_DO_PROCESSO_DOS_DADOS]: c for c in clients if c.get(CHAVE_DO_PROCESSO_DOS_DADOS)}
    if pendentes:
        docs = await db.processes.find(
            {"id": {"$in": list(pendentes)}}, {"_id": 0, "id": 1, "personal_data": 1},
        ).to_list(length=len(pendentes))
        por_id = {d["id"]: d.get("personal_data") or {} for d in docs if d.get("id")}
        for processo_id, linha in pendentes.items():
            pessoais = por_id.get(processo_id, {})
            linha["dados_pessoais"] = pessoais
            linha["nif"] = pessoais.get("nif")
    for c in clients:
        c.pop(CHAVE_DO_PROCESSO_DOS_DADOS, None)
    return clients


def _merge_entity_client_docs(
    clients: list,
    extra_docs: list,
    search: Optional[str] = None,
) -> list:
    """Copia fonte/tipo para as linhas existentes e acrescenta clientes sem processo."""
    if not extra_docs:
        return clients
    extra_by_id = {d["id"]: d for d in extra_docs if d.get("id")}
    present = {c.get("id") for c in clients if c.get("id")}
    search_lc = (search or "").strip().lower()

    for c in clients:
        extra = extra_by_id.get(c.get("id"))
        if not extra:
            continue
        if extra.get("fonte") and not c.get("fonte"):
            c["fonte"] = extra["fonte"]
        item = client_doc_to_list_item(extra)
        c["tipo_cliente"] = item["tipo_cliente"]

    for doc in extra_docs:
        cid = doc.get("id")
        if not cid or cid in present:
            continue
        if search_lc:
            blob = " ".join([
                str(doc.get("nome") or ""),
                str((doc.get("contacto") or {}).get("email") or ""),
                str((doc.get("dados_pessoais") or {}).get("nif") or ""),
            ]).lower()
            if search_lc not in blob:
                continue
        clients.append(client_doc_to_list_item(doc))
        present.add(cid)
    return clients


async def _enrich_clients_fonte(clients: list) -> list:
    """Preenche ``fonte`` / ``tipo_cliente`` a partir da colecção clients."""
    ids = [c.get("id") for c in clients if c.get("id")]
    if not ids:
        return clients
    docs = await db.clients.find(
        {"id": {"$in": ids}},
        {
            "_id": 0, "id": 1, "fonte": 1, "tipo": 1, "tipo_cliente": 1,
            "titular2_data": 1, "titular2_name": 1, "submitted_by_partner_name": 1,
        },
    ).to_list(length=None)
    by_id = {d["id"]: d for d in docs if d.get("id")}
    for c in clients:
        extra = by_id.get(c.get("id"))
        if not extra:
            continue
        if extra.get("fonte") and not c.get("fonte"):
            c["fonte"] = extra["fonte"]
        if extra.get("submitted_by_partner_name") and not c.get("parceiro_name"):
            c["parceiro_name"] = extra["submitted_by_partner_name"]
        if not c.get("tipo_cliente"):
            c["tipo_cliente"] = client_doc_to_list_item(extra)["tipo_cliente"]
    return clients

async def run_search_clients(
    q: str,
    user: dict,
    limit: int = 10
):
    """Pesquisa leve de clientes para autocomplete."""
    q = sanitize_string(q, max_length=200)

    simple_regex = {"$regex": re.escape(q), "$options": "i"}
    name_filter = build_multiword_search_filter(q, "nome")

    # Para email/NIF, usar pesquisa simples (contígua)
    or_conditions = [
        name_filter,
        {"contacto.email": simple_regex},
        {"dados_pessoais.nif": simple_regex},
    ]

    # PACOTE DG — excluir clientes eliminados (soft-delete) do autocomplete.
    query = com_isolamento(
        await build_tenant_condition(user),
        {"$or": or_conditions, "is_deleted": {"$ne": True}},
    )

    clients = await db.clients.find(
        query,
        {"_id": 0, "id": 1, "nome": 1, "contacto.email": 1, "contacto.telefone": 1, "dados_pessoais.nif": 1, "is_active": 1}
    ).sort("nome", 1).limit(limit).to_list(length=limit)

    results = [
        {
            "id": c.get("id"),
            "nome": c.get("nome"),
            "nif": c.get("dados_pessoais", {}).get("nif") if isinstance(c.get("dados_pessoais"), dict) else None,
            "email": c.get("contacto", {}).get("email") if isinstance(c.get("contacto"), dict) else None,
            "telefone": c.get("contacto", {}).get("telefone") if isinstance(c.get("contacto"), dict) else None,
            "is_active": c.get("is_active", True),
        }
        for c in clients
    ]

    results = decrypt_clients_list(results)

    return {"results": results}

async def _predicado_de_processo_activo(processos: list):
    """``e_activo(processo) -> bool`` decidido pelo MOTOR, não por uma lista cravada (D-6).

    Cada processo fecha segundo o workflow da rede DONA (um processo partilhado continua a
    significar em casa o que significa em casa). Eliminado nunca é activo. Se o motor não se
    deixar ler, cai no resíduo `INACTIVE_STATUSES` — e di-lo no log: um número de «carteira
    activa» que diverge do quadro tem de ter um aviso, não uma explicação por descobrir.
    """
    from services.portal_estado import estado_e_terminal
    from services.workflow_phases import chave_da_rede, fases_por_rede, rede_do_processo

    try:
        fases = await fases_por_rede(rede_do_processo(p) for p in processos)
    except Exception as exc:  # noqa: BLE001 — a listagem não pode cair por causa do motor
        logger.warning("[CLIENTES] Motor de workflow ilegível (%s): a usar a lista legada de fases fechadas.", exc)
        fases = None

    # `estado_e_terminal` reconstrói o conjunto de fases terminais a CADA chamada; com 20 mil processos
    # (duas chamadas cada) isso era mais de meio segundo só em fases. A resposta é uma função pura de
    # (fases da rede, estado): calcula-se uma vez por par — são meia dúzia de estados em duas ou três redes.
    memoria: dict[tuple, bool] = {}

    def e_activo(proc: dict) -> bool:
        if proc.get("is_deleted", False):
            return False
        if fases is None:
            return proc.get("status") not in INACTIVE_STATUSES
        chave = (chave_da_rede(rede_do_processo(proc)), proc.get("status"))
        terminal = memoria.get(chave)
        if terminal is None:
            terminal = estado_e_terminal(proc.get("status"), fases[chave[0]])
            memoria[chave] = terminal
        return not terminal

    return e_activo


def _so_processos_terminados(cliente: dict, terminais: set, ids_terminados: frozenset = frozenset()) -> bool:
    """O cliente tem processos e TODOS estão terminados (fase terminal do motor ou eliminados).

    `terminais` são nomes de fase; `ids_terminados` os processos que o MOTOR da rede dona fechou
    (a resposta exacta por processo, D-6). Sem processos não é histórico: é uma lead, e o ecrã de
    trabalho é onde ela é tratada.
    """
    processos = cliente.get("processes") or []
    if not processos:
        return False
    return all(
        bool(p.get("is_deleted")) or p.get("status") in terminais or p.get("id") in ids_terminados
        for p in processos
    )


#: Tamanho de página por omissão e tecto (P4). O tecto existe porque a lista agrupa processos em
#: memória e desencripta a página: uma página enorme é a lista lenta de volta.
TAMANHO_DA_PAGINA = 50
TAMANHO_MAXIMO = 200

#: Colunas por que o utilizador pode ordenar a lista (P4). O que não esteja aqui é ignorado.
CAMPOS_ORDENAVEIS = frozenset({"nome", "contacto", "nif", "process_count", "created_at", "updated_at"})
#: Das anteriores, as que vivem cifradas até à desencriptação da página.
CAMPOS_CIFRADOS_ORDENAVEIS = frozenset({"nif", "contacto"})

_PESO_DA_PRIORIDADE = {"alta": 3, "high": 3, "media": 2, "medium": 2, "baixa": 1, "low": 1}


def _valor_de_ordenacao(cliente: dict, campo: str):
    """O valor por que se ordena, ou ``None`` quando o cliente não tem nada nesse campo."""
    if campo == "nome":
        return (cliente.get("nome") or "").lower() or None
    if campo == "contacto":
        contacto = cliente.get("contacto") or {}
        return (str(contacto.get("email") or contacto.get("telefone") or "")).lower() or None
    if campo == "nif":
        pessoais = cliente.get("dados_pessoais") or {}
        return (str(pessoais.get("nif") or cliente.get("nif") or "")).lower() or None
    if campo == "process_count":
        return len(cliente.get("process_ids") or [])
    valor = cliente.get(campo)
    return str(valor) if valor else None


def ordenar_clientes(clients: list[dict], sort_field: Optional[str], sort_order: Optional[str]) -> list[dict]:
    """Ordena por prioridade (alta primeiro) e, dentro dela, pelo campo pedido.

    Sem campo válido devolve a lista como veio (já ordenada por prioridade/fase/nome). Quem não
    tem valor no campo vai SEMPRE para o fim, seja a ordem ascendente ou descendente: «sem NIF»
    no topo de uma ordenação descendente seria ruído.
    """
    campo = str(sort_field or "").strip()
    if campo not in CAMPOS_ORDENAVEIS:
        return clients
    descendente = str(sort_order or "asc").lower() == "desc"
    com_valor = [c for c in clients if _valor_de_ordenacao(c, campo) is not None]
    sem_valor = [c for c in clients if _valor_de_ordenacao(c, campo) is None]
    com_valor.sort(key=lambda c: _valor_de_ordenacao(c, campo), reverse=descendente)
    ordenados = com_valor + sem_valor
    # Estável: a prioridade manda, o campo desempata.
    ordenados.sort(key=lambda c: -_PESO_DA_PRIORIDADE.get(str(c.get("prioridade") or "").lower(), 0))
    return ordenados


async def _condicao_do_parceiro_nos_clientes(parceiro_id: Optional[str], tenant_condition: dict) -> Optional[dict]:
    """Condição sobre ``clients`` para «os clientes deste parceiro» (P4), ou ``None`` se não filtra.

    Dois caminhos, porque o parceiro entra por dois: a lead que ele submeteu
    (``submitted_by_partner_id``, no cliente) e o processo atribuído a ele
    (``assigned_parceiro_id``, no processo — por vezes posto à mão, sem passar pela lead). Só
    contam processos da rede de quem pergunta e não eliminados.
    """
    valor = str(parceiro_id or "").strip()
    if not valor or valor in ("all", "none"):
        return None
    processos = await db.processes.find(
        com_isolamento(tenant_condition, {"assigned_parceiro_id": valor, "is_deleted": {"$ne": True}}),
        {"_id": 0, "client_id": 1},
    ).to_list(length=None)
    ids = sorted({p["client_id"] for p in processos if p.get("client_id")})
    return {"$or": [{"submitted_by_partner_id": valor}, {"id": {"$in": ids}}]}


async def run_list_clients(
    user: dict,
    search: Optional[str] = None,
    has_active_process: Optional[bool] = None,
    show_all: Optional[bool] = True,
    status_filter: Optional[str] = None,
    assignment_filter: Optional[str] = None,
    indexacao_filter: Optional[str] = None,
    exclude_deleted: Optional[bool] = False,
    deleted_only: Optional[bool] = False,
    limit: Optional[int] = 100,
    skip: Optional[int] = 0,
    fonte: Optional[str] = None,
    tipo: Optional[str] = None,
    status: Optional[str] = None,
    historico: Optional[bool] = False,
    parceiro: Optional[str] = None,
    page: Optional[int] = None,
    size: Optional[int] = None,
    sort_field: Optional[str] = None,
    sort_order: Optional[str] = "asc",
):
    """
    Listar clientes.
    - show_all=True: Todos os utilizadores vêem todos os clientes da empresa
    - show_all=False: Utilizadores vêem apenas os seus clientes (atribuídos)
    
    Filtros disponíveis:
    - historico: o ecrã «Clientes Registados» é o ecrã de TRABALHO. Por omissão (`False`)
      não mostra os clientes cujos processos estão TODOS terminados (Concluído,
      Desistência… — as fases terminais DO MOTOR, nunca uma lista de nomes) nem
      eliminados; `True` mostra só esses (o separador «Histórico»). Um cliente sem
      nenhum processo (lead) continua no ecrã de trabalho. O `total_historico` da
      resposta diz quantos há, para o separador anunciar o que esconde.
    - status_filter: Filtrar por fase do processo
    - assignment_filter: 'both' (consultor+intermediario), 'consultor', 'intermediario', 'none'
    
    - parceiro (P4): só os clientes de UM parceiro — os que ele trouxe (`submitted_by_partner_id`)
      e os que têm um processo atribuído a esse parceiro. «Todos»/vazio/«none» não filtram.
    - page/size (P4): paginação. Com `page` a resposta traz também `page`, `size` e `pages`;
      sem ele vale o `limit`/`skip` de sempre. O tamanho da página tem tecto (`TAMANHO_MAXIMO`).
    - sort_field/sort_order (P4): a ordenação é do SERVIDOR — com a lista paginada, ordenar no
      browser ordenava só a página aberta. A prioridade continua a vir primeiro.

    Nota: Todos podem ver a lista de clientes para referência,
    mas apenas têm acesso total a processos que lhes estão atribuídos.
    """
    # Apply defaults for None values (handles empty string from query params)
    show_all = show_all if show_all is not None else True
    exclude_deleted = exclude_deleted if exclude_deleted is not None else False
    deleted_only = deleted_only if deleted_only is not None else False
    limit = limit if limit is not None else 100
    skip = skip if skip is not None else 0
    if page is not None:
        page = max(1, int(page))
        size = max(1, min(int(size or TAMANHO_DA_PAGINA), TAMANHO_MAXIMO))
        limit = size
        skip = (page - 1) * size

    user_role = user.get("role", "")
    user_id = user.get("id", "")
    user_email = user.get("email", "")
    
    # Sanitize search params used in MongoDB queries
    if search:
        search = sanitize_string(search, max_length=200)
    if status_filter:
        status_filter = sanitize_string(status_filter, max_length=50)
    if assignment_filter:
        assignment_filter = sanitize_string(assignment_filter, max_length=50)
    if fonte:
        fonte = sanitize_string(fonte, max_length=50)
    if tipo:
        tipo = sanitize_string(tipo, max_length=50)
    if status:
        status = sanitize_string(status, max_length=50)

    # PACOTE FK — filtros da entidade Cliente (independentes do processo).
    client_entity_query = build_client_entity_query(fonte=fonte, tipo=tipo, status=status)
    # DUAS condições, porque são DUAS colecções (D-25): `db.clients` não
    # tem partilha — a partilha é uma propriedade do PROCESSO —, logo a
    # consulta aos clientes continua na condição genérica e só a dos
    # processos inclui os partilhados. Usar a de processos nos clientes
    # era acrescentar um `$or` que nenhum documento satisfaz; usar a
    # genérica nos processos escondia ao parceiro a ficha que ele vê.
    tenant_condition = await build_tenant_condition(user)
    # «JANELA, NÃO PORTA» (Lote 6): esta lista é de CLIENTES, e as linhas saem dos processos. Com a
    # condição de processos (que conta a rede convidada) um processo partilhado trazia para aqui a
    # ficha de um cliente de OUTRA rede — nome, email, NIF, e todos os processos dele. O processo
    # partilhado continua visível onde é um processo (Kanban, lista de processos, detalhe); aqui
    # só entra o que é da minha rede.
    tenant_condition_processos = tenant_condition
    cond_parceiro = await _condicao_do_parceiro_nos_clientes(parceiro, tenant_condition)
    if cond_parceiro:
        client_entity_query = (
            {"$and": [client_entity_query, cond_parceiro]} if client_entity_query else cond_parceiro
        )
    matching_client_ids = None
    extra_client_docs: list[dict] = []
    if client_entity_query:
        extra_client_docs = await db.clients.find(
            com_isolamento(tenant_condition, client_entity_query),
            {
                "_id": 0, "id": 1, "nome": 1, "contacto": 1, "dados_pessoais": 1,
                "process_ids": 1, "fonte": 1, "created_at": 1, "updated_at": 1,
                "is_active": 1, "is_deleted": 1, "prioridade": 1, "priority": 1,
                "titular2_data": 1, "titular2_name": 1, "tipo": 1, "tipo_cliente": 1,
                "submitted_by_partner_name": 1,
            },
        ).to_list(length=None)
        matching_client_ids = [d["id"] for d in extra_client_docs if d.get("id")]
        if not matching_client_ids:
            workflow_statuses = await fases_do_utilizador(user)
            available_statuses = [
                {"name": s["name"], "label": s.get("label", s["name"])}
                for s in workflow_statuses
            ]
            return {
                "clients": [],
                "total": 0,
                "showing_all": bool(show_all),
                "available_statuses": available_statuses,
            }
    
    # Buscar workflow statuses para labels
    workflow_statuses = await fases_do_utilizador(user)
    status_map = {s["name"]: s for s in workflow_statuses}
    
    # Se show_all=True OU é admin/ceo/diretor, mostrar todos
    if show_all or user_role in ["master", "admin", "ceo", "diretor"]:
        # Mostrar todos os clientes da empresa
        process_query = {}
        # Os filtros que são do PROCESSO (e não do cliente): valem também para o
        # processo em que o cliente é 2.º titular (Bloco 1, ponto 6).
        filtros_de_processo: list[dict] = []
        
        if search:
            simple_regex = {"$regex": re.escape(search), "$options": "i"}
            name_filter = build_multiword_search_filter(search, "client_name")
            process_query = {
                "$or": [
                    name_filter,
                    {"client_email": simple_regex},
                    {"personal_data.nif": simple_regex}
                ]
            }

        # PACOTE FK — restringir processos aos clientes que casam fonte/tipo/estado
        if matching_client_ids is not None:
            id_filter = {"client_id": {"$in": matching_client_ids}}
            if process_query:
                process_query = {"$and": [process_query, id_filter]}
            else:
                process_query = id_filter
        
        # Filtro por fase/status
        if status_filter:
            filtros_de_processo.append({"status": status_filter})
            if process_query:
                process_query = {"$and": [process_query, {"status": status_filter}]}
            else:
                process_query = {"status": status_filter}
        
        # Filtro por tipo de atribuição
        if assignment_filter:
            assignment_query = None
            if assignment_filter == "both":
                # Tem consultor E intermediario
                assignment_query = {
                    "assigned_consultor_id": {"$exists": True, "$ne": None},
                    "assigned_mediador_id": {"$exists": True, "$ne": None}
                }
            elif assignment_filter == "consultor":
                # Tem apenas consultor (sem intermediario)
                assignment_query = {
                    "assigned_consultor_id": {"$exists": True, "$ne": None},
                    "$or": [
                        {"assigned_mediador_id": None},
                        {"assigned_mediador_id": {"$exists": False}}
                    ]
                }
            elif assignment_filter == "intermediario":
                # Tem apenas intermediario (sem consultor)
                assignment_query = {
                    "assigned_mediador_id": {"$exists": True, "$ne": None},
                    "$or": [
                        {"assigned_consultor_id": None},
                        {"assigned_consultor_id": {"$exists": False}}
                    ]
                }
            elif assignment_filter == "none":
                # Não tem nenhum atribuido
                assignment_query = {
                    "$and": [
                        {"$or": [
                            {"assigned_consultor_id": None},
                            {"assigned_consultor_id": {"$exists": False}}
                        ]},
                        {"$or": [
                            {"assigned_mediador_id": None},
                            {"assigned_mediador_id": {"$exists": False}}
                        ]}
                    ]
                }
            
            if assignment_query:
                filtros_de_processo.append(assignment_query)
                if process_query:
                    if "$and" in process_query:
                        process_query["$and"].append(assignment_query)
                    else:
                        process_query = {"$and": [process_query, assignment_query]}
                else:
                    process_query = assignment_query
        
        # Filtro por indexação
        if indexacao_filter:
            indexacao_filter = sanitize_string(indexacao_filter, max_length=50)
            indexacao_query = None
            if indexacao_filter == "assigned":
                # Tem indexação atribuída
                indexacao_query = {"assigned_indexacao_id": {"$exists": True, "$ne": None}}
            elif indexacao_filter == "unassigned":
                # Sem indexação atribuída
                indexacao_query = {
                    "$or": [
                        {"assigned_indexacao_id": None},
                        {"assigned_indexacao_id": {"$exists": False}}
                    ]
                }
            
            if indexacao_query:
                filtros_de_processo.append(indexacao_query)
                if process_query:
                    if "$and" in process_query:
                        process_query["$and"].append(indexacao_query)
                    else:
                        process_query = {"$and": [process_query, indexacao_query]}
                else:
                    process_query = indexacao_query
        
        # Filtro de eliminados (soft delete)
        # PACOTE DG — usar is_deleted como filtro principal (defesa em
        # profundidade: manter também o filtro de status="eliminado(s)" para
        # documentos legados com inconsistência de campos).
        # Fix: Normalize process status filters — a query anterior exigia
        # is_deleted=True E status=="eliminado" (singular) em simultâneo
        # (AND), pelo que um documento legado com status="eliminados"
        # (plural) nunca aparecia no filtro "Eliminados"; e o filtro
        # "Ativos" só excluía o singular, deixando passar o plural. Usa-se
        # agora $or para o caso "deleted" (basta UMA das duas fontes de
        # verdade) e $nin com ambas as variações para o caso "excluir".
        if deleted_only:
            deleted_query = {"$or": [
                {"is_deleted": True},
                {"status": {"$in": DELETED_STATUS_VALUES}},
            ]}
            filtros_de_processo.append(deleted_query)
            if process_query:
                if "$and" in process_query:
                    process_query["$and"].append(deleted_query)
                else:
                    process_query = {"$and": [process_query, deleted_query]}
            else:
                process_query = deleted_query
        elif exclude_deleted:
            deleted_query = {
                "is_deleted": {"$ne": True},
                "status": {"$nin": DELETED_STATUS_VALUES},
            }
            filtros_de_processo.append(deleted_query)
            if process_query:
                if "$and" in process_query:
                    process_query["$and"].append(deleted_query)
                else:
                    process_query = {"$and": [process_query, deleted_query]}
            else:
                process_query = deleted_query
        
        # Buscar todos os processos (clientes únicos)
        # NOTA: Não aplicar limit/skip ao nível dos processos pois isso limitaria
        # o número de clientes únicos. A paginação aplica-se ao resultado final.
        # FIX (Pacote K): adicionado is_deleted à projection para o cálculo de
        # "cliente ativo" poder filtrar processos eliminados.
        #
        # PERFORMANCE (Out 2026): esta lista agrupa TODOS os processos em memória e só depois pagina,
        # logo o que cada documento traz multiplica pelo tamanho da carteira. Dois cortes, sem mudar o
        # resultado: (1) os dados pessoais (`personal_data`, o bloco mais pesado do processo) só se lêem
        # para os clientes da PÁGINA — salvo se se ordena por NIF/contacto, que são cifrados e exigem a
        # lista inteira; (2) a ordem por nome faz-se aqui, estável, em vez de um sort do Mongo sobre a
        # colecção toda (sem índice, sobre documentos grandes).
        ordena_pelos_dados_pessoais = (sort_field or "") in CAMPOS_CIFRADOS_ORDENAVEIS
        projeccao = (
            PROJECCAO_DOS_PROCESSOS_DA_LISTAGEM if ordena_pelos_dados_pessoais
            else PROJECCAO_LEVE_DOS_PROCESSOS_DA_LISTAGEM
        )
        processes = await db.processes.find(
            com_isolamento(tenant_condition_processos, process_query), projeccao,
        ).to_list(length=None)
        processes.sort(key=_por_nome_do_cliente)
        processes = await so_o_que_a_janela_deixa_ver(processes, user)

        # Quem é 2.º titular ou co-titular também é cliente: cada processo com
        # titulares secundários contribui com uma linha por secundário, que
        # entra no mesmo acumulador do 1.º titular (Bloco 1, ponto 6).
        processes.extend(await linhas_dos_titulares_secundarios(
            tenant_condition_processos=tenant_condition_processos,
            tenant_condition_clientes=tenant_condition,
            filtros_de_processo=filtros_de_processo,
            # os dados pessoais destas linhas vêm do CLIENTE (o `personal_data` do processo é trocado)
            projeccao_do_processo=PROJECCAO_LEVE_DOS_PROCESSOS_DA_LISTAGEM,
            search=search,
            ids_permitidos=matching_client_ids,
        ))
        
        e_activo = await _predicado_de_processo_activo(processes)
        ids_terminados = frozenset(
            p.get("id") for p in processes if p.get("id") and not p.get("is_deleted", False) and not e_activo(p)
        )

        # Agrupar por cliente
        clients_map = {}
        for proc in processes:
            key = proc.get("client_id") or proc.get("client_name", "").lower().strip()
            if not key:
                continue
            
            # Determinar prioridade do processo (suporta campo PT e EN)
            proc_priority = proc.get("prioridade") or proc.get("priority") or ""
            
            if key not in clients_map:
                clients_map[key] = {
                    "id": proc.get("client_id") or proc.get("id"),
                    "nome": proc.get("client_name"),
                    "contacto": {
                        "email": proc.get("client_email"),
                        "telefone": proc.get("client_phone")
                    },
                    "dados_pessoais": proc.get("personal_data", {}),
                    "nif": proc.get("personal_data", {}).get("nif"),
                    # Projecção leve: os dados pessoais deste processo lêem-se depois, só se o cliente
                    # estiver na página (ver `_preencher_dados_pessoais`).
                    **({} if "personal_data" in proc else {CHAVE_DO_PROCESSO_DOS_DADOS: proc.get("id")}),
                    "process_ids": [],
                    "active_processes_count": 0,
                    "processes": [],  # Lista de processos com fase
                    "created_at": proc.get("created_at"),  # For sorting by date
                    "updated_at": proc.get("updated_at"),  # Last update date
                    "prioridade": proc_priority,  # Prioridade mais alta dos processos
                    "is_active": True,  # Valor por defeito; será ajustado abaixo com base nos processos
                }
            
            # Update created_at to earliest process date
            proc_date = proc.get("created_at")
            if proc_date and (not clients_map[key].get("created_at") or proc_date < clients_map[key]["created_at"]):
                clients_map[key]["created_at"] = proc_date
            
            # Update updated_at to latest date
            proc_updated = proc.get("updated_at")
            if proc_updated and (not clients_map[key].get("updated_at") or proc_updated > clients_map[key]["updated_at"]):
                clients_map[key]["updated_at"] = proc_updated
            
            # Adicionar informação do processo
            status_info = status_map.get(proc.get("status"), {})
            process_info = {
                "id": proc.get("id"),
                "process_number": proc.get("process_number"),
                "status": proc.get("status"),
                "status_label": status_info.get("label", proc.get("status")),
                "status_color": status_info.get("color", "#6B7280"),
                "is_active": proc.get("is_active", True),
                "is_deleted": bool(proc.get("is_deleted", False)),
                "consultor_name": proc.get("consultor_name"),
                "mediador_name": proc.get("mediador_name"),
                "prioridade": proc_priority,
                "titular": proc.get("titular", "titular1"),
            }
            clients_map[key]["processes"].append(process_info)
            clients_map[key]["process_ids"].append(proc.get("id"))
            
            # Determinar fase principal (primeiro processo ativo ou primeiro processo)
            if not clients_map[key].get("fase_principal"):
                clients_map[key]["fase_principal"] = process_info
            
            # Atualizar prioridade do cliente para a mais alta entre os seus processos
            PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baixa": 1}
            current_weight = PRIORITY_WEIGHT.get(clients_map[key].get("prioridade", ""), 0)
            new_weight = PRIORITY_WEIGHT.get(proc_priority, 0)
            if new_weight > current_weight:
                clients_map[key]["prioridade"] = proc_priority
            
            # FIX (Pacote K): Cálculo de "processo ativo" baseado em status + is_deleted
            # (anteriormente usava a flag is_active desnormalizada + lista de status
            # com typos "concluidos"/"arquivado"). Um processo conta como ativo se
            # NÃO estiver eliminado (is_deleted) e a fase NÃO for terminal NO WORKFLOW
            # DA REDE DONA (`_predicado_de_processo_activo`, D-6) — não uma lista cravada.
            if e_activo(proc):
                clients_map[key]["active_processes_count"] += 1
        
        # Determinar is_active de cada cliente com base nos seus processos
        # FIX (Pacote K): Um cliente é ativo se tiver pelo menos UM processo
        # onde is_deleted=False E status NOT IN (concluido, desistencia,
        # desistencias, eliminado). Anteriormente usava a flag is_active
        # desnormalizada, que pode dessincronizar do status real.
        for key in clients_map:
            all_processes = clients_map[key].get("processes", [])
            if all_processes:
                has_any_active = any(
                    not p.get("is_deleted", False)
                    and p.get("id") not in ids_terminados
                    for p in all_processes
                )
                clients_map[key]["is_active"] = has_any_active
            # Se não tem processos, mantém o valor por defeito (True)
        
        clients = list(clients_map.values())
        
        # Ordenação composta: 1ª por prioridade (alta primeiro), 2ª por fase do workflow, 3ª por nome
        status_order = {s["name"]: idx for idx, s in enumerate(workflow_statuses)}
        PRIORITY_SORT = {"alta": 3, "high": 3, "media": 2, "medium": 2, "baixa": 1, "low": 1}
        clients.sort(key=lambda c: (
            -PRIORITY_SORT.get(c.get("prioridade", ""), 0),
            status_order.get(c.get("fase_principal", {}).get("status"), 999),
            (c.get("nome") or "").lower()
        ))
        
        # Trabalho vs Histórico (Lote 4). O «Eliminados» é outra vista e não se mexe.
        total_historico = 0
        if not deleted_only:
            historicos = [c for c in clients if _so_processos_terminados(c, set(), ids_terminados)]
            total_historico = len(historicos)
            if historico:
                clients = historicos
            else:
                ids_do_historico = {id(c) for c in historicos}
                clients = [c for c in clients if id(c) not in ids_do_historico]

        # Filtrar por ter processo activo
        if has_active_process is not None:
            clients = [c for c in clients if (c["active_processes_count"] > 0) == has_active_process]

        clients = _merge_entity_client_docs(clients, extra_client_docs, search)

        # P4 — ordenar no servidor. NIF e contacto estão cifrados em repouso: ordenar por eles
        # exige desencriptar a lista INTEIRA (opt-in, é a coluna que o utilizador escolheu); nos
        # restantes campos desencripta-se só a página, como sempre.
        ja_desencriptados = False
        if (sort_field or "") in CAMPOS_CIFRADOS_ORDENAVEIS:
            clients = decrypt_clients_list(clients)
            ja_desencriptados = True
        clients = ordenar_clientes(clients, sort_field, sort_order)

        # Aplicar paginação ao resultado final (clientes, não processos)
        total_count = len(clients)
        clients = clients[skip:skip + limit]

        # Só a PÁGINA precisa da origem/tipo (`fonte`, `tipo_cliente`, parceiro) e dos dados pessoais:
        # nenhum deles entra na ordenação nem nos filtros (que são do Mongo). Antes, a origem lia-se
        # com um `$in` de TODOS os ids da carteira.
        clients = await _enrich_clients_fonte(clients)
        clients = await _preencher_dados_pessoais(clients)

        # Desencriptar dados sensíveis
        if not ja_desencriptados:
            clients = decrypt_clients_list(clients)

        # Adicionar lista de fases disponíveis para o filtro
        available_statuses = [{"name": s["name"], "label": s.get("label", s["name"])} for s in workflow_statuses]

        resposta = {
            "clients": clients,
            "total": total_count,
            "total_historico": total_historico,
            "showing_all": True,
            "available_statuses": available_statuses
        }
        if page is not None:
            resposta.update({"page": page, "size": limit, "pages": max(1, -(-total_count // limit))})
        return resposta
    
    # show_all=False - Mostrar apenas clientes do utilizador
    # Construir query baseada no papel do utilizador
    if user_role == "consultor":
        role_query = {
            "$or": [
                {"assigned_consultor_id": user_id},
                {"created_by": user_email}
            ]
        }
    elif user_role == "intermediario":
        role_query = {
            "$or": [
                {"assigned_mediador_id": user_id},
                {"created_by": user_email}
            ]
        }
    else:
        role_query = {"created_by": user_email}
    
    process_query = role_query
    filtros_de_processo = [role_query]
    
    if search:
        simple_regex = {"$regex": re.escape(search), "$options": "i"}
        name_filter = build_multiword_search_filter(search, "client_name")
        search_filter = {
            "$or": [
                name_filter,
                {"client_email": simple_regex},
                {"personal_data.nif": simple_regex}
            ]
        }
        process_query = {"$and": [process_query, search_filter]}
    
    if matching_client_ids is not None:
        id_filter = {"client_id": {"$in": matching_client_ids}}
        if "$and" in process_query:
            process_query["$and"].append(id_filter)
        else:
            process_query = {"$and": [process_query, id_filter]}
    
    # Filtro de eliminados (soft delete) - non-show_all path
    # PACOTE DG — usar is_deleted como filtro principal (defesa em
    # profundidade: manter também o filtro de status="eliminado(s)" para
    # documentos legados com inconsistência de campos).
    # Fix: Normalize process status filters — ver comentário equivalente
    # acima (show_all path) sobre o bug do AND estrito singular/plural.
    if deleted_only:
        deleted_query = {"$or": [
            {"is_deleted": True},
            {"status": {"$in": DELETED_STATUS_VALUES}},
        ]}
        filtros_de_processo.append(deleted_query)
        if "$and" in process_query:
            process_query["$and"].append(deleted_query)
        else:
            process_query = {"$and": [process_query, deleted_query]}
    elif exclude_deleted:
        deleted_query = {
            "is_deleted": {"$ne": True},
            "status": {"$nin": DELETED_STATUS_VALUES},
        }
        filtros_de_processo.append(deleted_query)
        if "$and" in process_query:
            process_query["$and"].append(deleted_query)
        else:
            process_query = {"$and": [process_query, deleted_query]}
    
    # Buscar processos e transformar em "clientes"
    # FIX (Pacote K): adicionado is_deleted à projection para o cálculo de
    # "cliente ativo" poder filtrar processos eliminados.
    processes = await db.processes.find(
        com_isolamento(tenant_condition, process_query),
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, 
         "personal_data": 1, "status": 1, "process_number": 1, "client_id": 1, "created_at": 1,
         "is_deleted": 1, **PROJECCAO_DO_CARIMBO,
         "prioridade": 1, "priority": 1, "partner_network_ids": 1}
    ).sort("client_name", 1).skip(skip).limit(limit).to_list(length=limit)
    processes = await so_o_que_a_janela_deixa_ver(processes, user)

    # Os titulares secundários dos processos que são meus (Bloco 1, ponto 6).
    processes.extend(await linhas_dos_titulares_secundarios(
        tenant_condition_processos=tenant_condition,
        tenant_condition_clientes=tenant_condition,
        filtros_de_processo=filtros_de_processo,
        projeccao_do_processo=PROJECCAO_DOS_PROCESSOS_DA_LISTAGEM,
        search=search,
        ids_permitidos=matching_client_ids,
    ))
    
    e_activo = await _predicado_de_processo_activo(processes)

    # Agrupar por cliente (usando client_id ou client_name como chave)
    clients_map = {}
    for proc in processes:
        key = proc.get("client_id") or proc.get("client_name", "").lower().strip()
        if not key:
            continue
        
        if key not in clients_map:
            # Determinar prioridade do processo (suporta campo PT e EN)
            proc_priority = proc.get("prioridade") or proc.get("priority") or ""
            
            clients_map[key] = {
                "id": proc.get("client_id") or f"process_{proc.get('id')}",
                "nome": proc.get("client_name"),
                "contacto": {
                    "email": proc.get("client_email"),
                    "telefone": proc.get("client_phone")
                },
                "dados_pessoais": proc.get("personal_data", {}),
                "nif": proc.get("personal_data", {}).get("nif"),
                "process_ids": [],
                "active_processes_count": 0,
                "created_at": proc.get("created_at"),
                "prioridade": proc_priority,
            }
        
        # Update created_at to earliest process date
        proc_date = proc.get("created_at")
        if proc_date and (not clients_map[key].get("created_at") or proc_date < clients_map[key]["created_at"]):
            clients_map[key]["created_at"] = proc_date
        
        clients_map[key]["process_ids"].append(proc.get("id"))
        
        # Atualizar prioridade do cliente para a mais alta
        proc_priority = proc.get("prioridade") or proc.get("priority") or ""
        PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baixa": 1}
        current_weight = PRIORITY_WEIGHT.get(clients_map[key].get("prioridade", ""), 0)
        new_weight = PRIORITY_WEIGHT.get(proc_priority, 0)
        if new_weight > current_weight:
            clients_map[key]["prioridade"] = proc_priority
        
        # FIX (Pacote K): Cálculo de "processo ativo" baseado em status + is_deleted
        # Activo = não eliminado e fase não terminal no workflow da rede dona (D-6).
        if e_activo(proc):
            clients_map[key]["active_processes_count"] += 1
    
    clients = list(clients_map.values())
    
    # M5 - Ordenar: 1ª por prioridade (alta primeiro), 2ª por nome
    PRIORITY_SORT = {"alta": 3, "high": 3, "media": 2, "medium": 2, "baixa": 1, "low": 1}
    clients.sort(key=lambda c: (
        -PRIORITY_SORT.get(c.get("prioridade", ""), 0),
        (c.get("nome") or "").lower()
    ))
    
    # Filtrar por ter processo activo
    if has_active_process is not None:
        clients = [c for c in clients if (c["active_processes_count"] > 0) == has_active_process]

    clients = _merge_entity_client_docs(clients, extra_client_docs, search)
    clients = await _enrich_clients_fonte(clients)
    
    # Desencriptar dados sensíveis
    clients = decrypt_clients_list(clients)
    
    return {
        "clients": clients,
        "total": len(clients),
        "showing_all": False
    }
