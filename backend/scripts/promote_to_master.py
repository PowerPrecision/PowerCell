"""Promove contas existentes ao perfil MASTER (o único perfil global).

Corre contra a base de dados configurada em `MONGO_URL`/`DB_NAME` — PRODUÇÃO
incluída, de propósito: é o passo operacional do deploy da adenda de RBAC
(sem ele ninguém tem acesso global). Por isso NÃO chama
`require_non_production_db`, e em troca é cauteloso:

  * a omissão é MOSTRAR o plano; só `--aplicar` escreve;
  * os emails são explícitos (`--emails a@x.pt,b@y.pt`) — nunca «todos os admins»;
  * um plano com qualquer recusa não escreve NADA.

Exemplos:
    python scripts/promote_to_master.py --emails dono@empresa.pt
    python scripts/promote_to_master.py --emails dono@empresa.pt --aplicar
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402
from services import master_promotion as mp  # noqa: E402


async def principal(args: argparse.Namespace) -> int:
    emails = mp.normalizar_emails(args.emails.split(','))
    if not emails:
        print("Indique pelo menos um email em --emails.")
        return 2

    plano = mp.planear(
        emails,
        await mp.carregar_utilizadores(db, emails),
        qualquer_papel=args.qualquer_papel,
    )

    print(f"A promover ({len(plano.promover)}):")
    for u in plano.promover:
        print(f"  + {u['email']}  ({u.get('role')} → master)")
    print(f"Já são Master ({len(plano.ja_master)}):")
    for u in plano.ja_master:
        print(f"  = {u['email']}")
    print(f"Recusados ({len(plano.recusados)}):")
    for email, motivo in plano.recusados:
        print(f"  ! {email}: {motivo}")

    if plano.recusados:
        print("\nHá recusas: nada foi escrito.")
        return 1
    if not plano.promover:
        print("\nNada a fazer.")
        return 0
    if not args.aplicar:
        print("\nSimulação. Repita com --aplicar para escrever.")
        return 0

    n = await mp.aplicar(plano, db, executado_por="scripts/promote_to_master.py")
    print(f"\n{n} conta(s) promovida(s) a Master.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--emails", required=True, help="Emails separados por vírgula.")
    parser.add_argument("--aplicar", action="store_true", help="Escreve (omissão: só mostra).")
    parser.add_argument("--qualquer-papel", action="store_true", help="Permite promover quem não é admin/ceo.")
    sys.exit(asyncio.run(principal(parser.parse_args())))
