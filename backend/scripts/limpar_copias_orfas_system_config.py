#!/usr/bin/env python3
"""Apaga as cópias órfãs de ``system_config`` (``company:<id>``) — Out 2026.

    # ler e contar (omissão — NÃO escreve)
    python scripts/limpar_copias_orfas_system_config.py

    # apagar só as cópias PROVADAMENTE iguais à global
    python scripts/limpar_copias_orfas_system_config.py --aplicar

    # incluir também as de empresas que já não existem
    python scripts/limpar_copias_orfas_system_config.py --aplicar --incluir-sem-empresa

O QUE É UMA CÓPIA ÓRFÃ
======================
Ver ``services/system_config_orphans.py``: um documento ``company:<id>`` igual
à global em tudo o que não é volátil. Antes da correcção do copy-on-write,
LER a configuração de uma empresa sem config própria gravava esta cópia — com
as credenciais da global em claro. As que divergem da global **nunca** são
apagadas (podem ser configuração real); ficam listadas, com as secções que
diferem e SEM valores.

CORRE CONTRA PRODUÇÃO DE PROPÓSITO
==================================
Como os outros scripts de operações, não chama ``require_non_production_db``:
as cópias existem em produção. Em troca:

  * a omissão é LER e contar — apagar exige ``--aplicar``;
  * só ``_id`` com prefixo ``company:`` é tocado (a colecção guarda também
    templates RGPD/minutas, configuração financeira, etc.);
  * a eliminação é condicional ao ``updated_at`` lido: se alguém gravou entre
    a leitura e a eliminação, o documento NÃO é apagado;
  * as cópias idênticas reconstroem-se da global, por isso não se escreve
    cópia de segurança (seria mais um ficheiro com credenciais em claro).

DEPOIS DE CORRER
================
A API mantém uma cache de 60 s da configuração; as instâncias em execução
deixam de ver as cópias dentro desse prazo (a leitura devolve a herdada da
global, sem a gravar).

CÓDIGOS DE SAÍDA
================
    0  nada a fazer, ou ``--aplicar`` correu sem falhas
    1  há documentos que EXIGEM DECISÃO humana (``divergente``/``ilegivel``)
    2  a leitura não aconteceu (sem base de dados / sem configuração global)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.system_config_orphans import (  # noqa: E402
    ID_GLOBAL,
    PREFIXO,
    VEREDICTO_DIVERGENTE,
    VEREDICTO_IDENTICA,
    VEREDICTO_ILEGIVEL,
    VEREDICTO_SEM_EMPRESA,
    ConfiguracaoGlobalIlegivel,
    a_apagar,
    classificar_todas,
    resumir,
)

ROTULOS = {
    VEREDICTO_IDENTICA: "cópia idêntica à global — apagável",
    VEREDICTO_SEM_EMPRESA: "cópia idêntica de empresa que já não existe — apagável com --incluir-sem-empresa",
    VEREDICTO_DIVERGENTE: "EXIGE DECISÃO — difere da global (pode ser configuração própria)",
    VEREDICTO_ILEGIVEL: "EXIGE DECISÃO — não valida como configuração",
}
ORDEM = (VEREDICTO_ILEGIVEL, VEREDICTO_DIVERGENTE, VEREDICTO_SEM_EMPRESA, VEREDICTO_IDENTICA)


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aplicar", action="store_true",
                   help="apaga as cópias provadamente idênticas (sem esta bandeira só lê e conta)")
    p.add_argument("--incluir-sem-empresa", action="store_true",
                   help="apaga também as cópias idênticas de empresas que já não existem")
    return p.parse_args()


async def _carregar(db):
    """(documento global, documentos company:<id>, ids das empresas existentes)."""
    doc_global = await db.system_config.find_one({"_id": ID_GLOBAL})
    docs = await db.system_config.find({"_id": {"$regex": f"^{PREFIXO}"}}).to_list(100000)
    empresas = await db.companies.find({}, {"_id": 0, "id": 1}).to_list(100000)
    return doc_global, docs, {e.get("id") for e in empresas if e.get("id")}


async def _apagar(db, doc: dict) -> bool:
    """Elimina UM documento, condicionado ao ``updated_at`` que foi lido."""
    filtro = {"_id": doc["_id"], "updated_at": doc.get("updated_at")}
    resultado = await db.system_config.delete_one(filtro)
    return bool(resultado.deleted_count)


def _imprimir(veredictos, resumo, estados, aplicado: bool) -> None:
    print("=" * 72)
    print("CÓPIAS ÓRFÃS DE system_config (company:<id>)")
    print("=" * 72)
    print(f"Documentos company:<id> encontrados: {resumo.total}")
    print("-" * 72)
    for chave in ORDEM:
        quantos = resumo.por_veredicto.get(chave, 0)
        if quantos:
            print(f"  {quantos:>5}  {ROTULOS[chave]}")
    print("-" * 72)
    for v in veredictos:
        if v.veredicto == VEREDICTO_IDENTICA and not aplicado:
            continue
        marca = {"apagado": "✔", "inalterado": "✖"}.get(estados.get(v.doc_id, ""), "·")
        print(f"  {marca} {v.veredicto:<18} {v.doc_id}")
        if v.seccoes_diferentes:
            print(f"      secções diferentes: {', '.join(v.seccoes_diferentes)}")
        if v.veredicto in (VEREDICTO_DIVERGENTE, VEREDICTO_ILEGIVEL):
            print(f"      motivo: {v.motivo}  (updated_at={v.updated_at})")
    print("=" * 72)


async def principal() -> int:
    args = _argumentos()
    try:
        from database import db
        doc_global, docs, empresas = await _carregar(db)
        veredictos = classificar_todas(docs, doc_global, empresas)
    except ConfiguracaoGlobalIlegivel as exc:
        print(f"LEITURA NÃO REALIZADA: {exc}")
        print("Sem a global não há com quê comparar — nada foi classificado nem apagado.")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"LEITURA NÃO REALIZADA: não foi possível ler a base de dados: {exc}")
        print("Sem leitura não há contagem — e um 0 aqui leria-se como «não há cópias».")
        return 2

    resumo = resumir(veredictos)
    estados: dict = {}
    if args.aplicar:
        por_id = {d["_id"]: d for d in docs}
        for v in a_apagar(veredictos, incluir_sem_empresa=args.incluir_sem_empresa):
            try:
                estados[v.doc_id] = "apagado" if await _apagar(db, por_id[v.doc_id]) else "inalterado"
            except Exception as exc:  # noqa: BLE001
                estados[v.doc_id] = "inalterado"
                print(f"[ERRO] {v.doc_id}: {exc}")

    _imprimir(veredictos, resumo, estados, args.aplicar)
    if not args.aplicar and any(v.apagavel_por_omissao for v in veredictos):
        print("→ Nada foi apagado. Correr outra vez com --aplicar.")
    if args.aplicar:
        print(f"Apagados: {sum(1 for e in estados.values() if e == 'apagado')} "
              f"· inalterados: {sum(1 for e in estados.values() if e == 'inalterado')}")

    exigem = resumo.por_veredicto.get(VEREDICTO_DIVERGENTE, 0) + resumo.por_veredicto.get(VEREDICTO_ILEGIVEL, 0)
    return 1 if exigem else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
