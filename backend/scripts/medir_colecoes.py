#!/usr/bin/env python3
"""D-13, passo 1 — MEDIR antes de mover: peso e idade de cada colecção.

Sem esta tabela nenhum passo seguinte do épico de custos do Atlas começa
(TECHNICAL_DEBT D-13): arquiva-se a colecção errada. A classificação vive em
`services/db_storage_audit.py` (puro, com testes); aqui só se lê.

ESTRITAMENTE SÓ DE LEITURA — `collStats` e contagens, nenhuma escrita (há um
teste por AST). Corre contra produção DE PROPÓSITO (como os outros
`diagnose_*`/`medir_*`): a pergunta está nos dados reais, logo NÃO chama
`require_non_production_db`.

O QUE SAI
=========
    * por colecção: documentos, dados, índices, bytes por documento e a fatia
      do total;
    * a idade: quantos documentos são mais velhos que 30/90/180/365 dias, pelo
      campo de data que a colecção realmente usa (datetime OU texto ISO — os
      dois tipos contam) e quantos não têm data utilizável;
    * pontos de atenção: volume E idade juntos.
    Não diz o que se pode apagar: a retenção é decisão jurídica.

CÓDIGOS DE SAÍDA
================
    0  a medição aconteceu
    2  a base de dados não respondeu: uma tabela vazia leria-se como «não pesa nada»

USO
===
    MONGO_URL=... DB_NAME=... python scripts/medir_colecoes.py
    ... python scripts/medir_colecoes.py --csv /tmp/d13.csv --so history,emails
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo.errors import OperationFailure, PyMongoError  # noqa: E402
from services.db_storage_audit import (  # noqa: E402
    COLECCOES_MEDIDAS,
    ESCALOES_EM_DIAS,
    LEITURA_DO_PESO,
    LinhaDaColeccao,
    condicao_mais_antigo_que,
    condicao_sem_data,
    escolher_campo_de_data,
    fatia_do_total,
    formatar_bytes,
    linha_de_collstats,
    ordenar_por_peso,
    pontos_de_atencao,
)

#: Tecto de cada leitura: uma medição não pode pendurar a base de produção.
MAX_TIME_MS = 120_000
NAMESPACE_NOT_FOUND = 26


def _argumentos():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--csv", default=None, help="Escreve a tabela neste ficheiro.")
    p.add_argument("--so", default=None, help="Só estas colecções (separadas por vírgulas).")
    p.add_argument("--markdown", action="store_true",
                   help="Imprime também a tabela em Markdown, pronta a colar no worklog.md.")
    return p.parse_args()


async def _collstats(db, nome: str, existentes: set[str]) -> dict | None:
    """`None` quando a colecção não existe — não é o mesmo que zero bytes.

    O `collStats` de uma colecção inexistente NÃO falha no MongoDB 7: responde ok com tudo a zero, o que
    se leria como «existe e está vazia». Quem decide é a lista de colecções.
    """
    if nome not in existentes:
        return None
    try:
        return await db.command("collStats", nome)
    except OperationFailure as exc:
        if exc.code == NAMESPACE_NOT_FOUND or "not found" in str(exc).lower():
            return None
        raise


async def _medir_idade(db, linha: LinhaDaColeccao, candidatos, agora: datetime) -> None:
    colecao = getattr(db, linha.nome)
    com_campo = {}
    for campo in candidatos:
        com_campo[campo] = await colecao.count_documents(
            {campo: {"$exists": True, "$ne": None}}, maxTimeMS=MAX_TIME_MS,
        )
    campo = escolher_campo_de_data(com_campo, candidatos)
    if campo is None:
        linha.aviso = "nenhum campo de data com valores"
        linha.sem_data = linha.documentos
        return
    linha.campo_de_data = campo
    linha.sem_data = await colecao.count_documents(condicao_sem_data(campo), maxTimeMS=MAX_TIME_MS)
    for dias in ESCALOES_EM_DIAS:
        linha.mais_antigos_que[dias] = await colecao.count_documents(
            condicao_mais_antigo_que(campo, agora, dias), maxTimeMS=MAX_TIME_MS,
        )


async def medir(nomes: list[str]) -> list[LinhaDaColeccao]:
    from database import db

    agora = datetime.now(timezone.utc)
    existentes = set(await db.list_collection_names())
    linhas = []
    for nome in nomes:
        linha = linha_de_collstats(nome, await _collstats(db, nome, existentes))
        if linha.existe and linha.documentos:
            await _medir_idade(db, linha, COLECCOES_MEDIDAS[nome], agora)
        linhas.append(linha)
    return linhas


def _imprimir(linhas: list[LinhaDaColeccao]) -> None:
    print("=" * 96)
    print("D-13 · PASSO 1 — PESO E IDADE DAS COLECÇÕES (só leitura)")
    print("=" * 96)
    cab = f"{'colecção':<20}{'docs':>9}{'dados':>11}{'índices':>11}{'B/doc':>9}{'fatia':>7}"
    cab += "".join(f"{'>' + str(d) + 'd':>8}" for d in ESCALOES_EM_DIAS) + "  campo de data"
    print(cab)
    print("-" * 96)
    for l in ordenar_por_peso(linhas):
        if not l.existe:
            print(f"{l.nome:<20}  (não existe)")
            continue
        fatias = []
        for d in ESCALOES_EM_DIAS:
            f = l.fatia_mais_antiga_que(d)
            fatias.append(f"{f:>8.0%}" if f is not None else f"{'—':>8}")
        print(
            f"{l.nome:<20}{l.documentos:>9}{formatar_bytes(l.bytes_dados):>11}"
            f"{formatar_bytes(l.bytes_indices):>11}{l.media_por_documento:>9}"
            f"{fatia_do_total(l, linhas):>7.0%}" + "".join(fatias)
            + f"  {l.campo_de_data or (l.aviso or '—')}"
            + (f"  [{l.sem_data} sem data]" if l.sem_data and l.campo_de_data else "")
        )
    print("-" * 96)
    pontos = pontos_de_atencao(linhas)
    if not any(l.existe and l.documentos for l in linhas):
        print("→ NENHUM documento lido em nenhuma colecção: confirmar DB_NAME antes de tirar conclusões "
              "(zero não é «não pesa nada»).")
    elif pontos:
        print("PONTOS DE ATENÇÃO (volume e idade juntos):")
        for nome, motivo in pontos:
            print(f"  • {nome}: {motivo}")
    else:
        print("Nenhuma colecção junta volume relevante e maioria antiga.")
    print(f"\n{LEITURA_DO_PESO}")
    print("=" * 96)


def _markdown(linhas: list[LinhaDaColeccao], base: str, agora: datetime) -> str:
    """A «fotografia» para o `worklog.md`: data, nome da base e uma linha por colecção.

    Leva o NOME da base (não o URL: traz credenciais) — uma fotografia sem a
    base de onde saiu não distingue produção de desenvolvimento.
    """
    cab = "".join(f" >{d}d |" for d in ESCALOES_EM_DIAS)
    linhas_md = [
        f"**Fotografia D-13 — {agora:%Y-%m-%d %H:%M} UTC — base `{base}`**",
        "",
        f"| colecção | docs | dados | índices | B/doc | fatia |{cab} campo de data |",
        "|---|---:|---:|---:|---:|---:|" + "---:|" * len(ESCALOES_EM_DIAS) + "---|",
    ]
    for l in ordenar_por_peso(linhas):
        if not l.existe:
            linhas_md.append(f"| {l.nome} | _(não existe)_ |" + " |" * (4 + len(ESCALOES_EM_DIAS)))
            continue
        fatias = []
        for d in ESCALOES_EM_DIAS:
            f = l.fatia_mais_antiga_que(d)
            fatias.append(f"{f:.0%}" if f is not None else "—")
        linhas_md.append(
            f"| {l.nome} | {l.documentos} | {formatar_bytes(l.bytes_dados)} | "
            f"{formatar_bytes(l.bytes_indices)} | {l.media_por_documento} | {fatia_do_total(l, linhas):.0%} | "
            + " | ".join(fatias) + f" | {l.campo_de_data or (l.aviso or '—')} |"
        )
    return "\n".join(linhas_md)


def main() -> int:
    args = _argumentos()
    nomes = list(COLECCOES_MEDIDAS)
    if args.so:
        pedidos = [n.strip() for n in args.so.split(",") if n.strip()]
        desconhecidas = [n for n in pedidos if n not in COLECCOES_MEDIDAS]
        if desconhecidas:
            print(f"Colecções sem campos de data conhecidos: {', '.join(desconhecidas)}")
            return 2
        nomes = pedidos
    try:
        linhas = asyncio.run(medir(nomes))
    except PyMongoError as exc:
        print("D-13 — MEDIÇÃO NÃO REALIZADA")
        print(f"  A base de dados não respondeu: {exc}")
        print("  Uma tabela vazia leria-se como «não pesa nada». Confirmar MONGO_URL/DB_NAME e repetir.")
        return 2
    _imprimir(linhas)
    if args.markdown:
        import os

        print()
        print(_markdown(linhas, os.environ.get("DB_NAME", "?"), datetime.now(timezone.utc)))
    if args.csv:
        with Path(args.csv).open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["colecao", "documentos", "bytes_dados", "bytes_indices", "campo_de_data",
                        "sem_data", *[f"mais_de_{d}d" for d in ESCALOES_EM_DIAS]])
            for l in ordenar_por_peso(linhas):
                w.writerow([l.nome, l.documentos, l.bytes_dados, l.bytes_indices,
                            l.campo_de_data or "", l.sem_data,
                            *[l.mais_antigos_que.get(d, "") for d in ESCALOES_EM_DIAS]])
        print(f"Tabela → {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
