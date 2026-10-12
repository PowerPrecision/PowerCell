"""
====================================================================
MIGRAÇÃO: carimbar `network_id` nas caixas partilhadas por cargo (D-8)
====================================================================
Duas colecções, uma regra.

  * `shared_role_email_configs` — a configuração (IMAP/SMTP, refresh token do
    Google) de cada caixa. Até aqui havia UMA por cargo para o sistema
    inteiro; desde o D-8 a identidade é (cargo, rede).
  * `emails` com `shared_role` — o que essas caixas já sincronizaram.

A REDE
  Antes do D-8 só existia uma caixa por cargo e era do grupo que sempre a
  usou: a **rede de omissão** (`TENANT_DEFAULT_NETWORK_ID`). É essa a rede
  que se carimba — a mesma convenção de todas as outras colecções («sem
  `network_id` = a pilha antiga, que pertence à rede de omissão»).

  Sem `TENANT_DEFAULT_NETWORK_ID` e sem `--rede` o script RECUSA-SE (código
  2): carimbar a rede errada é permanente, e adivinhá-la é precisamente o que
  este trabalho existe para impedir.

SEGURANÇA
  * Corre contra PRODUÇÃO de propósito (não chama `require_non_production_db`).
    Em troca, a omissão é LER e CONTAR; só `--aplicar` escreve.
  * O `$set` é ESTRITO (`network_id`) e só onde o campo ainda falta: nunca
    sobrepõe um carimbo, e é idempotente — a segunda passagem escreve 0.
  * Os emails sem `shared_role` (pessoais, de processo) NÃO se tocam: esses
    são carimbados pelo `backfill_email_network_id`.

ORDEM NO DEPLOY
  Código primeiro, base de dados depois. Entre os dois, nada parte: as
  configurações e os emails sem carimbo continuam a ser da rede de omissão
  (é a regra de leitura), por isso este script só TORNA EXPLÍCITO o que já
  estava implícito — e é o que permite a uma segunda rede ter a sua caixa.

EXECUÇÃO
  cd backend && python -m scripts.backfill_shared_mailbox_network_id            # só mostra
  cd backend && python -m scripts.backfill_shared_mailbox_network_id --aplicar
  Flags:  --rede <network_id>   (por omissão TENANT_DEFAULT_NETWORK_ID)
====================================================================
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("backfill_shared_mailbox_network_id")

SEM_REDE = {"$in": [None, ""]}
COM_CARGO = {"$nin": [None, ""]}


class RedeIndeterminada(Exception):
    """Sem rede explícita nem de omissão: o script não adivinha."""


def rede_a_carimbar(rede_pedida: Optional[str] = None) -> str:
    from services.tenant_network import rede_de_omissao

    rede = (rede_pedida or "").strip() or (rede_de_omissao() or "")
    if not rede:
        raise RedeIndeterminada(
            "Sem rede para carimbar: defina TENANT_DEFAULT_NETWORK_ID ou passe --rede. "
            "Um carimbo errado é permanente — o script não adivinha."
        )
    return rede


async def planear(db_handle, rede: str) -> dict:
    """Quanto há por carimbar (só lê)."""
    return {
        "rede": rede,
        "configs_por_carimbar": await db_handle.shared_role_email_configs.count_documents(
            {"network_id": SEM_REDE}
        ),
        "emails_por_carimbar": await db_handle.emails.count_documents(
            {"shared_role": COM_CARGO, "network_id": SEM_REDE}
        ),
    }


async def aplicar(db_handle, rede: str) -> dict:
    """Carimba o que falta. Idempotente; nunca sobrepõe um carimbo."""
    configs = await db_handle.shared_role_email_configs.update_many(
        {"network_id": SEM_REDE}, {"$set": {"network_id": rede}},
    )
    emails = await db_handle.emails.update_many(
        {"shared_role": COM_CARGO, "network_id": SEM_REDE}, {"$set": {"network_id": rede}},
    )
    return {
        "rede": rede,
        "configs_carimbadas": getattr(configs, "modified_count", 0),
        "emails_carimbados": getattr(emails, "modified_count", 0),
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="Escreve. Sem isto só mostra.")
    parser.add_argument("--rede", default=None, help="Rede a carimbar (por omissão TENANT_DEFAULT_NETWORK_ID).")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        rede = rede_a_carimbar(args.rede)
    except RedeIndeterminada as exc:
        logger.error("%s", exc)
        return 2

    from database import db

    plano = await planear(db, rede)
    logger.info(
        "%sRede %s: %d configuração(ões) e %d email(s) de caixa partilhada por carimbar.",
        "" if args.aplicar else "[SÓ LEITURA] ", rede,
        plano["configs_por_carimbar"], plano["emails_por_carimbar"],
    )
    if not args.aplicar:
        logger.info("Nada foi escrito. Repita com --aplicar para carimbar.")
        return 0
    escrito = await aplicar(db, rede)
    logger.info(
        "Carimbadas: %d configuração(ões), %d email(s).",
        escrito["configs_carimbadas"], escrito["emails_carimbados"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
