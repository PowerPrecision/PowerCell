#!/usr/bin/env python3
"""Conta (e opcionalmente corrige) o desfasamento de atribuição nos processos.

PARA QUE SERVE (Lote 6, ponto 8)
================================
Até ao Lote 5, `build_clear_consultor_fields` limpava quatro dos seis
campos canónicos e deixava `consultor_id` e `consultant_id` com o valor
antigo. A correcção parou de PRODUZIR o problema; **não limpou o que já
existia**. Dois leitores continuam a consultar esses campos:

  * `services/alerts.py` — notifica quem estiver em `consultor_id`;
  * `process_list_filters` — usa `consultant_id` em "Os Meus Processos".

É a hipótese principal para os alertas que chegam a consultores de
processos que não são deles. Este script mede-a.

ESTE SCRIPT CORRE CONTRA PRODUÇÃO — DE PROPÓSITO
================================================
Ao contrário dos scripts de seed, NÃO chama `require_non_production_db`:
a dívida que mede está na base de dados real. Em troca:

  * a omissão é **ler e contar**; escrever exige `--corrigir`;
  * `--corrigir` só toca no que é INEQUÍVOCO (ver abaixo);
  * os casos ambíguos exigem `--incluir-ambiguos`, uma segunda ordem
    explícita, porque corrigi-los pode DESATRIBUIR trabalho real.

A AMBIGUIDADE, QUE É O PONTO TODO
=================================
"Lista vazia + campo singular preenchido" não é sinónimo de resíduo. O
`dual_auto_assign_on_pre_registo_transition` gravava SÓ `consultant_id`,
pelo que há processos legitimamente atribuídos cuja lista nunca foi
escrita. Limpar esses deixa o processo sem dono, e um processo sem dono
não se nota até alguém reparar que ninguém lhe pega — um carimbo errado é
permanente, e é a mesma razão pela qual o `backfill_network_id` se recusa
a adivinhar.

USO
===
    MONGO_URL=... DB_NAME=... python scripts/diagnose_assignment_drift.py
    MONGO_URL=... DB_NAME=... python scripts/diagnose_assignment_drift.py --corrigir
    MONGO_URL=... DB_NAME=... python scripts/diagnose_assignment_drift.py \
        --corrigir --incluir-ambiguos
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.assignment_drift import (  # noqa: E402
    VEREDICTO_AMBIGUO,
    VEREDICTO_DIVERGENTE,
    VEREDICTO_EM_FALTA,
    correccao_do_processo,
    desfasamentos_do_processo,
    resumir,
)
from services.process_staff_assignment import (  # noqa: E402
    CONSULTOR_ID_FIELDS,
    MEDIADOR_ID_FIELDS,
)

#: Só os campos precisos. Um processo inteiro traz o cliente desencriptado
#: e não há motivo nenhum para o ler aqui.
PROJECCAO = {
    "_id": 0,
    "id": 1,
    "process_number": 1,
    "is_deleted": 1,
    "assigned_consultor_ids": 1,
    "assigned_mediador_ids": 1,
    **{campo: 1 for campo in CONSULTOR_ID_FIELDS},
    **{campo: 1 for campo in MEDIADOR_ID_FIELDS},
}

MAX_EXEMPLOS = 10


def _argumentos():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--corrigir",
        action="store_true",
        help="Aplica as correcções INEQUÍVOCAS (divergente e em_falta). "
             "Sem esta bandeira o script apenas lê e conta.",
    )
    p.add_argument(
        "--incluir-ambiguos",
        action="store_true",
        help="Aplica TAMBÉM os casos ambíguos (lista vazia + singular "
             "preenchido). ATENÇÃO: pode desatribuir processos legados que "
             "só têm `consultant_id`. Ler o cabeçalho antes de usar.",
    )
    p.add_argument(
        "--incluir-eliminados",
        action="store_true",
        help="Analisa também os processos com `is_deleted`.",
    )
    return p.parse_args()


async def principal() -> int:
    args = _argumentos()

    if args.incluir_ambiguos and not args.corrigir:
        print("`--incluir-ambiguos` só faz sentido com `--corrigir`.")
        return 2

    if not os.environ.get("MONGO_URL"):
        print("MONGO_URL por definir — nada a fazer.")
        return 2

    from database import db

    filtro = {} if args.incluir_eliminados else {"is_deleted": {"$ne": True}}

    processos = []
    cursor = db.processes.find(filtro, PROJECCAO)
    async for processo in cursor:
        processos.append(processo)

    resumo = resumir(processos)

    print("=" * 66)
    print("DESFASAMENTO DE ATRIBUIÇÃO — processos")
    print("=" * 66)
    print(f"  Base de dados        : {os.environ.get('DB_NAME', '(omissão)')}")
    print(f"  Processos analisados : {resumo['total_analisados']}")
    print(f"  Com desfasamento     : {resumo['processos_afectados']}")
    print()
    print("  Por veredicto:")
    for veredicto, rotulo in (
        (VEREDICTO_DIVERGENTE, "divergente  (lista tem gente, singular aponta para fora)"),
        (VEREDICTO_EM_FALTA, "em_falta    (lista tem gente, singular vazio)"),
        (VEREDICTO_AMBIGUO, "ambiguo     (lista vazia, singular preenchido)"),
    ):
        print(f"    {rotulo:<58} {resumo['por_veredicto'].get(veredicto, 0):>6}")
    print()
    print("  Por campo (os dois primeiros são os que o Lote 5 deixava para trás):")
    for campo in (*CONSULTOR_ID_FIELDS, *MEDIADOR_ID_FIELDS):
        print(f"    {campo:<58} {resumo['por_campo'].get(campo, 0):>6}")
    print()
    print(f"  Corrigíveis sem ambiguidade : {resumo['processos_corrigiveis']}")
    print(f"  A precisar de decisão humana: {resumo['processos_ambiguos']}")
    print()

    ambiguos = [
        p for p in processos
        if any(d.veredicto == VEREDICTO_AMBIGUO for d in desfasamentos_do_processo(p))
    ]
    if ambiguos:
        print(f"  Exemplos ambíguos (até {MAX_EXEMPLOS}):")
        for p in ambiguos[:MAX_EXEMPLOS]:
            campos = {
                d.campo: d.valor_actual
                for d in desfasamentos_do_processo(p)
                if d.veredicto == VEREDICTO_AMBIGUO
            }
            print(f"    #{p.get('process_number', '?')} {p.get('id', '?')} → {campos}")
        print()

    if not args.corrigir:
        print("  MODO LEITURA. Nada foi escrito.")
        print("  Para aplicar as correcções inequívocas: --corrigir")
        print("=" * 66)
        return 0

    corrigidos = 0
    campos_escritos = 0
    for processo in processos:
        correccao = correccao_do_processo(
            processo, incluir_ambiguos=args.incluir_ambiguos
        )
        if not correccao:
            continue
        await db.processes.update_one({"id": processo["id"]}, {"$set": correccao})
        corrigidos += 1
        campos_escritos += len(correccao)

    print(f"  CORRIGIDOS: {corrigidos} processos, {campos_escritos} campos.")
    if not args.incluir_ambiguos and resumo["processos_ambiguos"]:
        print(
            f"  {resumo['processos_ambiguos']} processos ambíguos ficaram INTACTOS "
            "de propósito — ver o cabeçalho deste ficheiro."
        )
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
