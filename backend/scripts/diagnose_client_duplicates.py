#!/usr/bin/env python3
"""Quantos clientes violam a regra «NIF e Email não se repetem» (D-38 → D-42, identidade global).

A PERGUNTA
==========
A regra é nova e a base de dados é antiga. A guarda (`client_uniqueness`)
só verifica o que entra e o que muda; **o que já lá está fica como está**.
Antes de decidir se os índices únicos parciais (`db_indexes`: NIF e Email,
globais — são a única coisa que fecha a corrida entre dois pedidos simultâneos)
se constroem, é preciso saber quantos clientes existentes os violariam, onde e
por que campo. É isso que este
script imprime. A classificação vive em `services/client_duplicates_audit.py`
(puro, com testes); aqui só se lê a base de dados. Para RESOLVER, `scripts/resolve_client_duplicates.py`.

ESTRITAMENTE SÓ DE LEITURA
==========================
Não tem nenhuma bandeira de escrita e não chama nenhuma operação de escrita
(há um teste por AST que o afirma). Corre contra produção DE PROPÓSITO —
como o `diagnose_assignment_drift.py` e o `diagnose_s3_name_fallback.py`,
NÃO chama `require_non_production_db`: a dívida que mede está nos dados
reais. Resolver os duplicados é uma decisão humana, cliente a cliente
(qual se mantém? os processos passam para onde?), nunca um automatismo.

O QUE SAI
=========
    * por rede: nº de clientes, nº de grupos repetidos por campo e nº de
      clientes envolvidos;
    * os grupos (valor MASCARADO + ids dos clientes + nº de processos de cada);
    * «casos»: clientes ligados por qualquer campo contam como UMA decisão
      (a mesma pessoa inserida duas vezes repete NIF, email e telemóvel de
      uma só vez — são 3 grupos e 1 caso);
    * quantos grupos atravessam redes DIFERENTES (a mesma pessoa com processos
      em duas empresas: é o caso que `resolve_client_duplicates` funde);
    * o veredicto: «índice único viável» ou quantos casos o impedem.

Os valores saem mascarados (`*****9461`, `a***@dominio.pt`) e sem nomes;
`--dados-pessoais` mostra-os completos. O CSV segue a mesma regra.

CÓDIGOS DE SAÍDA
================
    0  a leitura aconteceu (houve ou não duplicados — o relatório diz)
    2  a leitura NÃO aconteceu (base de dados sem resposta): um relatório
       de zero clientes leria-se como «não há duplicados»

USO
===
    MONGO_URL=... DB_NAME=... TENANT_DEFAULT_NETWORK_ID=... \
        python scripts/diagnose_client_duplicates.py
    ... python scripts/diagnose_client_duplicates.py --csv /tmp/d38.csv --limite-exemplos 50
    ... python scripts/diagnose_client_duplicates.py --dados-pessoais
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo.errors import PyMongoError  # noqa: E402
from services.client_duplicates_audit import (  # noqa: E402
    Registo,
    Relatorio,
    auditar,
    esta_eliminado,
    mostrar,
    rede_do_documento,
    registo_de,
    resumir,
)
from services.client_uniqueness import CAMPOS_UNICOS, ROTULOS  # noqa: E402

#: Só os campos precisos — um cliente inteiro traz dados pessoais que o
#: relatório não usa (regra do `diagnose_assignment_drift`).
PROJECCAO_CLIENTE = {
    "_id": 0, "id": 1, "nome": 1, "name": 1, "client_name": 1,
    "is_deleted": 1, "status": 1,
    "network_id": 1, "company_id": 1, "company": 1, "company_name": 1,
    "dados_pessoais.nif": 1, "dados_pessoais.nif_hash": 1,
    "contacto.email": 1, "contacto.email_hash": 1,
}
PROJECCAO_EMPRESA = {"_id": 0, "id": 1, "name": 1, "network_id": 1}

#: Tecto de cada leitura: um diagnóstico não pode pendurar a base de produção.
MAX_TIME_MS = 120_000
TAMANHO_DO_LOTE = 500


def _argumentos():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--limite-exemplos", type=int, default=20,
        help="Quantos grupos imprimir (default 20, os maiores primeiro). "
             "A lista completa sai com --csv.",
    )
    p.add_argument(
        "--csv", default=None,
        help="Escreve todos os grupos neste ficheiro (valores mascarados, "
             "salvo --dados-pessoais).",
    )
    p.add_argument(
        "--dados-pessoais", action="store_true",
        help="Mostra os valores completos (NIF, email, telemóvel) e os nomes. "
             "Por omissão saem mascarados e sem nomes.",
    )
    return p.parse_args()


async def _redes_das_empresas() -> dict[str, str | None]:
    """company id/nome → rede (a ilha implícita quando a empresa não tem grupo)."""
    from database import db
    from services.tenant_network import resolve_network_id

    mapa: dict[str, str | None] = {}
    cursor = db.companies.find({}, PROJECCAO_EMPRESA).max_time_ms(MAX_TIME_MS)
    async for empresa in cursor:
        rede = resolve_network_id(empresa)
        for chave in (empresa.get("id"), empresa.get("name")):
            if chave:
                mapa[str(chave).strip()] = rede
    return mapa


async def _carregar_registos() -> list[Registo]:
    from database import db
    from services.encryption import decrypt_client_data

    redes = await _redes_das_empresas()
    registos: list[Registo] = []
    cursor = db.clients.find({}, PROJECCAO_CLIENTE).max_time_ms(MAX_TIME_MS)
    async for doc in cursor:
        if esta_eliminado(doc) or not doc.get("id"):
            continue
        registos.append(registo_de(
            doc, rede=rede_do_documento(doc, redes), decifrar=decrypt_client_data,
        ))
    return registos


async def _processos_por_cliente(ids: list[str]) -> dict[str, int]:
    """Quantos processos (não eliminados) cada cliente tem — ajuda a escolher qual manter."""
    from database import db

    contagem: dict[str, int] = {}
    for i in range(0, len(ids), TAMANHO_DO_LOTE):
        lote = ids[i:i + TAMANHO_DO_LOTE]
        pipeline = [
            {"$match": {"client_id": {"$in": lote}, "is_deleted": {"$ne": True}}},
            {"$group": {"_id": "$client_id", "n": {"$sum": 1}}},
        ]
        async for linha in db.processes.aggregate(pipeline, maxTimeMS=MAX_TIME_MS):
            contagem[linha["_id"]] = linha["n"]
    return contagem


def _imprimir(relatorio: Relatorio, registos: list[Registo], processos: dict[str, int], args) -> None:
    resumo = resumir(relatorio)
    nomes = {r.id: r.nome for r in registos}
    completos = args.dados_pessoais

    print("=" * 70)
    print("D-42 — DUPLICADOS DE NIF / EMAIL (identidade global, só leitura)")
    print("=" * 70)
    print(f"Clientes activos auditados: {resumo['total_clientes']}")
    for rede, n in sorted(resumo["clientes_por_rede"].items()):
        print(f"  {n:>6}  {rede}")
    print("-" * 70)

    if resumo["sem_rede_de_omissao"]:
        print("  ⚠ TENANT_DEFAULT_NETWORK_ID não está definido: a pilha por carimbar\n"
              "    ficou num grupo à parte «(por carimbar)». Com a variável de produção\n"
              "    definida, esses clientes contam na rede de omissão.")
        print("-" * 70)
    if resumo["sem_decifrar"]:
        print("  ⚠ Valores que NÃO se conseguiram decifrar (comparados pelo índice cego):")
        for campo, n in sorted(resumo["sem_decifrar"].items()):
            print(f"      {ROTULOS[campo]}: {n}")
        print("    Confirmar que a chave de cifra do ambiente é a de produção.")
        print("-" * 70)

    print("DUPLICADOS (em qualquer rede)")
    if not resumo["grupos"]:
        print("  Nenhuma.")
    for rede, linha in resumo["por_rede"].items():
        por_campo = ", ".join(
            f"{ROTULOS[c]} {linha['grupos'][c]}" for c in CAMPOS_UNICOS if linha["grupos"][c]
        )
        print(f"  {rede}: {linha['clientes']} cliente(s) envolvido(s) — grupos repetidos: {por_campo}")
    por_campo_total = ", ".join(f"{ROTULOS[c]} {resumo['por_campo'][c]}" for c in CAMPOS_UNICOS)
    print(f"  TOTAL: {resumo['grupos']} grupo(s) repetido(s) ({por_campo_total})")
    print(f"  CLIENTES ENVOLVIDOS: {resumo['clientes_afectados']}  "
          f"→  CASOS A DECIDIR À MÃO: {resumo['casos']}")
    print("-" * 70)

    entre_redes = resumo["grupos_entre_redes"]
    if entre_redes:
        print("GRUPOS QUE ATRAVESSAM REDES (o mesmo cliente com processos em empresas diferentes):")
        for campo in CAMPOS_UNICOS:
            if entre_redes.get(campo):
                print(f"  {ROTULOS[campo]}: {entre_redes[campo]} valor(es)")
        print("-" * 70)

    if resumo["total_clientes"] == 0:
        print("→ NENHUM cliente activo foi lido: confirmar DB_NAME antes de tirar conclusões "
              "(zero clientes não é «sem duplicados»).")
    elif resumo["indice_unico_viavel"]:
        print("→ Os índices únicos de NIF e Email são VIÁVEIS: não há nenhum duplicado a resolver.")
    else:
        print(f"→ Os índices únicos NÃO se constroem ainda: {resumo['casos']} caso(s) "
              "têm de ser resolvidos antes\n  (`python -m scripts.resolve_client_duplicates`: "
              "descreve; `--aplicar` funde o que é inequívoco).")
    print("-" * 70)

    if relatorio.grupos:
        mostrados = relatorio.grupos[:args.limite_exemplos]
        print(f"GRUPOS (maiores primeiro, {len(mostrados)} de {len(relatorio.grupos)}):")
        for g in mostrados:
            print(f"  [{' + '.join(g.redes)}] {ROTULOS[g.campo]} {mostrar(g.campo, g.chave, valores_completos=completos)}"
                  f" — {len(g.membros)} clientes")
            for cid in g.membros:
                nome = f" «{nomes.get(cid, '')}»" if completos else ""
                print(f"      cliente:{cid}{nome}  ({processos.get(cid, 0)} processo(s))")

    if args.csv:
        destino = Path(args.csv)
        with destino.open("w", newline="", encoding="utf-8") as fh:
            escritor = csv.writer(fh)
            escritor.writerow(["redes", "campo", "valor", "clientes", "ids", "processos"])
            for g in relatorio.grupos:
                escritor.writerow([
                    " + ".join(g.redes), g.campo, mostrar(g.campo, g.chave, valores_completos=completos),
                    len(g.membros), ";".join(g.membros),
                    ";".join(str(processos.get(c, 0)) for c in g.membros),
                ])
        print(f"\nLista completa ({len(relatorio.grupos)} grupos) → {destino}")
    print("=" * 70)


async def principal() -> int:
    args = _argumentos()
    try:
        registos = await _carregar_registos()
        relatorio = auditar(registos)
        em_conflito = sorted({cid for g in relatorio.grupos for cid in g.membros})
        processos = await _processos_por_cliente(em_conflito) if em_conflito else {}
    except PyMongoError as exc:
        print("=" * 70)
        print("D-42 — MEDIÇÃO NÃO REALIZADA")
        print("=" * 70)
        print(f"  A base de dados não respondeu: {exc}")
        print(
            "\n  Nenhum cliente foi lido, logo não há contagem nenhuma — e um\n"
            "  relatório de zero clientes leria-se como «não há duplicados».\n"
            "  Confirmar MONGO_URL/DB_NAME e repetir."
        )
        print("=" * 70)
        return 2
    _imprimir(relatorio, registos, processos, args)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
