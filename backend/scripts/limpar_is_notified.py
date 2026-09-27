"""
====================================================================
LIMPEZA: o campo morto `notifications.is_notified`
====================================================================
Limpeza Estrutural, Ponto 3.

O QUE ERA
  `realtime_notifications` escrevia `is_notified: False` em cada
  notificação e, quando o utilizador estava ligado, fazia um `update_one`
  para o pôr a `True`. O campo NUNCA era lido — nem no backend, nem no
  frontend. Não prevenia re-emissão nenhuma, ao contrário do que o
  comentário original afirmava.

  A escrita já saiu do código. Este script tira o campo dos documentos
  antigos, para o Mongo deixar de o carregar em cada leitura da colecção.

POR OMISSÃO NÃO ESCREVE
  Sem `--aplicar` só CONTA. O `--aplicar` faz um `$unset` — que remove o
  campo e não o documento.

  É seguro por construção: o campo não é lido por ninguém, portanto não
  há nada que possa deixar de funcionar. Mesmo assim conta primeiro e
  aplica depois, porque uma escrita em massa numa colecção de produção
  merece um número antes de um comando.

EXECUÇÃO
  cd backend && python -m scripts.limpar_is_notified
  cd backend && python -m scripts.limpar_is_notified --aplicar

  Flags:
    --aplicar   Executa o `$unset`
    --lote N    Documentos por lote (omissão 5000)
====================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402

CAMPO = "is_notified"


async def contar() -> tuple[int, int]:
    """(com o campo, total). Nunca escreve."""
    com_campo = await db.notifications.count_documents({CAMPO: {"$exists": True}})
    total = await db.notifications.count_documents({})
    return com_campo, total


async def aplicar(lote: int) -> int:
    """`$unset` em lotes. Devolve quantos documentos foram alterados.

    Em lotes e não de uma vez: um `update_many` sobre centenas de
    milhares de documentos segura o servidor durante a operação toda, e
    esta colecção é lida pelo sino das notificações de toda a gente.
    """
    alterados = 0
    while True:
        ids = [
            d["_id"]
            for d in await db.notifications.find(
                {CAMPO: {"$exists": True}}, {"_id": 1},
            ).limit(lote).to_list(lote)
        ]
        if not ids:
            break
        resultado = await db.notifications.update_many(
            {"_id": {"$in": ids}}, {"$unset": {CAMPO: ""}},
        )
        alterados += resultado.modified_count
        print(f"  … {alterados} documento(s) limpos")
        if resultado.modified_count == 0:
            # Defesa contra ciclo infinito: se o `$unset` não mexeu em
            # nada mas a procura continua a devolver ids, algo está
            # errado e parar é melhor do que rodar para sempre.
            print("AVISO: o $unset não alterou nada neste lote — a parar.")
            break
    return alterados


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true",
                        help="Executa o $unset (por omissão só conta)")
    parser.add_argument("--lote", type=int, default=5000,
                        help="Documentos por lote (omissão 5000)")
    args = parser.parse_args()

    com_campo, total = await contar()
    print(f"Notificações: {total}")
    print(f"  com `{CAMPO}`: {com_campo}")

    if not com_campo:
        print("Nada a limpar.")
        return 0
    if not args.aplicar:
        print("Correr com --aplicar para remover o campo.")
        return 0

    print(f"A remover `{CAMPO}` em lotes de {args.lote} …")
    alterados = await aplicar(args.lote)
    restantes, _ = await contar()
    print(f"  {alterados} documento(s) alterados. Restantes: {restantes}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
