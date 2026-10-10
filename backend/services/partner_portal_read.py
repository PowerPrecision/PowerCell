"""
====================================================================
PORTAL DO PARCEIRO — LEITURA: painel, lista, detalhe (V1)
====================================================================
Tudo o que o parceiro LÊ passa por aqui, e tudo parte de duas condições
(`partner_visibility.condicao_de_processos` / `condicao_de_leads`): não
há uma terceira maneira de chegar a um processo ou a um cliente.

UM «CASO» É UM PROCESSO OU UMA LEAD
  O parceiro não distingue «cliente» de «processo»: traz um negócio e
  acompanha-o. Uma lead (cliente sem processo) vive em `db.clients`; no dia
  em que a equipa abre o processo, a lead deixa de o ser e o caso passa a
  aparecer como processo (a herança de `assigned_parceiro_id` está em
  `partner_attribution`). O `id` de uma lead e o do processo seguinte são
  diferentes — o ecrã navega pelo `kind` + `id` que recebe.

A COMUNICAÇÃO SÃO OS PEDIDOS DE DOCUMENTOS
  Não há chat. O consultor pede um documento (a nota que escreve é a que o
  cliente também lê) e o parceiro vê o mesmo pedido, com o mesmo estado, e
  responde com o ficheiro. `pedidos` no detalhe são esses pedidos; nada
  mais da equipa sai daqui (notas internas, histórico, atribuições).

FICHEIROS: O QUE O PARCEIRO ENVIOU E O QUE O CLIENTE ENVIOU
  A pasta documental é do cliente; a visibilidade é do FICHEIRO
  (`ficheiro_e_visivel`). E o parceiro nunca nomeia uma chave S3: pede por
  `file_id` e é o servidor quem a resolve — a classe de ataque do Incidente
  P0 (a chave vem do corpo do pedido) não tem por onde entrar.
====================================================================
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.document_portal_counts import parse_expected_count
from services.document_portal_request import (
    PORTAL_REQUEST_SOURCES,
    build_portal_requests_query,
    clientes_do_processo,
)
from services.partner_visibility import (
    ESTADOS_PENDENTES,
    ETAPA_CONCLUIDO,
    ETAPA_LEAD,
    ETAPAS,
    ORIGEM_DO_PARCEIRO,
    PROJECCAO_DA_LEAD,
    PROJECCAO_DO_PROCESSO,
    ROTULOS_DAS_ETAPAS,
    condicao_de_leads,
    condicao_de_processos,
    contagem_do_funil,
    dto_da_lead,
    dto_do_processo,
    etapa_de_um_estado,
    ficheiro_e_visivel,
    filtrar_casos,
    ordenar_por_actividade,
    quem_enviou,
    taxa_de_conversao,
)
from services.portal_doc_categories import DOCUMENT_CATEGORY_MAP
from services.portal_status_helpers import nota_do_pedido, rotulo_do_pedido
from services.workflow_phases import carregar_fases

logger = logging.getLogger(__name__)

#: Um parceiro tem dezenas de casos, não milhares. O tecto existe para que
#: um dado estranho não transforme a lista num varrimento; se for atingido
#: diz-se no log (e o ecrã pagina o que recebe).
LIMITE_DE_CASOS = 2000
TAMANHO_DE_PAGINA_MAXIMO = 50
TAMANHO_DE_PAGINA_POR_OMISSAO = 20

ERRO_CASO_NAO_ENCONTRADO = "Caso não encontrado."


@dataclass(frozen=True)
class Caso:
    """O que o parceiro está a olhar: um processo ou uma lead."""

    tipo: str  # "process" | "lead"
    id: str
    process: Optional[dict]
    client: Optional[dict]

    @property
    def e_processo(self) -> bool:
        return self.tipo == "process"

    @property
    def client_id(self) -> Optional[str]:
        if self.client and self.client.get("id"):
            return self.client["id"]
        return (self.process or {}).get("client_id")


# ════════════════════════════════════════════════════════════════════
#  CARREGAR CASOS
# ════════════════════════════════════════════════════════════════════
async def _carregar_processos(partner: dict) -> list[dict]:
    processos = await db.processes.find(
        condicao_de_processos(partner), PROJECCAO_DO_PROCESSO
    ).to_list(LIMITE_DE_CASOS)
    if len(processos) >= LIMITE_DE_CASOS:
        logger.warning("[PARCEIRO] %s atingiu o tecto de %d processos.", partner.get("id"), LIMITE_DE_CASOS)
    return processos


async def _carregar_leads(partner: dict) -> list[dict]:
    return await db.clients.find(
        condicao_de_leads(partner), PROJECCAO_DA_LEAD
    ).to_list(LIMITE_DE_CASOS)


def _sem_processo() -> list[dict]:
    return [{"process_id": None}, {"process_id": ""}, {"process_id": {"$exists": False}}]


async def _pedidos_pendentes_por_caso(processos: list[dict], leads: list[dict]) -> dict[str, int]:
    """id do caso → nº de pedidos de documentos por satisfazer.

    Uma só consulta: os pedidos vivem ligados ao processo OU, antes de ele
    existir (registo público, Sala de Triagem), só ao cliente — as duas
    pontas contam, como na aba Documentos do CRM.
    """
    ids_de_processo = [p["id"] for p in processos if p.get("id")]
    cliente_para_caso: dict[str, str] = {}
    for p in processos:
        for cid in clientes_do_processo(p):
            cliente_para_caso.setdefault(cid, p["id"])
    for lead in leads:
        if lead.get("id"):
            cliente_para_caso.setdefault(lead["id"], lead["id"])

    ramos: list[dict] = []
    if ids_de_processo:
        ramos.append({"process_id": {"$in": ids_de_processo}})
    if cliente_para_caso:
        ramos.append({"client_id": {"$in": list(cliente_para_caso)}, "$or": _sem_processo()})
    if not ramos:
        return {}

    consulta = {
        "status": {"$in": list(ESTADOS_PENDENTES)},
        "$and": [
            {"$or": ramos},
            {"$or": [
                {"source": {"$in": list(PORTAL_REQUEST_SOURCES)}},
                {"source": {"$exists": False}},
            ]},
        ],
    }
    contagem: dict[str, int] = {}
    docs = await db.documents.find(consulta, {"_id": 0, "process_id": 1, "client_id": 1}).to_list(10000)
    for doc in docs:
        caso = doc.get("process_id") or cliente_para_caso.get(doc.get("client_id") or "")
        if caso:
            contagem[caso] = contagem.get(caso, 0) + 1
    return contagem


async def _casos_com_dto(partner: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(dtos de todos os casos, processos crus, leads cruas)."""
    processos, leads, fases = await _carregar_processos(partner), await _carregar_leads(partner), await carregar_fases()
    pendentes = await _pedidos_pendentes_por_caso(processos, leads)

    dtos = [
        dto_do_processo(p, etapa_de_um_estado(p.get("status"), fases), pedidos_pendentes=pendentes.get(p["id"], 0))
        for p in processos
    ]
    dtos += [dto_da_lead(c, pedidos_pendentes=pendentes.get(c["id"], 0)) for c in leads]
    return ordenar_por_actividade(dtos), processos, leads


