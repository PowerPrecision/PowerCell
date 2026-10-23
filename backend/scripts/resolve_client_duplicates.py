#!/usr/bin/env python3
"""Funde os clientes duplicados (NIF/Email) e prepara os índices únicos (D-42/D-40).

A DECISÃO
=========
A direcção decidiu que **NIF e Email definem um cliente único em toda a base
de dados** (o telemóvel não conta). A base é antiga e tem duplicados, incluindo
a mesma pessoa em redes diferentes. Este script junta-os; a regra de quem fica
vive em `services/client_merge_plan.py` (puro, com testes) e a execução em
`services/client_merge_apply.py`.

COMO FUNCIONA (e o que NUNCA faz)
=================================
* A OMISSÃO É LER e dizer o plano. Só `--aplicar` escreve.
* Funde o que é inequívoco: um grupo ligado por NIF e/ou Email onde não há dois
  NIFs diferentes. Os processos, documentos e restantes referências passam para
  o sobrevivente; as redes dos absorvidos ficam em `redes_associadas` (cada
  equipa continua a ver só o seu processo); o absorvido fica ELIMINADO (não
  apagado: é o rasto e a reversão).
* **Os AMBÍGUOS nunca se fundem sozinhos**: dois NIFs diferentes ligados por um
  email partilhado são duas pessoas. Listam-se e decidem-se à mão (corrigir o
  email de um deles); o índice único do email só se constrói depois.
* Nada se move no S3. O telemóvel não é tocado.
* Idempotente: uma segunda passagem não encontra nada a fazer.
* Corre contra produção de propósito (a dívida está nos dados reais): NÃO chama
  `require_non_production_db`. Em troca, o que escreve é só o que o plano diz.
* O relatório mascara NIF/Email e não mostra nomes (`--dados-pessoais` revela).

DEPOIS DA LIMPEZA
=================
Os índices únicos parciais estão DECLARADOS em `services/db_indexes.py`
(`idx_client_nif_hash_unico`, `idx_client_email_hash_unico`) e nascem no
arranque seguinte. `--criar-indices` constrói-os já, a partir dessas mesmas
definições (nunca uma cópia), e recusa-se se ainda houver grupos por resolver.

CÓDIGOS DE SAÍDA
================
    0  nada por resolver, ou tudo o que era inequívoco foi fundido
    1  há grupos AMBÍGUOS por decidir à mão (ou referências por reapontar)
    2  a leitura NÃO aconteceu (base de dados sem resposta)

USO
===
    MONGO_URL=... DB_NAME=... TENANT_DEFAULT_NETWORK_ID=... \
        python -m scripts.resolve_client_duplicates
    ... python -m scripts.resolve_client_duplicates --aplicar
    ... python -m scripts.resolve_client_duplicates --aplicar --criar-indices
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo.errors import PyMongoError  # noqa: E402
from services.client_duplicates_audit import (  # noqa: E402
    esta_eliminado,
    mostrar,
    rede_do_documento,
    registo_de,
)
from services.client_merge_plan import (  # noqa: E402
    AMBIGUO,
    FUNDIR,
    Candidato,
    PlanoDeFusao,
    planear,
    resumir,
)
from services.client_uniqueness import CAMPOS_UNICOS, ROTULOS  # noqa: E402

#: O cliente inteiro: para PREENCHER o que falta ao sobrevivente é preciso o documento.
PROJECCAO_EMPRESA = {"_id": 0, "id": 1, "name": 1, "network_id": 1}
MAX_TIME_MS = 120_000
TAMANHO_DO_LOTE = 500
NOMES_DOS_INDICES_UNICOS = ("idx_client_nif_hash_unico", "idx_client_email_hash_unico")


def _argumentos():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aplicar", action="store_true", help="Escreve (omissão: só mostra o plano).")
    p.add_argument(
        "--criar-indices", action="store_true",
        help="Depois de fundir, constrói já os índices únicos parciais (declarados em db_indexes).",
    )
    p.add_argument("--csv", default=None, help="Escreve os grupos neste ficheiro (valores mascarados).")
    p.add_argument("--limite-exemplos", type=int, default=20, help="Quantos grupos imprimir (default 20).")
    p.add_argument("--dados-pessoais", action="store_true", help="Mostra valores completos e nomes.")
    return p.parse_args()


async def _redes_das_empresas() -> dict[str, str | None]:
    from database import db
    from services.tenant_network import resolve_network_id

    mapa: dict[str, str | None] = {}
    async for empresa in db.companies.find({}, PROJECCAO_EMPRESA).max_time_ms(MAX_TIME_MS):
        rede = resolve_network_id(empresa)
        for chave in (empresa.get("id"), empresa.get("name")):
            if chave:
                mapa[str(chave).strip()] = rede
    return mapa


async def _processos_por_cliente(ids: list[str]) -> dict[str, int]:
    from database import db

    contagem: dict[str, int] = {}
    for i in range(0, len(ids), TAMANHO_DO_LOTE):
        lote = ids[i:i + TAMANHO_DO_LOTE]
        for campo in ("client_id", "second_client_id"):
            pipeline = [
                {"$match": {campo: {"$in": lote}, "is_deleted": {"$ne": True}}},
                {"$group": {"_id": f"${campo}", "n": {"$sum": 1}}},
            ]
            async for linha in db.processes.aggregate(pipeline, maxTimeMS=MAX_TIME_MS):
                contagem[linha["_id"]] = contagem.get(linha["_id"], 0) + linha["n"]
    return contagem


async def _carregar_candidatos() -> list[Candidato]:
    """Todos os clientes activos, com o documento (cifrado) e o nº de processos."""
    from database import db
    from services.encryption import decrypt_client_data

    redes = await _redes_das_empresas()
    pares: list[tuple] = []
    async for doc in db.clients.find({}, {"_id": 0}).max_time_ms(MAX_TIME_MS):
        if esta_eliminado(doc) or not doc.get("id"):
            continue
        registo = registo_de(doc, rede=rede_do_documento(doc, redes), decifrar=decrypt_client_data)
        pares.append((registo, doc))

    # Só quem tem NIF ou Email chave pode estar num grupo: o resto não interessa ao plano.
    relevantes = [(r, d) for r, d in pares if r.nif or r.email]
    processos = await _processos_por_cliente([r.id for r, _ in relevantes])
    return [Candidato(registo=r, doc=d, n_processos=processos.get(r.id, 0)) for r, d in relevantes]


def _imprimir(planos: list[PlanoDeFusao], candidatos: list[Candidato], args, *, aplicado: bool) -> None:
    resumo = resumir(planos)
    por_id = {c.registo.id: c for c in candidatos}
    completos = args.dados_pessoais

    print("=" * 70)
    print("D-42 — FUSÃO DE CLIENTES DUPLICADOS (NIF / Email, identidade global)")
    print("APLICADO" if aplicado else "SIMULAÇÃO (nada foi escrito)")
    print("=" * 70)
    print(f"Clientes activos com NIF ou Email: {len(candidatos)}")
    print(f"Grupos de duplicados: {resumo['grupos']}  "
          f"(a fundir {resumo['a_fundir']}, ambíguos {resumo['ambiguos']})")
    print(f"Clientes a absorver: {resumo['clientes_absorvidos']}  "
          f"— grupos que atravessam redes: {resumo['atravessam_redes']}")
    print("-" * 70)

    for plano in planos[:args.limite_exemplos]:
        etiqueta = "FUNDIR" if plano.veredicto == FUNDIR else "AMBÍGUO"
        print(f"  [{etiqueta}] {len(plano.membros)} clientes"
              + (f" — {plano.motivo}" if plano.motivo else ""))
        for cid in plano.membros:
            c = por_id[cid]
            papel = "fica" if cid == plano.sobrevivente and plano.veredicto == FUNDIR else (
                "absorvido" if cid in plano.absorvidos else "decidir")
            nome = f" «{c.registo.nome}»" if completos else ""
            valores = ", ".join(
                f"{ROTULOS[campo]} {mostrar(campo, chave, valores_completos=completos)}"
                for campo in CAMPOS_UNICOS if (chave := c.registo.chave(campo))
            )
            print(f"      {papel:<9} cliente:{cid}{nome}  rede={c.registo.rede}  "
                  f"{c.n_processos} processo(s)  {valores}")
    if len(planos) > args.limite_exemplos:
        print(f"  … e mais {len(planos) - args.limite_exemplos} grupo(s) (--csv para a lista completa)")
    print("-" * 70)

    if args.csv:
        with Path(args.csv).open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["veredicto", "motivo", "sobrevivente", "absorvidos", "membros", "redes_a_associar"])
            for p in planos:
                w.writerow([
                    p.veredicto, p.motivo, p.sobrevivente, ";".join(p.absorvidos),
                    ";".join(p.membros), ";".join(p.redes_a_associar),
                ])
        print(f"Lista completa ({len(planos)} grupos) → {args.csv}")


async def _criar_indices_unicos() -> list[str]:
    """Constrói os índices únicos a partir das definições de `db_indexes` (a mesma fonte do arranque)."""
    from database import db
    from services.db_indexes import INDEX_DEFINITIONS, _create_index_safe

    resultados = {"created": [], "errors": [], "skipped": []}
    for idx in INDEX_DEFINITIONS["clients"]:
        if idx["name"] in NOMES_DOS_INDICES_UNICOS:
            await _create_index_safe(db.clients, idx, "clients", resultados)
    for erro in resultados["errors"]:
        print(f"  ! {erro}")
    return resultados["created"] + resultados["skipped"]


async def principal() -> int:
    args = _argumentos()
    try:
        candidatos = await _carregar_candidatos()
    except PyMongoError as exc:
        print("D-42 — MEDIÇÃO NÃO REALIZADA")
        print(f"  A base de dados não respondeu: {exc}")
        print("  Nenhum cliente foi lido — um relatório de zero grupos leria-se como «não há duplicados».")
        return 2

    planos = planear(candidatos)
    aplicavel = [p for p in planos if p.veredicto == FUNDIR]
    ambiguos = [p for p in planos if p.veredicto == AMBIGUO]

    if args.aplicar and aplicavel:
        from database import db
        from services.client_merge_apply import aplicar_plano, referencias_fora_dos_processos

        agora = datetime.now(timezone.utc)
        try:
            for plano in aplicavel:
                await aplicar_plano(db, plano, agora=agora)
            absorvidos = [a for p in aplicavel for a in p.absorvidos]
            orfaos = await referencias_fora_dos_processos(db, absorvidos)
        except PyMongoError as exc:
            print(f"A fusão parou a meio ({exc}). É retomável: correr outra vez.")
            return 2
        _imprimir(planos, candidatos, args, aplicado=True)
        if orfaos:
            print("REFERÊNCIAS QUE FICARAM POR REAPONTAR (rever à mão):")
            for colecao, campos in orfaos.items():
                print(f"  {colecao}: {campos}")
            return 1
    else:
        _imprimir(planos, candidatos, args, aplicado=False)

    if ambiguos:
        print(f"{len(ambiguos)} grupo(s) AMBÍGUO(S): dois NIFs diferentes ligados por um email.")
        print("Decidir à mão (por exemplo corrigir o email de um deles). Os índices únicos só se")
        print("constroem depois.")
        return 1

    if args.criar_indices:
        if planos and not args.aplicar:
            print("--criar-indices recusa-se numa simulação com grupos por resolver.")
            return 1
        criados = await _criar_indices_unicos()
        print(f"Índices únicos: {', '.join(criados) or 'nenhum criado'}")
    elif args.aplicar:
        print("Os índices únicos nascem no arranque seguinte (ou correr com --criar-indices).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
