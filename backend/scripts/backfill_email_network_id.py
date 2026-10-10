"""
====================================================================
MIGRAÇÃO: carimbar `network_id` nos emails (D-8)
====================================================================
Os emails NOVOS já nascem carimbados (`services/email_tenant_stamp.inserir_email`).
Este script carimba os que já lá estavam, com a MESMA função de produção
(`resolver_rede_do_email`) — duas implementações da mesma dedução divergem
na primeira mudança, e o backfill é precisamente o sítio onde isso passaria
despercebido.

REGRA  (a do `rede_consensual`)
  Uma candidata é uma resposta (a rede do processo do email, a rede da
  empresa do email). Duas candidatas diferentes NÃO se resolvem por maioria
  nem por prioridade: o email fica por carimbar e é contado à parte. Um
  carimbo errado é permanente.

  Sem processo e sem empresa (caixas partilhadas por cargo ainda não
  associadas) também fica por carimbar — e continua a ser lido pela
  dedução que `email_access` já faz.

SEGURANÇA
  * Corre contra PRODUÇÃO de propósito (não chama `require_non_production_db`):
    é para isso que existe. Em troca, a omissão é LER e CONTAR; só
    `--aplicar` escreve.
  * O `$set` é ESTRITO (`network_id`) e só acontece onde o campo ainda
    falta (`network_id` ausente/vazio no filtro da escrita): nunca
    sobrepõe um carimbo e é idempotente — a segunda passagem escreve 0.
  * Passagem por cursor: não carrega a colecção na memória.

EXECUÇÃO
  cd backend && python -m scripts.backfill_email_network_id            # só mostra
  cd backend && python -m scripts.backfill_email_network_id --aplicar
  Flags:  --limite N   --verbose
====================================================================
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("backfill_email_network_id")

SEM_REDE = {"$in": [None, ""]}


async def carimbar_emails(db_handle, *, aplicar: bool, limite: Optional[int] = None, verbose: bool = False) -> dict:
    """Percorre os emails por carimbar. Devolve as contagens."""
    from services.email_tenant_stamp import resolver_rede_do_email

    contagens = {"vistos": 0, "carimbados": 0, "por_resolver": 0, "ja_carimbados_entretanto": 0}
    memo: dict = {}
    cursor = db_handle.emails.find(
        {"network_id": SEM_REDE},
        {"_id": 0, "id": 1, "process_id": 1, "company_id": 1},
    )

    async for email in cursor:
        if limite is not None and contagens["vistos"] >= limite:
            break
        contagens["vistos"] += 1
        rede = await resolver_rede_do_email(db_handle, email, memo=memo)
        if not rede:
            contagens["por_resolver"] += 1
            if verbose:
                logger.info("    ? %s sem rede dedutível (fica por carimbar)", email.get("id"))
            continue
        if verbose:
            logger.info("    → %s = %s", email.get("id"), rede)
        if not aplicar:
            contagens["carimbados"] += 1
            continue
        resultado = await db_handle.emails.update_one(
            {"id": email.get("id"), "network_id": SEM_REDE},
            {"$set": {"network_id": rede}},
        )
        if getattr(resultado, "modified_count", 1):
            contagens["carimbados"] += 1
        else:
            contagens["ja_carimbados_entretanto"] += 1
    return contagens


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="Escreve. Sem isto só mostra.")
    parser.add_argument("--limite", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from database import db

    prefixo = "" if args.aplicar else "[SÓ LEITURA] "
    contagens = await carimbar_emails(db, aplicar=args.aplicar, limite=args.limite, verbose=args.verbose)
    logger.info(
        "%sEmails por carimbar vistos: %d → %d carimbados, %d por resolver%s",
        prefixo, contagens["vistos"], contagens["carimbados"], contagens["por_resolver"],
        f", {contagens['ja_carimbados_entretanto']} já carimbados entretanto" if contagens["ja_carimbados_entretanto"] else "",
    )
    if not args.aplicar:
        logger.info("Nada foi escrito. Repita com --aplicar para carimbar.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