# ════════════════════════════════════════════════════════════════════
#  PAINEL, LISTA
# ════════════════════════════════════════════════════════════════════
async def run_get_dashboard(partner: dict) -> dict:
    dtos, _, _ = await _casos_com_dto(partner)
    funil = contagem_do_funil(
        (d["etapa"] for d in dtos if d["kind"] == "process"),
        sum(1 for d in dtos if d["kind"] == "lead"),
    )
    return {
        "funil": [
            {"etapa": e, "label": ROTULOS_DAS_ETAPAS[e], "total": funil[e]}
            for e in ETAPAS
            # «Em curso» só aparece quando existe: é o resíduo, não uma etapa
            # do negócio, e uma coluna a zero para sempre é ruído.
            if e != "em_curso" or funil[e] > 0
        ],
        "total_de_casos": len(dtos),
        "escriturados": funil[ETAPA_CONCLUIDO],
        "leads": funil[ETAPA_LEAD],
        "taxa_de_conversao": taxa_de_conversao(funil),
        "pedidos_pendentes": sum(d["pedidos_pendentes"] for d in dtos),
    }


async def run_list_cases(
    partner: dict,
    *,
    etapa: Optional[str] = None,
    pesquisa: Optional[str] = None,
    page: int = 1,
    size: int = TAMANHO_DE_PAGINA_POR_OMISSAO,
) -> dict:
    if etapa and etapa not in ETAPAS:
        raise HTTPException(status_code=400, detail="Etapa inválida.")
    size = max(1, min(int(size or TAMANHO_DE_PAGINA_POR_OMISSAO), TAMANHO_DE_PAGINA_MAXIMO))
    page = max(1, int(page or 1))

    dtos, _, _ = await _casos_com_dto(partner)
    filtrados = filtrar_casos(dtos, etapa=etapa, pesquisa=pesquisa)
    total = len(filtrados)
    inicio = (page - 1) * size
    return {
        "items": filtrados[inicio: inicio + size],
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


# ════════════════════════════════════════════════════════════════════
#  RESOLVER UM CASO — o ÚNICO caminho do id ao documento
# ════════════════════════════════════════════════════════════════════
async def resolver_caso(partner: dict, case_id: str) -> Caso:
    """O caso pedido, se for deste parceiro. **404 igual** para alheio e
    inexistente (nunca 403: seria um directório de ids)."""
    case_id = str(case_id or "").strip()
    if case_id:
        processo = await db.processes.find_one(
            {"$and": [{"id": case_id}, condicao_de_processos(partner)]}, PROJECCAO_DO_PROCESSO
        )
        if processo:
            cliente = None
            if processo.get("client_id"):
                cliente = await db.clients.find_one(
                    {"id": processo["client_id"]}, {"_id": 0, "id": 1, "nome": 1, "s3_folder": 1}
                )
            return Caso("process", processo["id"], processo, cliente)

        lead = await db.clients.find_one(
            {"$and": [{"id": case_id}, condicao_de_leads(partner)]}, PROJECCAO_DA_LEAD
        )
        if lead:
            return Caso("lead", lead["id"], None, lead)
    raise HTTPException(status_code=404, detail=ERRO_CASO_NAO_ENCONTRADO)


# ════════════════════════════════════════════════════════════════════
#  PEDIDOS E FICHEIROS DE UM CASO
# ════════════════════════════════════════════════════════════════════
def _consulta_de_pedidos(caso: Caso) -> dict:
    if caso.e_processo:
        return build_portal_requests_query(caso.id, clientes_do_processo(caso.process))
    return {
        "client_id": caso.id,
        "$or": _sem_processo(),
        "$and": [{"$or": [
            {"source": {"$in": list(PORTAL_REQUEST_SOURCES)}},
            {"source": {"$exists": False}},
        ]}],
    }


def _e_pedido(doc: dict) -> bool:
    """Pedido da equipa (ou da checklist) — por oposição a um envio solto."""
    return doc.get("source") not in ("client_portal", ORIGEM_DO_PARCEIRO)


def _categoria_em_texto(doc: dict) -> str:
    cat = doc.get("category") or "Outros"
    if isinstance(cat, dict):
        cat = cat.get("value", cat.get("label", "Outros"))
    return cat if isinstance(cat, str) else str(cat)


async def _documentos_do_caso(caso: Caso) -> list[dict]:
    docs = await db.documents.find(_consulta_de_pedidos(caso), {"_id": 0, "file_content": 0}).to_list(2000)
    return docs


def _ficheiros_de(doc: dict, partner_id: str) -> list[dict]:
    """Os ficheiros VISÍVEIS de um documento (pedido ou envio solto)."""
    pedido = doc.get("id")
    encontrados: list[dict] = []
    anexos = doc.get("attached_files") or []
    for entrada in anexos:
        if not isinstance(entrada, dict) or not entrada.get("s3_path"):
            continue
        if not ficheiro_e_visivel(entrada.get("uploaded_by"), partner_id):
            continue
        encontrados.append({
            "id": entrada.get("file_id") or f"{pedido}:{entrada['s3_path']}",
            "filename": entrada.get("original_filename") or entrada.get("filename"),
            "file_size": entrada.get("file_size"),
            "content_type": entrada.get("content_type"),
            "uploaded_at": entrada.get("uploaded_at"),
            "uploaded_by": entrada.get("uploaded_by"),
            "s3_path": entrada["s3_path"],
            "request_id": pedido if _e_pedido(doc) else None,
        })
    if not anexos and doc.get("s3_path") and ficheiro_e_visivel(doc.get("uploaded_by"), partner_id):
        encontrados.append({
            "id": doc.get("id"),
            "filename": doc.get("original_filename") or doc.get("filename"),
            "file_size": doc.get("file_size"),
            "content_type": doc.get("content_type"),
            "uploaded_at": doc.get("uploaded_at"),
            "uploaded_by": doc.get("uploaded_by"),
            "s3_path": doc["s3_path"],
            "request_id": pedido if _e_pedido(doc) else None,
        })
    return encontrados


async def ficheiros_internos(partner: dict, caso: Caso) -> list[dict]:
    """Os ficheiros visíveis, COM a chave S3 — só para uso interno (descarga)."""
    resultado: list[dict] = []
    for doc in await _documentos_do_caso(caso):
        resultado.extend(_ficheiros_de(doc, partner["id"]))
    return resultado


def _dto_do_ficheiro(f: dict, partner_id: str) -> dict:
    return {
        "id": f["id"],
        "filename": f.get("filename"),
        "file_size": f.get("file_size"),
        "content_type": f.get("content_type"),
        "uploaded_at": f.get("uploaded_at"),
        "by": quem_enviou(f.get("uploaded_by"), partner_id),
    }


def _dto_do_pedido(doc: dict, partner_id: str) -> dict:
    categoria = _categoria_em_texto(doc)
    info = DOCUMENT_CATEGORY_MAP.get(categoria, {"label": categoria, "icon": "📎"})
    pendente = doc.get("status") in ESTADOS_PENDENTES
    return {
        "id": doc.get("id"),
        "label": rotulo_do_pedido(doc, info if isinstance(info, dict) else {}),
        "category": categoria,
        "notes": nota_do_pedido(doc),
        "estado": "pendente" if pendente else "recebido",
        "expected_count": parse_expected_count(doc),
        "uploaded_count": len(doc.get("attached_files") or []) or doc.get("uploaded_count") or 0,
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "ficheiros": [_dto_do_ficheiro(f, partner_id) for f in _ficheiros_de(doc, partner_id)],
    }


# ════════════════════════════════════════════════════════════════════
#  DETALHE
# ════════════════════════════════════════════════════════════════════
async def run_get_case(partner: dict, case_id: str) -> dict:
    caso = await resolver_caso(partner, case_id)
    documentos = await _documentos_do_caso(caso)

    if caso.e_processo:
        etapa = etapa_de_um_estado(caso.process.get("status"), await carregar_fases())
        base = dto_do_processo(caso.process, etapa)
    else:
        base = dto_da_lead(caso.client)

    pedidos = [_dto_do_pedido(d, partner["id"]) for d in documentos if _e_pedido(d)]
    pedidos.sort(key=lambda p: str(p.get("created_at") or ""))
    soltos = [
        _dto_do_ficheiro(f, partner["id"])
        for d in documentos if not _e_pedido(d)
        for f in _ficheiros_de(d, partner["id"])
    ]
    soltos.sort(key=lambda f: str(f.get("uploaded_at") or ""), reverse=True)

    base["pedidos_pendentes"] = sum(1 for p in pedidos if p["estado"] == "pendente")
    return {**base, "pedidos": pedidos, "ficheiros": soltos}


__all__ = [
    "Caso",
    "ERRO_CASO_NAO_ENCONTRADO",
    "ficheiros_internos",
    "resolver_caso",
    "run_get_case",
    "run_get_dashboard",
    "run_list_cases",
]
