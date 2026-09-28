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
    ORIGEM_ATRIBUICAO_LEGADA,
    ORIGEM_INDETERMINADA,
    PAPEIS,
    VEREDICTO_AMBIGUO,
    VEREDICTO_DIVERGENTE,
    VEREDICTO_EM_FALTA,
    correccao_do_processo,
    desfasamentos_do_processo,
    origem_do_ambiguo,
    reposicao_de_listas_do_processo,
    resumir,
    resumir_ambiguos,
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
        "--repor-listas",
        action="store_true",
        help="Para os ambíguos provados como ATRIBUIÇÃO LEGADA, escreve a "
             "lista em falta a partir do campo singular (o caminho OPOSTO "
             "ao de limpar). Não alarga acesso nenhum: quem está no "
             "singular já recebe alertas e já vê o processo.",
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

    if args.repor_listas and not args.corrigir:
        print("`--repor-listas` só faz sentido com `--corrigir`.")
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

    # ── Desambiguar com o histórico ──────────────────────────────────
    # Só para os processos ambíguos: ler o histórico dos 333 seria caro e
    # inútil. A ordem é do mais antigo para o mais recente, porque o que
    # decide é o ÚLTIMO acontecimento de atribuição.
    historicos: dict[str, dict[str, list]] = {}
    for p in ambiguos:
        pid = p.get("id")
        if not pid:
            continue
        entradas = []
        cursor = db.history.find(
            {"process_id": pid},
            {"_id": 0, "field": 1, "action": 1, "new_value": 1, "created_at": 1},
        ).sort("created_at", 1)
        async for entrada in cursor:
            entradas.append(entrada)
        historicos[pid] = {papel: entradas for papel, _lista, _campos in PAPEIS}

    resumo_ambiguo = resumir_ambiguos(ambiguos, historicos_por_processo=historicos)

    if ambiguos:
        print("  Ambíguos por ORIGEM (papel : de onde veio):")
        for chave in sorted(resumo_ambiguo["por_papel_e_origem"]):
            print(f"    {chave:<58} {resumo_ambiguo['por_papel_e_origem'][chave]:>6}")
        print()
        print("    desatribuicao     → resíduo provado. `--incluir-ambiguos` limpa.")
        print("    atribuicao_legada → o processo TEM dono. `--repor-listas` repõe")
        print("                        a lista; limpar desatribuiria trabalho real.")
        print("    indeterminada     → sem prova. Fica para decisão humana.")
        print()

        print(f"  Exemplos ambíguos (até {MAX_EXEMPLOS}):")
        for p in ambiguos[:MAX_EXEMPLOS]:
            campos = {
                d.campo: d.valor_actual
                for d in desfasamentos_do_processo(p)
                if d.veredicto == VEREDICTO_AMBIGUO
            }
            do_processo = historicos.get(p.get("id"), {})
            origens = {
                papel: origem_do_ambiguo(p, papel, historico=do_processo.get(papel))
                for papel, _lista, _campos in PAPEIS
                if any(
                    d.papel == papel and d.veredicto == VEREDICTO_AMBIGUO
                    for d in desfasamentos_do_processo(p)
                )
            }
            print(
                f"    #{p.get('process_number', '?')} {p.get('id', '?')} "
                f"→ {campos} | {origens}"
            )
        print()

        # QUEM aparece nos singulares. É a linha que transforma "N
        # processos indecidíveis" em "duas pessoas a confirmar": os
        # mesmos ids repetidos não são actividade orgânica de gente a
        # atribuir processos um a um — são uma escrita em massa, e isso
        # diz-se olhando para a concentração, não para a lista de ids.
        responsaveis = resumo_ambiguo.get("responsaveis_por_origem", {})
        if responsaveis:
            print("  Quem aparece nos campos singulares (id : nº de papéis):")
            for origem in sorted(responsaveis):
                pares = sorted(
                    responsaveis[origem].items(), key=lambda kv: -kv[1]
                )
                print(f"    {origem}:")
                for uid, quantos in pares[:MAX_EXEMPLOS]:
                    nome = ""
                    doc = await db.users.find_one(
                        {"id": uid}, {"name": 1, "role": 1, "is_active": 1}
                    )
                    if doc:
                        estado = "activo" if doc.get("is_active") else "INACTIVO"
                        nome = f"  {doc.get('name', '?')} ({doc.get('role', '?')}, {estado})"
                    else:
                        nome = "  ⚠ utilizador NÃO EXISTE"
                    print(f"      {uid}  ×{quantos}{nome}")
                if len(pares) > MAX_EXEMPLOS:
                    print(f"      … mais {len(pares) - MAX_EXEMPLOS} id(s)")
            print()

        indeterminados = resumo_ambiguo["processos_por_origem"].get(
            ORIGEM_INDETERMINADA, []
        )
        if indeterminados:
            papeis = sum(
                n for chave, n in resumo_ambiguo["por_papel_e_origem"].items()
                if chave.endswith(f":{ORIGEM_INDETERMINADA}")
            )
            print(
                f"  INDETERMINADOS: {len(indeterminados)} processo(s), "
                f"{papeis} papel(éis) — nenhum automatismo lhes toca."
            )
            print(f"    {', '.join(indeterminados)}")
            print()

    if not args.corrigir:
        print("  MODO LEITURA. Nada foi escrito.")
        print("  Para aplicar as correcções inequívocas: --corrigir")
        print("=" * 66)
        return 0

    corrigidos = 0
    campos_escritos = 0
    listas_repostas = 0
    for processo in processos:
        pid = processo.get("id")
        do_processo = historicos.get(pid, {})

        escrita: dict = {}

        # ORDEM: repor a lista PRIMEIRO. Só depois se calcula a correcção
        # dos singulares, e sobre o documento JÁ com a lista — senão o
        # processo saía desta passagem com a lista reposta e os
        # singulares em falta, ou seja, ainda desfasado. (Deu-se por isso
        # a correr o script duas vezes no laboratório local: a segunda
        # ainda tinha trabalho.)
        if args.repor_listas:
            reposicao = reposicao_de_listas_do_processo(
                processo, historicos_por_papel=do_processo
            )
            if reposicao:
                # O nome acompanha a lista: um cartão de Atribuição com
                # ids e sem nomes fica em branco na mesma.
                for campo_da_lista, ids in reposicao.items():
                    escrita[campo_da_lista] = ids
                    campo_nomes = (
                        "consultor_names"
                        if campo_da_lista == "assigned_consultor_ids"
                        else "mediador_names"
                    )
                    nomes = []
                    for uid in ids:
                        doc = await db.users.find_one({"id": uid}, {"name": 1})
                        if doc and doc.get("name"):
                            nomes.append(doc["name"])
                    if nomes:
                        escrita[campo_nomes] = nomes
                listas_repostas += 1

        escrita.update(
            correccao_do_processo(
                {**processo, **escrita},
                incluir_ambiguos=args.incluir_ambiguos,
                historicos_por_papel=do_processo,
            )
        )

        if not escrita:
            continue
        await db.processes.update_one({"id": pid}, {"$set": escrita})
        corrigidos += 1
        campos_escritos += len(escrita)

    print(f"  CORRIGIDOS: {corrigidos} processos, {campos_escritos} campos.")
    if args.repor_listas:
        print(f"  LISTAS REPOSTAS: {listas_repostas} processos.")
    intocados = (
        resumo_ambiguo["por_papel_e_origem"] and not args.incluir_ambiguos
    )
    if intocados:
        print(
            "  Os ambíguos ficaram INTACTOS de propósito — ver o cabeçalho "
            "deste ficheiro."
        )
    if args.incluir_ambiguos:
        legados = len(
            resumo_ambiguo["processos_por_origem"].get(ORIGEM_ATRIBUICAO_LEGADA, [])
        )
        indets = len(
            resumo_ambiguo["processos_por_origem"].get(ORIGEM_INDETERMINADA, [])
        )
        if legados or indets:
            print(
                f"  {legados} atribuição(ões) legada(s) e {indets} "
                "indeterminado(s) NÃO foram limpos, apesar da bandeira: "
                "limpá-los deixaria o processo sem dono."
            )
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
