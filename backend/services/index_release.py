"""Libertar a pasta `Index` quando o processo passa a indexado (Bloco 2, Lote 12).

O PEDIDO: «qualquer upload vai inicialmente para a pasta `Index`; só após o
processo ser marcado como indexado é que o sistema/IA move os ficheiros para
as categorias finais».

AS REGRAS (cada uma tem teste)
==============================
1. **Sem IA aqui.** A categoria já foi decidida — pela categorização em
   background que correu quando o ficheiro entrou (`document_metadata.
   ai_category`) ou pelo indexador. Esta função só MOVE. Chamar o modelo de
   novo seria pagar duas vezes pelo mesmo ficheiro, que é precisamente o que
   o desvio inteligente existe para evitar.
2. **Sem categoria, fica.** Um ficheiro cuja IA falhou (ou ainda não correu)
   não tem para onde ir: continua na `Index` e vem no relatório
   (`sem_categoria`). Mandá-lo para «Outros» às cegas esconderia da fila de
   quem o devia tratar um documento que ninguém olhou.
3. **Só depois de indexado.** Lê o processo da base de dados (a fonte da
   verdade, não o dicionário que o chamador traz — esse é o de ANTES da
   escrita) e recusa se não passou a indexação.
4. **Nunca sobrescreve.** Conflito de nome no destino → sufixo `_2`, `_3`…
5. **O Portal acompanha.** O pedido do cliente guarda o `s3_path` (e
   `attached_files[].s3_path`): se o ficheiro muda e o registo não, o cliente
   passa a ver um documento que já não existe ao abrigo daquela chave.
6. **Um só registo no histórico**, com o actor — e `log_history` já é mudo
   para o perfil `indexacao` (é quase sempre ele a marcar como indexado).
7. **Nunca propaga.** A indexação já está gravada quando isto corre; um
   problema aqui (S3 em baixo) não pode desfazê-la nem devolver erro por uma
   operação que teve sucesso. Fica no relatório e no log.
8. **Corre ANTES do motor financeiro**: ele lê o `s3_path` dos metadados, e
   tem de o encontrar já actualizado.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from services.document_intake import (
    CATEGORIA_INDEX,
    chave_esta_na_index,
    processo_ja_passou_a_indexacao,
)
from services.history import log_history
from services.s3_document_root import pasta_gravada
from services.s3_storage import sanitize_folder_name, s3_service

logger = logging.getLogger(__name__)

#: Tecto por libertação: uma pasta com milhares de ficheiros não pode prender o
#: pedido de «marcar como indexado». O que sobra fica na `Index` e vem contado.
MAXIMO_POR_LIBERTACAO = 200
#: Tentativas de sufixo `_N` antes de desistir de um nome.
MAXIMO_DE_SUFIXOS = 50


def _relatorio_vazio() -> dict[str, Any]:
    return {
        "executado": False,
        "movidos": 0,
        "sem_categoria": 0,
        "falhados": 0,
        "adiados": 0,
        "detalhe": [],
    }


def _pasta_de_destino(categoria: Any) -> Optional[str]:
    """O nome da pasta final, ou `None` se a categoria não serve."""
    if not isinstance(categoria, str) or not categoria.strip():
        return None
    pasta = sanitize_folder_name(categoria)
    if not pasta or pasta.lower() in (CATEGORIA_INDEX.lower(), "cliente"):
        return None
    return pasta


def _com_sufixo(nome: str, n: int) -> str:
    base, ponto, extensao = nome.rpartition(".")
    if not ponto:
        return f"{nome}_{n}"
    return f"{base}_{n}.{extensao}"


def _destino_livre(base: str, pasta: str, nome: str) -> Optional[str]:
    """Primeiro caminho livre no destino (síncrono: corre numa thread)."""
    candidato = f"{base}/{pasta}/{nome}"
    if not s3_service.file_exists(candidato):
        return candidato
    for n in range(2, MAXIMO_DE_SUFIXOS + 2):
        candidato = f"{base}/{pasta}/{_com_sufixo(nome, n)}"
        if not s3_service.file_exists(candidato):
            return candidato
    return None


def _mover_sincrono(origem: str, base: str, pasta: str, nome: str) -> Optional[str]:
    destino = _destino_livre(base, pasta, nome)
    if not destino:
        return None
    return destino if s3_service.rename_file(origem, destino) else None


async def _repontar_pedidos_do_portal(origem: str, destino: str) -> None:
    """Leitura-modificação-escrita do `s3_path` nos pedidos que o apontam."""
    candidatos = await db.documents.find(
        {"$or": [{"s3_path": origem}, {"attached_files": {"$elemMatch": {"s3_path": origem}}}]},
        {"_id": 0},
    ).to_list(50)
    for doc in candidatos:
        alteracoes: dict[str, Any] = {}
        if doc.get("s3_path") == origem:
            alteracoes["s3_path"] = destino
        anexos = doc.get("attached_files")
        if isinstance(anexos, list) and any(
            isinstance(a, dict) and a.get("s3_path") == origem for a in anexos
        ):
            alteracoes["attached_files"] = [
                {**a, "s3_path": destino} if isinstance(a, dict) and a.get("s3_path") == origem else a
                for a in anexos
            ]
        if alteracoes and doc.get("id"):
            await db.documents.update_one({"id": doc["id"]}, {"$set": alteracoes})


async def libertar_ficheiros_do_index(
    process_id: str,
    *,
    user: Optional[dict] = None,
) -> dict[str, Any]:
    """Move os ficheiros da `Index` para as pastas finais. Nunca levanta."""
    relatorio = _relatorio_vazio()
    try:
        return await _libertar(process_id, user, relatorio)
    except Exception as exc:
        logger.warning(
            "[INDEX-RELEASE] Falha a libertar a pasta Index do processo %s "
            "(a indexação mantém-se): %s: %s", process_id, type(exc).__name__, exc,
        )
        relatorio["erro"] = type(exc).__name__
        return relatorio


async def _libertar(process_id: str, user: Optional[dict], relatorio: dict) -> dict:
    processo = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not processo or not processo_ja_passou_a_indexacao(processo):
        return relatorio
    if not s3_service.is_configured():
        return relatorio

    pasta = pasta_gravada(processo.get("s3_folder"), contexto=f"libertação da Index de {process_id}")
    if not pasta:
        return relatorio

    listagem = await asyncio.to_thread(
        s3_service.list_files,
        process_id,
        processo.get("client_name", ""),
        None,
        pasta,
    )
    ficheiros = (listagem or {}).get("files", {}).get(CATEGORIA_INDEX) or []
    relatorio["executado"] = True
    if not ficheiros:
        return relatorio

    agora = datetime.now(timezone.utc).isoformat()
    for i, ficheiro in enumerate(ficheiros):
        origem = ficheiro.get("path") if isinstance(ficheiro, dict) else None
        if not origem or not chave_esta_na_index(origem):
            continue
        if i >= MAXIMO_POR_LIBERTACAO:
            relatorio["adiados"] += 1
            continue

        meta = await db.document_metadata.find_one({"s3_path": origem}, {"_id": 0})
        destino_pasta = _pasta_de_destino((meta or {}).get("ai_category"))
        if not destino_pasta:
            relatorio["sem_categoria"] += 1
            relatorio["detalhe"].append({"ficheiro": ficheiro.get("name"), "resultado": "sem_categoria"})
            continue

        segmentos = [s for s in origem.split("/") if s]
        base = "/".join(segmentos[:-2])
        nome = segmentos[-1]
        destino = await asyncio.to_thread(_mover_sincrono, origem, base, destino_pasta, nome)
        if not destino:
            relatorio["falhados"] += 1
            relatorio["detalhe"].append({"ficheiro": nome, "resultado": "falhou"})
            continue

        novo_nome = os.path.basename(destino)
        if meta:
            await db.document_metadata.update_one(
                {"s3_path": origem},
                {"$set": {
                    "s3_path": destino,
                    "filename": novo_nome,
                    "in_index_queue": False,
                    "released_from_index_at": agora,
                    "updated_at": agora,
                }},
            )
        await _repontar_pedidos_do_portal(origem, destino)
        relatorio["movidos"] += 1
        relatorio["detalhe"].append({"ficheiro": nome, "resultado": "movido", "para": destino_pasta})

    if relatorio["movidos"]:
        try:
            await log_history(
                process_id=process_id,
                user=user or {},
                action="Ficheiros da pasta Index organizados",
                field="documento",
                new_value=(
                    f"{relatorio['movidos']} movido(s) para as pastas finais"
                    + (f"; {relatorio['sem_categoria']} por categorizar" if relatorio["sem_categoria"] else "")
                ),
            )
        except Exception as exc:
            logger.warning("[INDEX-RELEASE] Histórico não registado: %s", exc)

    logger.info(
        "[INDEX-RELEASE] %s: movidos=%s sem_categoria=%s falhados=%s adiados=%s",
        process_id, relatorio["movidos"], relatorio["sem_categoria"],
        relatorio["falhados"], relatorio["adiados"],
    )
    return relatorio
