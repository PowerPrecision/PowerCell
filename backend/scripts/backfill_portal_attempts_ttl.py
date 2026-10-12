#!/usr/bin/env python3
"""Dá `expire_at` aos registos antigos das tentativas do Portal (D-31, remate).

    # ler e contar (omissão — NÃO escreve)
    python scripts/backfill_portal_attempts_ttl.py

    # gravar `expire_at` nos que ainda não o têm
    python scripts/backfill_portal_attempts_ttl.py --aplicar

POR QUE EXISTE
==============
Os índices TTL `ttl_portal_verify_attempts` (login por NIF) e
`ttl_portal_login_attempts` (login por email) actuam sobre `expire_at`, que só
os registos criados DEPOIS do deploy levam. Os que já existiam — um por cada
`client_id` ou email inventado ou falhado até hoje — ficavam para sempre. O
script percorre as DUAS colecções (`COLECCOES_DE_TENTATIVAS`). A data vem de
`portal_attempts_ttl.expire_at_do_registo` (a partir da última tentativa; nunca
antes do fim de um bloqueio em curso).

CORRE CONTRA PRODUÇÃO DE PROPÓSITO (como `fix_s3_folder_anomalies`): a omissão é
LER e contar; só `--aplicar` escreve, e cada escrita é um `$set` estrito de
`expire_at`, condicionado a ele ainda não existir (idempotente, e seguro se a
aplicação gravar o seu entretanto).

CÓDIGOS DE SAÍDA:  0 ok · 2 a leitura não aconteceu (sem base de dados)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.portal_attempts_ttl import (  # noqa: E402
    COLECCOES_DE_TENTATIVAS,
    expire_at_do_registo,
)


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aplicar", action="store_true", help="grava (omissão: só lê)")
    return p.parse_args()


async def principal() -> int:
    args = _argumentos()
    agora = datetime.now(timezone.utc)
    por_colecao: dict[str, list[dict]] = {}
    try:
        from database import db
        for nome in COLECCOES_DE_TENTATIVAS:
            por_colecao[nome] = await getattr(db, nome).find(
                {"expire_at": {"$exists": False}},
                {"_id": 1, "last_attempt_at": 1, "locked_until": 1},
            ).to_list(1_000_000)
    except Exception as exc:  # noqa: BLE001
        print(f"LEITURA NÃO REALIZADA: {exc}\n"
              "Sem leitura não há contagem — um 0 aqui leria-se como «já está tudo feito».")
        return 2

    for nome, registos in por_colecao.items():
        ja_expirados = sum(1 for r in registos if expire_at_do_registo(r, agora=agora) <= agora)
        print(f"{nome}: {len(registos)} sem `expire_at` "
              f"({ja_expirados} já passaram o prazo e o TTL apaga-os na 1.ª passagem)")

    if not args.aplicar:
        if any(por_colecao.values()):
            print("→ Nada foi gravado. Correr outra vez com --aplicar.")
        return 0

    for nome, registos in por_colecao.items():
        gravados = 0
        for registo in registos:
            resultado = await getattr(db, nome).update_one(
                {"_id": registo["_id"], "expire_at": {"$exists": False}},
                {"$set": {"expire_at": expire_at_do_registo(registo, agora=agora)}},
            )
            gravados += int(bool(resultado.modified_count))
        print(f"{nome}: gravados {gravados}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
