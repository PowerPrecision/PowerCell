#!/usr/bin/env python3
"""Dá `expire_at` aos registos antigos de `portal_verify_attempts` (D-31, remate).

    # ler e contar (omissão — NÃO escreve)
    python scripts/backfill_portal_verify_ttl.py

    # gravar `expire_at` nos que ainda não o têm
    python scripts/backfill_portal_verify_ttl.py --aplicar

POR QUE EXISTE
==============
O índice TTL `ttl_portal_verify_attempts` actua sobre `expire_at`, que só os
registos criados DEPOIS do deploy levam. Os que já existiam — um por cada
`client_id` inventado ou falhado até hoje — ficavam para sempre. A data vem de
`portal_verify_ttl.expire_at_do_registo` (a partir da última tentativa; nunca
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

from services.portal_verify_ttl import expire_at_do_registo  # noqa: E402


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aplicar", action="store_true", help="grava (omissão: só lê)")
    return p.parse_args()


async def principal() -> int:
    args = _argumentos()
    try:
        from database import db
        registos = await db.portal_verify_attempts.find(
            {"expire_at": {"$exists": False}}, {"_id": 1, "last_attempt_at": 1, "locked_until": 1},
        ).to_list(1_000_000)
    except Exception as exc:  # noqa: BLE001
        print(f"LEITURA NÃO REALIZADA: {exc}\n"
              "Sem leitura não há contagem — um 0 aqui leria-se como «já está tudo feito».")
        return 2

    agora = datetime.now(timezone.utc)
    ja_expirados = sum(1 for r in registos if expire_at_do_registo(r, agora=agora) <= agora)
    print(f"Registos sem `expire_at`: {len(registos)} "
          f"({ja_expirados} já passaram o prazo e o TTL apaga-os na 1.ª passagem)")

    if not args.aplicar:
        if registos:
            print("→ Nada foi gravado. Correr outra vez com --aplicar.")
        return 0

    gravados = 0
    for registo in registos:
        resultado = await db.portal_verify_attempts.update_one(
            {"_id": registo["_id"], "expire_at": {"$exists": False}},
            {"$set": {"expire_at": expire_at_do_registo(registo, agora=agora)}},
        )
        gravados += int(bool(resultado.modified_count))
    print(f"Gravados: {gravados}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
