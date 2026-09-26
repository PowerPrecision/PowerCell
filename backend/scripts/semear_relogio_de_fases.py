"""
====================================================================
BACKFILL: semear o relógio de fases nos processos legados
====================================================================
Refinamento Analítico e SLAs (Dashboard), Camada 1.5.
Ver `services/phase_clock_backfill.py`.

O QUE FAZ
  Carimba `fase_desde` / `macro_fase_desde` com o `updated_at` nos
  processos que não têm relógio, marcando-os como ESTIMADOS e guardando
  **a qualidade** da estimativa em três níveis:

    plausivel           o BI pode usar para médias
    nunca_tocado        a estimativa é a data de criação — SOBRESTIMA
    tocado_apos_fecho   tocado meses depois de fechar — SUBESTIMA

  Um booleano cego obrigava o BI a escolher entre não ter história nenhuma
  e desenhar médias sobre cinco mil valores aberrantes.

POR OMISSÃO NÃO ESCREVE NADA
  Sem `--aplicar` é uma simulação: lê, classifica e mostra o plano. É a
  mesma disciplina do `limpar_is_notified` — o que se vai escrever em
  12.450 documentos vê-se antes de se escrever.

IDEMPOTENTE
  A condição de ausência (`fase_desde` inexistente) está na QUERY de cada
  escrita, não num `if` em Python: entre a leitura e a escrita pode ter
  havido uma transição REAL, e é ela que manda. Correr isto duas vezes não
  desfaz uma medição.

ORDEM DE OPERAÇÕES
  Corre na MESMA janela do deploy. Até correr, a primeira transição de um
  processo legado acumula um intervalo derivado do `created_at`, que
  sobrestima; o que este script carimba fica marcado como estimado e
  deixa de acumular.

NÃO chama `scripts/env_guard.py`: esse guarda existe para impedir que um
seed de dados simulados escreva em produção, e é contra produção que isto
tem de correr. O que o torna seguro é a simulação por omissão, o filtro de
idempotência em cada escrita e não haver aqui nenhuma operação destrutiva
(`delete_*` / `drop` / `$unset`).

EXECUÇÃO
  cd backend && python -m scripts.semear_relogio_de_fases            # simula
  cd backend && python -m scripts.semear_relogio_de_fases --aplicar  # escreve
  cd backend && python -m scripts.semear_relogio_de_fases --aplicar --lote 2000

  Depois, o `medir_relogio_de_fases` volta a correr e a cobertura do
  relógio deixa de ser zero — é a prova de que isto fez o que diz.
====================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402
from services.phase_clock_backfill import (  # noqa: E402
    PROJECCAO_DO_BACKFILL,
    formatar_plano,
    para_json,
    preparar,
)
from services.process_phase_clock import CAMPO_FASE_DESDE  # noqa: E402

LOTE_POR_OMISSAO = 5000


async def carregar_fases() -> list[dict]:
    return await db.workflow_statuses.find(
        {}, {"_id": 0},
    ).sort("order", 1).to_list(500)


async def ler_processos() -> list[dict]:
    """Os processos vivos, com a projecção mínima."""
    return await db.processes.find(
        {"is_deleted": {"$ne": True}}, PROJECCAO_DO_BACKFILL,
    ).to_list(None)


async def escrever(escritas, *, lote: int) -> int:
    """Aplica as escritas em lotes, com a condição de idempotência.

    Um `bulk_write` por lote e não uma escrita por documento: 12.450 idas
    e voltas ao Atlas levariam minutos e falhariam a meio sem forma de
    saber onde.

    O filtro de cada escrita repete `fase_desde` ausente — é isso que faz
    a operação perder a corrida contra uma transição real em vez de a
    sobrepor.
    """
    from pymongo import UpdateOne

    total = 0
    for inicio in range(0, len(escritas), lote):
        fatia = escritas[inicio:inicio + lote]
        operacoes = [
            UpdateOne(
                {"id": identificador, CAMPO_FASE_DESDE: {"$exists": False}},
                {"$set": campos},
            )
            for identificador, campos in fatia
        ]
        resultado = await db.processes.bulk_write(operacoes, ordered=False)
        escritos = resultado.modified_count or 0
        total += escritos
        print(f"  lote {inicio // lote + 1}: {escritos}/{len(fatia)} escritos")
    return total


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true",
                        help="Escreve. Sem esta bandeira, apenas simula.")
    parser.add_argument("--lote", type=int, default=LOTE_POR_OMISSAO,
                        help=f"Documentos por bulk_write (omissão: {LOTE_POR_OMISSAO})")
    parser.add_argument("--json", dest="ficheiro_json", default=None,
                        help="Escreve o plano em JSON")
    args = parser.parse_args()

    if args.lote < 1:
        print("ERRO: --lote tem de ser >= 1.")
        return 2

    print("A ler as fases configuradas …")
    fases = await carregar_fases()
    print(f"  {len(fases)} fase(s).")

    print("A ler os processos …")
    linhas = await ler_processos()
    print(f"  {len(linhas)} processo(s).")

    # A macro-fase de cada valor de `status` vem do RESOLVEDOR, como em
    # todo o resto: um processo gravado como `cpcv` tem de ser classificado
    # pela macro da fase a que corresponde. Sem isto, os 217 processos de
    # alias e gralha caíam fora da regra do `tocado_apos_fecho`.
    from services.phase_clock_coverage import macro_por_valor

    mapa_de_macros = macro_por_valor((l.get("status") for l in linhas), fases)

    agora = datetime.now(timezone.utc)
    escritas, plano = preparar(linhas, mapa_de_macros, agora=agora)

    if args.aplicar and escritas:
        print(f"A escrever {len(escritas)} documento(s) em lotes de {args.lote} …")
        plano.escritos = await escrever(escritas, lote=args.lote)

    print(formatar_plano(plano, aplicado=args.aplicar))

    if args.ficheiro_json:
        saida = para_json(plano, aplicado=args.aplicar)
        saida["semeado_em"] = agora.isoformat()
        Path(args.ficheiro_json).write_text(
            json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"Plano escrito em {args.ficheiro_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
