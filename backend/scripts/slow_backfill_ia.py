#!/usr/bin/env python3
"""Reanálise retroactiva LENTA do Index: o banco dos extratos e a localidade dos recibos (Out 2026).

    # contar o que falta (omissão — NÃO chama a IA, NÃO escreve)
    python -m scripts.slow_backfill_ia

    # processar UM lote (pensado para cron)
    SLOW_BACKFILL_BATCH_SIZE=20 python -m scripts.slow_backfill_ia --aplicar

    # exemplo de cron: de 30 em 30 minutos, 20 documentos
    */30 * * * *  cd /app/backend && python -m scripts.slow_backfill_ia --aplicar >> /var/log/slow_backfill.log 2>&1

O QUE FAZ
=========
Procura documentos já analisados a que falta o BANCO (extratos) ou a LOCALIDADE da entidade (recibos), relê-os
com a IA e acrescenta SÓ esse campo. Cada execução faz no máximo `SLOW_BACKFILL_BATCH_SIZE` documentos (20 por
omissão, tecto 200) com uma pausa entre chamadas (`SLOW_BACKFILL_PAUSE_SECONDS`, 1 s). A impressão digital de cada
documento NÃO muda e cada um leva uma marca (`slow_backfill_ia`): o que o documento realmente não diz não se paga
duas vezes e nada entra em ciclo. Ver `services/index_slow_backfill.py` para as regras.

OPÇÕES
======
  --aplicar            chama a IA e grava (omissão: só conta)
  --batch-size N       tamanho do lote (vence a variável de ambiente; inválido → 20; nunca acima de 200)
  --tipo extrato|recibo   só um dos dois
  --permitir-simulado  (dev/testes) corre mesmo com o motor simulado — escreve dados SIMULADOS

CÓDIGOS DE SAÍDA:  0 ok · 2 sem base de dados · 3 motor de IA simulado (recusado)

O progresso sai no stdout, uma linha por documento, só com ids e contagens (nunca nomes nem valores), e termina
com `PROGRESSO: …` — uma linha fácil de seguir num log de cron.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import index_slow_backfill as sb  # noqa: E402
from services.index_ai import TIPO_EXTRATO, TIPO_RECIBO  # noqa: E402

TIPOS = {"extrato": TIPO_EXTRATO, "recibo": TIPO_RECIBO}


def _argumentos(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aplicar", action="store_true", help="chama a IA e grava (omissão: só conta)")
    p.add_argument("--batch-size", type=int, default=None, help="documentos por execução")
    p.add_argument("--tipo", choices=sorted(TIPOS), default=None)
    p.add_argument("--permitir-simulado", action="store_true", help="dev/testes: corre com o motor simulado")
    return p.parse_args(argv)


async def principal(argv=None) -> int:
    args = _argumentos(argv)
    tipos = (TIPOS[args.tipo],) if args.tipo else None
    tamanho = sb.tamanho_do_lote(pedido=args.batch_size)
    try:
        faltam = await sb.contar_candidatos(tipos)
    except Exception as exc:  # noqa: BLE001
        print(f"LEITURA NÃO REALIZADA: {exc}\nSem leitura não há contagem — um 0 aqui leria-se como «já está tudo feito».")
        return 2

    total = sum(faltam.values())
    print(f"[slow-backfill] em falta: {', '.join(f'{k}={v}' for k, v in faltam.items()) or 'nada'} · lote={tamanho}")
    if not args.aplicar:
        if total:
            print("→ Nada foi chamado nem gravado. Correr outra vez com --aplicar (um lote por execução).")
        return 0
    if not total:
        print("PROGRESSO: concluído (nada em falta).")
        return 0

    try:
        resumo = await sb.correr_lote(
            tamanho=tamanho, tipos=tipos, pausa=sb.pausa_entre_chamadas(), permitir_simulado=args.permitir_simulado,
        )
    except sb.IASimulada as exc:
        print(f"RECUSADO: {exc}")
        return 3

    estados = resumo["por_estado"]
    restantes = sum((await sb.contar_candidatos(tipos)).values())
    print(
        "PROGRESSO: "
        f"lote={resumo['candidatos']}/{resumo['lote']} "
        f"preenchidos={estados.get('preenchido', 0)} sem_valor={estados.get('sem_valor', 0)} "
        f"adiados={estados.get('adiado', 0)} falhados={estados.get('falhou', 0)} "
        f"outros={sum(v for k, v in estados.items() if k not in ('preenchido', 'sem_valor', 'adiado', 'falhou'))} "
        f"processos_recalculados={resumo['recalculados']} restantes={restantes}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
