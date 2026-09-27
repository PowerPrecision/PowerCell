"""
====================================================================
MIGRAÇÃO: carimbar `company_id` nos emails (Webmail por empresa)
====================================================================
Ponto 8, Fase 1 — ver `services/webmail_scope.py`.

O PROBLEMA QUE ISTO RESOLVE
  O `email_service` grava a empresa CONDICIONALMENTE
  (`if company_id: email_doc["company_id"] = company_id`), pelo que há
  emails antigos sem carimbo nenhum. O âmbito do separador resgata-os
  pelo endereço da conta que os sincronizou (`account`), mas isso é uma
  dedução em tempo de leitura: enquanto durar, a pertença daqueles
  emails depende de a configuração de email não mudar. Este script
  torna-a explícita.

COMO DEDUZ O DONO DE UM EMAIL
  1. `account` — o endereço da caixa que o sincronizou. É a prova mais
     forte que existe: aquele email entrou por aquela caixa.
  2. `synced_for_user` / `created_by` — a empresa do utilizador, SÓ se
     ele tiver UMA empresa. Com várias, não se adivinha.
  3. nada: fica por carimbar, e continua a ser resgatado em leitura pelo
     ramo do `account`.

  Nunca escreve uma empresa "provável". Um carimbo errado aqui é pior do
  que nenhum: passa a MANDAR sobre a dedução pelo endereço (é essa a
  regra em `build_company_mailbox_condition`), e o email fica preso à
  empresa errada para sempre.

  Um endereço configurado em DUAS empresas não é dedutível: o script
  conta-o como por resolver em vez de escolher uma.

EXECUÇÃO
  cd backend && python -m scripts.backfill_email_company_id --dry-run
  cd backend && python -m scripts.backfill_email_company_id

  Flags:
    --dry-run    Mostra o que faria, sem escrever nada
    --limite N   Processa no máximo N emails (por omissão: todos)
    --verbose    Detalhe por email
====================================================================
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_email_company_id")

LOTE = 500


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def _endereco(valor: Any) -> str:
    return _texto(valor).lower()


def empresa_consensual(candidatas: list[Optional[str]]) -> Optional[str]:
    """Uma empresa só quando TODAS as pistas concordam.

    Com mais do que uma candidata devolve `None`: um endereço partilhado
    por duas empresas não se resolve por maioria.
    """
    distintas = {c for c in (_texto(c) for c in candidatas) if c}
    if len(distintas) == 1:
        return distintas.pop()
    return None


async def mapa_endereco_para_empresa(db) -> dict[str, Optional[str]]:
    """endereço → company_id, com `None` para os endereços ambíguos."""
    por_endereco: dict[str, set] = {}

    async def juntar(coleccao, campo_email, campo_empresa):
        try:
            docs = await coleccao.find(
                {}, {"_id": 0, campo_email: 1, campo_empresa: 1},
            ).to_list(5000)
        except Exception as exc:
            logger.warning("  ! Falha a ler %s: %s", campo_email, exc)
            return
        for doc in docs:
            endereco = _endereco(doc.get(campo_email))
            empresa = _texto(doc.get(campo_empresa))
            if endereco and empresa:
                por_endereco.setdefault(endereco, set()).add(empresa)

    await juntar(db.user_email_configs, "email_address", "company_id")
    await juntar(db.company_email_configs, "email_address", "company_id")

    return {
        endereco: (empresas.pop() if len(empresas) == 1 else None)
        for endereco, empresas in (
            (e, set(v)) for e, v in por_endereco.items()
        )
    }


async def empresa_unica_do_utilizador(db, user_id: str) -> Optional[str]:
    """A empresa de um utilizador — só quando ele tem exactamente uma."""
    if not user_id:
        return None
    try:
        ucrs = await db.user_company_roles.find(
            {"user_id": user_id, "is_deleted": {"$ne": True},
             "is_active": {"$ne": False}},
            {"_id": 0, "company_id": 1},
        ).to_list(20)
    except Exception:
        return None
    return empresa_consensual([u.get("company_id") for u in ucrs])


async def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Carimba `company_id` nos emails por carimbar.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limite", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    from database import db

    prefixo = "[SIMULAÇÃO] " if args.dry_run else ""
    agora = datetime.now(timezone.utc).isoformat()

    enderecos = await mapa_endereco_para_empresa(db)
    ambiguos = sum(1 for v in enderecos.values() if v is None)
    logger.info(
        "%s%d endereços mapeados (%d ambíguos, configurados em mais de uma empresa).",
        prefixo, len(enderecos), ambiguos,
    )

    query = {"company_id": {"$in": [None, ""]}}
    por_carimbar = await db.emails.find(
        query,
        {"_id": 0, "id": 1, "account": 1, "synced_for_user": 1, "created_by": 1},
    ).to_list(args.limite or 100000)

    logger.info("%s%d emails por carimbar.", prefixo, len(por_carimbar))

    carimbados = 0
    por_resolver = 0
    cache_utilizadores: dict[str, Optional[str]] = {}

    for email in por_carimbar:
        alvo = enderecos.get(_endereco(email.get("account")))

        if not alvo:
            for campo in ("synced_for_user", "created_by"):
                uid = _texto(email.get(campo))
                if not uid:
                    continue
                if uid not in cache_utilizadores:
                    cache_utilizadores[uid] = await empresa_unica_do_utilizador(db, uid)
                alvo = cache_utilizadores[uid]
                if alvo:
                    break

        if not alvo:
            por_resolver += 1
            if args.verbose:
                logger.info(
                    "    ? %s sem dono dedutível (continua resgatado pelo endereço)",
                    email.get("id"),
                )
            continue

        carimbados += 1
        if args.verbose:
            logger.info("    → %s = %s", email.get("id"), alvo)
        if not args.dry_run:
            await db.emails.update_one(
                {"id": email.get("id")},
                {"$set": {"company_id": alvo, "updated_at": agora}},
            )

    logger.info(
        "%sTotal: %d carimbados, %d por resolver.",
        prefixo, carimbados, por_resolver,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
