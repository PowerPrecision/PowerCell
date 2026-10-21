#!/usr/bin/env python3
"""Grava `index_status` / `index_skipped` nos processos existentes (Lote 12, Fase 1).

    # ler e contar (omissão — NÃO escreve)
    python -m scripts.migrar_index_status

    # gravar o plano
    python -m scripts.migrar_index_status --aplicar

O QUE FAZ
=========
`is_indexed: true` → `indexed`; `skip_index` (Via Verde / rede sem Index) →
`indexed` + `index_skipped`; indexador atribuído → `in_review`; o resto →
`pending`. A regra é `services.index_status.derivar_estado` (a mesma dos
escritores). NÃO mexe em `is_indexed`, `skip_index`, nem em mais nenhum campo.

É conveniência, não pré-requisito do deploy: `condicao_da_fila` tolera
processos sem `index_status`. Idempotente (a 2.ª passagem escreve 0) e com
concorrência optimista (não pisa um processo que mudou entretanto).

CORRE CONTRA PRODUÇÃO DE PROPÓSITO (como `backfill_portal_attempts_ttl`): a
omissão é ler e contar; só `--aplicar` escreve.

CÓDIGOS DE SAÍDA:  0 ok · 2 a leitura não aconteceu (sem base de dados)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.index_status_migration import aplicar, ler_processos, resumo  # noqa: E402


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aplicar", action="store_true", help="grava (omissão: só lê)")
    return p.parse_args()


async def principal() -> int:
    args = _argumentos()
    try:
        from database import db

        docs = await ler_processos(db)
    except Exception as exc:  # noqa: BLE001
        print(f"LEITURA NÃO REALIZADA: {exc}\n"
              "Sem leitura não há contagem — um 0 aqui leria-se como «já está tudo feito».")
        return 2

    r = resumo(docs)
    print(f"Processos lidos: {r['total']} · a escrever: {r['a_escrever']}")
    for estado, n in sorted(r["por_estado"].items()):
        print(f"  → {estado}: {n}")

    if not args.aplicar:
        if r["a_escrever"]:
            print("→ Nada foi gravado. Correr outra vez com --aplicar.")
        return 0

    print(f"Gravados: {await aplicar(db, docs)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
