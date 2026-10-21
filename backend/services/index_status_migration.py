"""Migração do `index_status` (Lote 12): o que há a escrever, e a escrita.

Lógica à parte do script (`scripts/migrar_index_status.py`) para se testar sem
base de dados real. A regra de derivação NÃO é repetida aqui: vem de
`index_status.derivar_estado` — uma segunda cópia divergiria na primeira
mudança (a forma do `assignment_drift`).

Idempotente: um processo cujo `index_status`/`index_skipped` já são os que o
documento diz não entra no plano; a segunda passagem escreve 0.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from services.index_status import derivar_estado

#: Só o que a derivação lê (e o que se compara) — nunca o documento inteiro.
PROJECCAO = {
    "_id": 0, "id": 1, "is_indexed": 1, "skip_index": 1, "index_status": 1,
    "index_skipped": 1, "assigned_indexacao_id": 1, "is_deleted": 1,
}


def plano_do_processo(doc: dict) -> dict[str, Any] | None:
    """`$set` necessário para este processo, ou `None` se já está certo."""
    alvo = derivar_estado(doc)
    if (
        doc.get("index_status") == alvo["index_status"]
        and doc.get("index_skipped") is alvo["index_skipped"]
    ):
        return None
    return alvo


def resumo(docs: list[dict]) -> dict[str, Any]:
    """Contagem do plano por estado-alvo (para o relatório do script)."""
    contagem: Counter = Counter()
    a_escrever = 0
    for doc in docs:
        plano = plano_do_processo(doc)
        if plano is None:
            continue
        a_escrever += 1
        contagem[plano["index_status"] + ("+dispensado" if plano["index_skipped"] else "")] += 1
    return {"total": len(docs), "a_escrever": a_escrever, "por_estado": dict(contagem)}


async def ler_processos(db) -> list[dict]:
    """Todos os processos não eliminados, só com os campos da derivação."""
    return await db.processes.find({"is_deleted": {"$ne": True}}, PROJECCAO).to_list(1_000_000)


async def aplicar(db, docs: list[dict]) -> int:
    """Escreve o plano. O filtro repete o estado lido: se outro escritor mexeu entretanto, não se pisa."""
    gravados = 0
    for doc in docs:
        plano = plano_do_processo(doc)
        if plano is None:
            continue
        filtro: dict[str, Any] = {"id": doc["id"]}
        # Concorrência optimista: só escreve se o estado ainda é o que lemos.
        for campo in ("index_status", "is_indexed", "skip_index"):
            if campo in doc:
                filtro[campo] = doc[campo]
            else:
                filtro[campo] = {"$exists": False}
        resultado = await db.processes.update_one(filtro, {"$set": plano})
        gravados += int(bool(resultado.modified_count))
    return gravados
