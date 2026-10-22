#!/usr/bin/env python3
"""Constrói a pesquisa por DOCUMENTO do Index para o que JÁ foi analisado (Out 2026).

    # ler e contar (omissão — NÃO escreve)
    python -m scripts.backfill_index_documentos

    # gravar
    python -m scripts.backfill_index_documentos --aplicar

O QUE FAZ
=========
A pesquisa avançada por documento (`GET /index/advanced-search?document_type=…`) lê a colecção
`process_index_documents`, que a análise passou a manter. Os processos analisados ANTES não a têm até
alguém voltar a analisar o processo. Este script reconstrói-a a partir do que a análise já guardou em
`document_metadata.index_facts` — **sem chamar a IA e sem ler um único ficheiro do S3**. É a única forma de
esta funcionalidade valer para o histórico sem uma reanálise retroactiva (decisão da direcção: não há).

O QUE NÃO FAZ
=============
Não preenche o que as análises antigas nunca guardaram: os extratos analisados antes desta entrega não têm
banco e os recibos antigos não têm localidade — ficam `null` até serem extraídos outra vez (e só então).
O relatório di-lo, para um «0 extratos com banco» não se ler como um defeito.

Idempotente (a 2.ª passagem escreve as mesmas linhas, e não duplica) e tolerante a corridas. CORRE CONTRA
PRODUÇÃO DE PROPÓSITO: a omissão é ler e contar; só `--aplicar` escreve.

CÓDIGOS DE SAÍDA:  0 ok · 2 a leitura não aconteceu (sem base de dados)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import index_store as store  # noqa: E402


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aplicar", action="store_true", help="grava (omissão: só lê)")
    return p.parse_args()


def resumir(docs: list[dict]) -> dict:
    """Contagens do que a reconstrução produziria. Pura: usa a MESMA projecção que a escrita."""
    por_tipo: Counter = Counter()
    extratos_com_banco = recibos_com_localidade = 0
    for doc in docs:
        linha = store.projectar_documento(doc, process_id=str(doc.get("process_id")), network_id=None)
        if linha is None:
            continue
        por_tipo[linha["doc_type"]] += 1
        extratos_com_banco += int(linha["doc_type"] == store.DOC_TYPE_EXTRATO and bool(linha["bank_key"]))
        recibos_com_localidade += int(linha["doc_type"] == store.DOC_TYPE_RECIBO and bool(linha["employer_location"]))
    return {
        "linhas": sum(por_tipo.values()), "por_tipo": dict(por_tipo),
        "extratos_com_banco": extratos_com_banco, "recibos_com_localidade": recibos_com_localidade,
    }


async def principal() -> int:
    args = _argumentos()
    try:
        from database import db

        docs = await db.document_metadata.find(
            {"is_clean_pdf": {"$ne": True}, "index_facts": {"$exists": True, "$ne": None}},
            {"_id": 0, "id": 1, "process_id": 1, "index_facts": 1, "index_job": 1},
        ).to_list(None)
        processos = sorted({d["process_id"] for d in docs if d.get("process_id")})
        redes = {
            p["id"]: p.get("network_id")
            for p in await db.processes.find({"id": {"$in": processos}}, {"_id": 0, "id": 1, "network_id": 1}).to_list(None)
        }
    except Exception as exc:  # noqa: BLE001
        print(f"LEITURA NÃO REALIZADA: {exc}\n"
              "Sem leitura não há contagem — um 0 aqui leria-se como «já está tudo feito».")
        return 2

    r = resumir(docs)
    print(f"Ficheiros analisados: {len(docs)} em {len(processos)} processos · linhas a escrever: {r['linhas']}")
    for tipo, n in sorted(r["por_tipo"].items()):
        print(f"  → {tipo}: {n}")
    print(f"Extratos com banco: {r['extratos_com_banco']} · recibos com localidade: {r['recibos_com_localidade']} "
          "(as análises antigas não os guardaram: ficam por preencher até serem extraídas outra vez)")

    if not args.aplicar:
        if r["linhas"]:
            print("→ Nada foi gravado. Correr outra vez com --aplicar.")
        return 0

    escritas = 0
    for process_id in processos:
        escritas += await store.reconstruir_documentos_do_index(process_id, redes.get(process_id))
    print(f"Gravadas: {escritas}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
