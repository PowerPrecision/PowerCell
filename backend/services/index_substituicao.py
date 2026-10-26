"""Os comprovativos do cliente substituídos pelos que o Index carregou (Out 2026).

O PEDIDO (dono do produto)
==========================
O Index descarrega os extratos, os recibos e a declaração da entidade patronal que o cliente enviou,
valida-os e volta a carregá-los. **O que conta para o processo são os documentos que o Index carregou**; os do
cliente desses tipos deixam de estar visíveis. O nome do ficheiro não interessa. O cliente pode ter mais de um
trabalho e o processo pode ter os documentos do 2.º titular. **Num processo sem Index nada disto acontece.**
Decisão: os do cliente deixam de contar LOGO que o Index carrega o primeiro documento desse tipo (não só no
fim), e o Index tem uma opção para os voltar a ver.

A REGRA (pura: `documentos_substituidos`)
=========================================
* só num processo COM Index (`skip_index` desligado: Via Verde e redes sem Index ficam como estavam);
* só os três tipos (`TIPOS_SUBSTITUIVEIS`); a identificação e o resto nunca se escondem;
* por **(tipo, titular)**: o recibo que o Index carregou para o 1.º titular não esconde os recibos do 2.º;
* o trabalho (entidade patronal) não entra na chave: o Index volta a carregar os comprovativos de TODOS os
  trabalhos, e os dele agrupam-se por NIF na análise como sempre;
* o tipo de um ficheiro: o que a análise do Index gravou (`index_facts.tipo`) e, antes dela, o que a
  categorização e o nome dizem (`tipo_de_analise`). Um upload do Index ainda por categorizar não esconde nada;
* nunca se apaga nem se move nada: o documento continua no armazenamento e volta a contar se o do Index sair.

DE QUEM É UM DOCUMENTO
======================
Só há titulares a distinguir com 2.º titular (sem ele, tudo é do 1.º). Um marcador explícito (`titular`, que
o Index escolhe ao carregar e o parceiro também grava) vence; sem ele, o envio feito pelo próprio 2.º cliente
(`client_id` do registo do Portal) é do 2.º; o resto é do 1.º.

ONDE SE APLICA
==============
A listagem do separador Documentos, a bancada, a análise do Index (ficheiros a ler, metadados profissionais,
declarações, pesquisa avançada) e o motor financeiro. O Portal do cliente não muda (o Index é invisível).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from database import db
from services.index_ai import TIPO_DECLARACAO, TIPO_EXTRATO, TIPO_RECIBO, tipo_de_analise
from services.partner_titulares import TITULAR_1, TITULAR_2, titular_marcado

logger = logging.getLogger(__name__)

TIPOS_SUBSTITUIVEIS = (TIPO_RECIBO, TIPO_EXTRATO, TIPO_DECLARACAO)

#: Quem pode pedir para VER os substituídos: os mesmos que vêem a pasta `Index`.
PAPEIS_QUE_VEEM_OS_SUBSTITUIDOS = ("master", "admin", "ceo", "diretor", "indexacao")

_PROJECCAO = {
    "_id": 0, "id": 1, "s3_path": 1, "filename": 1, "ai_category": 1, "ai_subcategory": 1,
    "index_facts.tipo": 1, "uploaded_by_index": 1, "is_clean_pdf": 1, "titular": 1, "client_id": 1,
}


def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def processo_tem_index(processo: Optional[dict]) -> bool:
    return bool(processo) and processo.get("skip_index") is not True


def tem_segundo_titular(processo: Optional[dict]) -> bool:
    processo = processo or {}
    dados = processo.get("titular2_data") if isinstance(processo.get("titular2_data"), dict) else {}
    return bool(
        _texto(processo.get("second_client_id")) or _texto(processo.get("second_client_name"))
        or _texto(dados.get("name")) or _texto(dados.get("nome"))
    )


def tipo_do_documento(doc: dict) -> Optional[str]:
    """O tipo de comprovativo, ou `None`. A análise do Index manda; antes dela, a categorização e o nome."""
    factos = doc.get("index_facts") if isinstance(doc.get("index_facts"), dict) else {}
    tipo = factos.get("tipo") or tipo_de_analise(doc.get("ai_category"), doc.get("ai_subcategory"), doc.get("filename"))
    return tipo if tipo in TIPOS_SUBSTITUIVEIS else None


def titular_do_documento(doc: dict, processo: Optional[dict], registo: Optional[dict] = None) -> str:
    """`titular1`/`titular2`. `registo` é o do envio (`documents`, Portal/Parceiro), se houver."""
    if not tem_segundo_titular(processo):
        return TITULAR_1
    registo = registo or {}
    marcado = titular_marcado(doc.get("titular")) or titular_marcado(registo.get("titular"))
    if marcado:
        return marcado
    segundo = _texto((processo or {}).get("second_client_id"))
    cliente = _texto(doc.get("client_id")) or _texto(registo.get("client_id"))
    if segundo and cliente == segundo:
        return TITULAR_2
    return TITULAR_1


def documentos_substituidos(
    docs: Iterable[dict], processo: Optional[dict], registos_por_caminho: Optional[dict[str, dict]] = None
) -> set[str]:
    """Os `id` dos documentos do cliente que já não contam. Pura."""
    if not processo_tem_index(processo):
        return set()
    registos_por_caminho = registos_por_caminho or {}
    do_index: set[tuple[str, str]] = set()
    do_cliente: list[tuple[str, tuple[str, str]]] = []
    for doc in docs:
        if not isinstance(doc, dict) or doc.get("is_clean_pdf") or not doc.get("id"):
            continue
        tipo = tipo_do_documento(doc)
        if not tipo:
            continue
        chave = (tipo, titular_do_documento(doc, processo, registos_por_caminho.get(doc.get("s3_path") or "")))
        if doc.get("uploaded_by_index"):
            do_index.add(chave)
        else:
            do_cliente.append((doc["id"], chave))
    return {doc_id for doc_id, chave in do_cliente if chave in do_index}


async def _registos_do_envio(process_id: str, caminhos: list[str]) -> dict[str, dict]:
    """`{s3_path: {titular, client_id}}` dos registos do Portal e do Parceiro (`documents`)."""
    if not caminhos:
        return {}
    saida: dict[str, dict] = {}
    cursor = db.documents.find(
        {"$or": [{"s3_path": {"$in": caminhos}}, {"files.s3_path": {"$in": caminhos}}]},
        {"_id": 0, "s3_path": 1, "titular": 1, "client_id": 1, "files.s3_path": 1, "files.titular": 1},
    )
    for reg in await cursor.to_list(1000):
        base = {"titular": reg.get("titular"), "client_id": reg.get("client_id")}
        if reg.get("s3_path"):
            saida[reg["s3_path"]] = base
        for ficheiro in reg.get("files") or []:
            if isinstance(ficheiro, dict) and ficheiro.get("s3_path"):
                saida[ficheiro["s3_path"]] = {**base, "titular": ficheiro.get("titular") or base["titular"]}
    return saida


_PROJECCAO_DO_PROCESSO = {
    "_id": 0, "id": 1, "skip_index": 1, "second_client_id": 1, "second_client_name": 1,
    "titular2_data.name": 1, "titular2_data.nome": 1,
}


async def titulares_e_substituidos(process_id: str, processo: Optional[dict] = None) -> tuple[dict[str, str], set[str]]:
    """`({id: titular}, {ids substituídos})` dos documentos do processo.

    `{id: titular}` só vem preenchido com 2.º titular (sem ele não há nada a distinguir). Nunca levanta: se não
    der para ler, nada se esconde (o pior é contar a mais, como antes) — e di-lo o log.
    """
    try:
        if processo is None:
            processo = await db.processes.find_one({"id": process_id}, _PROJECCAO_DO_PROCESSO)
        if not processo:
            return {}, set()
        dois = tem_segundo_titular(processo)
        com_index = processo_tem_index(processo)
        if not dois and not com_index:
            return {}, set()
        docs = await db.document_metadata.find({"process_id": process_id}, _PROJECCAO).to_list(2000)
        if not dois and not any(d.get("uploaded_by_index") for d in docs):
            return {}, set()
        registos = await _registos_do_envio(process_id, [d["s3_path"] for d in docs if d.get("s3_path")]) if dois else {}
        titulares = {
            d["id"]: titular_do_documento(d, processo, registos.get(d.get("s3_path") or ""))
            for d in docs if d.get("id")
        } if dois else {}
        return titulares, documentos_substituidos(docs, processo, registos)
    except Exception as exc:  # noqa: BLE001 — esconder é um reforço; falhar não pode derrubar a leitura
        logger.warning("[INDEX] Substituídos do processo %s não calculados: %s", process_id, type(exc).__name__)
        return {}, set()


async def ids_substituidos(process_id: str, processo: Optional[dict] = None) -> set[str]:
    """Os `id` (de `document_metadata`) dos documentos do cliente que já não contam neste processo."""
    return (await titulares_e_substituidos(process_id, processo))[1]


def pode_ver_os_substituidos(papel: Optional[str]) -> bool:
    return _texto(papel).lower() in PAPEIS_QUE_VEEM_OS_SUBSTITUIDOS


async def aplicar_a_listagem(listagem: Any, process_id: Optional[str], papel: Optional[str], incluir: bool) -> Any:
    """A listagem por pastas do separador Documentos sem os comprovativos substituídos.

    Quem vê a pasta `Index` recebe `superseded_count` (para o ecrã oferecer a opção) e, com `incluir`, os
    ficheiros na mesma, marcados `superseded`. Os outros nem sabem que existem (o Index é invisível).
    """
    if not process_id or not isinstance(listagem, dict) or not isinstance(listagem.get("files"), dict):
        return listagem
    substituidos = await ids_substituidos(process_id)
    pode_ver = pode_ver_os_substituidos(papel)
    if not substituidos:
        return {**listagem, "superseded_count": 0} if pode_ver else listagem
    mostrar = pode_ver and incluir
    por_categoria: dict[str, Any] = {}
    retirados = 0
    for categoria, ficheiros in listagem["files"].items():
        if not isinstance(ficheiros, list):
            por_categoria[categoria] = ficheiros
            continue
        ficam = []
        for f in ficheiros:
            if isinstance(f, dict) and f.get("doc_id") in substituidos:
                retirados += 1
                if mostrar:
                    ficam.append({**f, "superseded": True})
                continue
            ficam.append(f)
        por_categoria[categoria] = ficam
    resultado = {**listagem, "files": por_categoria}
    stats = listagem.get("stats")
    if isinstance(stats, dict) and retirados and not mostrar:
        todos = [f for lista in por_categoria.values() if isinstance(lista, list) for f in lista if isinstance(f, dict)]
        tamanho = sum(int(f.get("size") or 0) for f in todos)
        resultado["stats"] = {**stats, "total_files": len(todos), "total_size": tamanho}
        if "total_size_formatted" in stats:
            from services.document_intake import _formatar_tamanho

            resultado["stats"]["total_size_formatted"] = _formatar_tamanho(tamanho)
    if pode_ver:
        resultado["superseded_count"] = retirados
    return resultado


__all__ = [
    "TIPOS_SUBSTITUIVEIS", "PAPEIS_QUE_VEEM_OS_SUBSTITUIDOS", "processo_tem_index", "tem_segundo_titular",
    "tipo_do_documento", "titular_do_documento", "documentos_substituidos", "ids_substituidos",
    "titulares_e_substituidos", "aplicar_a_listagem",
    "pode_ver_os_substituidos",
]
