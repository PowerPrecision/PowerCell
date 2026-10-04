#!/usr/bin/env python3
"""Sana o `s3_folder` gravado como par `(sucesso, caminho)` (Lote 8, ponto 1).

    # ler e contar (omissão — NÃO escreve)
    python scripts/fix_s3_folder_anomalies.py

    # escrever só o que se PROVA reparável
    python scripts/fix_s3_folder_anomalies.py --aplicar

    # lista completa para o painel
    python scripts/fix_s3_folder_anomalies.py --csv /tmp/anomalias.csv

CORRE CONTRA PRODUÇÃO DE PROPÓSITO
==================================
Como o `diagnose_assignment_drift.py` e o `diagnose_s3_name_fallback.py`,
**não** chama `require_non_production_db`: produção é o único sítio onde
estes registos existem. Em troca:

  * a omissão é LER e contar — a escrita exige `--aplicar`;
  * só o veredicto `par_de_sucesso` é escrito, e `--aplicar` não muda
    isso (a bandeira autoriza a escrita, não substitui a prova);
  * cada escrita é um `$set` ESTRITO na chave `s3_folder`, mais os
    metadados de auditoria. Nunca um documento inteiro.

PORQUE É QUE A ORDEM IMPORTA
============================
Estes registos têm hoje um `s3_folder` que o `pasta_gravada` recusa, logo
a aplicação trata-os como **sem mapeamento** e serve-lhes os documentos
pelo recurso por NOME. Enquanto o recurso existir, eles vêem os
documentos; no instante em que for apagado, deixam de ver.

Por isso esta migração corre **ANTES** de se apagar o recurso por nome
(D-19), e não depois: é ela que lhes dá um mapeamento explícito que
sobrevive ao corte.

CÓDIGOS DE SAÍDA
================
    0  nada a fazer, ou `--aplicar` correu sem falhas
    1  há casos que EXIGEM DECISÃO humana (e nenhuma escrita os resolve)
    2  a leitura não aconteceu (sem base de dados)
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.s3_document_root import pasta_para_gravar  # noqa: E402
from services.s3_folder_anomaly_repair import (  # noqa: E402
    VEREDICTO_FORA_DA_RAIZ,
    VEREDICTO_IRRECONHECIVEL,
    VEREDICTO_JA_E_TEXTO,
    VEREDICTO_PAR_DE_FALHA,
    VEREDICTO_PAR_DE_SUCESSO,
    classificar,
    resumir,
)

#: Nome da colecção → campo com o nome legível, para o relatório.
COLECCOES = (
    ("processes", ("client_name", "process_number")),
    ("clients", ("nome", "name", "client_name")),
)

ROTULOS = {
    VEREDICTO_PAR_DE_SUCESSO: "reparável — par (True, caminho) na raiz",
    VEREDICTO_PAR_DE_FALHA: "EXIGE DECISÃO — o par declara falha",
    VEREDICTO_FORA_DA_RAIZ: "EXIGE DECISÃO — caminho fora da raiz documental",
    VEREDICTO_IRRECONHECIVEL: "EXIGE DECISÃO — forma não reconhecida",
    VEREDICTO_JA_E_TEXTO: "já é texto (não é anomalia)",
}

ORDEM = (
    VEREDICTO_FORA_DA_RAIZ,
    VEREDICTO_IRRECONHECIVEL,
    VEREDICTO_PAR_DE_FALHA,
    VEREDICTO_PAR_DE_SUCESSO,
    VEREDICTO_JA_E_TEXTO,
)


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--aplicar", action="store_true",
        help="escreve a correcção dos casos PROVADOS reparáveis "
             "(sem esta bandeira apenas lê e conta)",
    )
    p.add_argument("--csv", help="escreve a lista completa neste ficheiro")
    return p.parse_args()


def _nome_legivel(doc: dict, campos: tuple) -> str:
    for campo in campos:
        valor = doc.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


async def _carregar(db) -> list[dict]:
    """As fichas cujo `s3_folder` NÃO é string nem está ausente.

    A ARMADILHA DA SEMÂNTICA DE ARRAYS
    ==================================
    A primeira versão deste filtro era

        {"$nor": [{"s3_folder": {"$type": "string"}}]}

    e encontrou **1 de 7** registos semeados. Numa consulta a um campo que
    contém um ARRAY, o Mongo compara o array E cada um dos seus elementos:
    `$type: "string"` é **verdadeiro** para `[True, "Documentação…"]`,
    porque há ali um elemento string. O `$nor` excluía precisamente as
    fichas que o script existe para encontrar — e, pior, um relatório a
    dizer «1 anomalia» leria-se como «as outras já estão sãs».

    É a família da lição do `$nor` no duplo de Mongo: a semântica de
    arrays não é a que a leitura ingénua da condição sugere, e só um
    Mongo REAL a revela (o duplo in-memory dos testes não a implementa).

    Daí a pergunta ser POSITIVA e em dois ramos:
      * `$type: "array"` — o Mongo trata "array" como «o campo É um
        array», e não «tem um elemento array»: é o único operador que
        responde ao que queremos;
      * `$not`/`$type: "string"` — para os tipos que não são arrays (um
        `dict`, um número), onde a comparação elemento a elemento não se
        aplica e a condição vale como se lê.
    """
    linhas: list[dict] = []
    for nome_coleccao, campos_de_nome in COLECCOES:
        coleccao = getattr(db, nome_coleccao)
        cursor = coleccao.find(
            {
                "s3_folder": {"$exists": True, "$ne": None},
                "$or": [
                    # O campo É um array (o caso dos 10 registos).
                    {"s3_folder": {"$type": "array"}},
                    # Qualquer outro tipo que não seja texto.
                    {"s3_folder": {"$not": {"$type": "string"}}},
                ],
            },
            {"_id": 0, "id": 1, "s3_folder": 1,
             **{campo: 1 for campo in campos_de_nome}},
        )
        for doc in await cursor.to_list(100000):
            if not doc.get("id"):
                continue
            linhas.append({
                "coleccao": nome_coleccao,
                "id": doc["id"],
                "nome": _nome_legivel(doc, campos_de_nome),
                "valor": doc.get("s3_folder"),
            })
    return linhas


async def _escrever(db, linha: dict, caminho: str) -> bool:
    """`$set` estrito no `s3_folder` + metadados. Devolve True se gravou."""
    coleccao = getattr(db, linha["coleccao"])
    agora = datetime.now(timezone.utc).isoformat()
    # O veredicto já provou que é uma string dentro da raiz; o primitivo é
    # a mesma parede que os escritores da aplicação atravessam, e aqui vale
    # mais do que lá: isto escreve DIRECTAMENTE em produção.
    pasta = pasta_para_gravar(caminho, contexto=f"reparação de {linha['id']}")
    resultado = await coleccao.update_one(
        {"id": linha["id"]},
        {"$set": {
            "s3_folder": pasta,
            "s3_mapping_updated_at": agora,
            "s3_mapping_updated_by": "script:fix_s3_folder_anomalies",
        }},
    )
    return bool(resultado.modified_count)


def _imprimir(registos: list[dict], resumo: dict, aplicado: bool) -> None:
    print("=" * 72)
    print("ANOMALIAS DE TIPO NO `s3_folder` — PAR (sucesso, caminho)")
    print("=" * 72)
    print(f"Fichas com `s3_folder` que não é texto: {resumo['total']}")
    print("-" * 72)
    for veredicto in ORDEM:
        quantos = resumo["por_veredicto"].get(veredicto, 0)
        if quantos:
            print(f"  {quantos:>5}  {ROTULOS[veredicto]}")
    print("-" * 72)
    print(f"  REPARÁVEIS AUTOMATICAMENTE: {resumo['reparaveis']}")
    print(f"  EXIGEM DECISÃO HUMANA:      {resumo['exigem_decisao']}")
    if not aplicado and resumo["reparaveis"]:
        print("\n  → Nada foi gravado. Correr outra vez com --aplicar.")
    print("-" * 72)

    for registo in registos:
        reparacao = registo["reparacao"]
        if reparacao.veredicto == VEREDICTO_JA_E_TEXTO:
            continue
        marca = {
            "gravado": "✔", "inalterado": "✖", "lido": "·",
        }.get(registo.get("estado", "lido"), "·")
        etiqueta = f" «{registo['nome']}»" if registo["nome"] else ""
        print(f"  {marca} {reparacao.veredicto:<16} "
              f"{registo['coleccao']}:{registo['id']}{etiqueta}")
        print(f"      gravado: {reparacao.valor_cru}")
        print(f"      motivo:  {reparacao.motivo}")
        if reparacao.reparavel:
            print(f"      → {reparacao.caminho}")
    print("=" * 72)


async def principal() -> int:
    args = _argumentos()

    try:
        from database import db
        registos_crus = await _carregar(db)
    except Exception as exc:  # noqa: BLE001
        print("=" * 72)
        print("LEITURA NÃO REALIZADA")
        print("=" * 72)
        print(f"Não foi possível ler a base de dados: {exc}")
        print("Sem leitura não há contagem — e um 0 aqui leria-se como "
              "«não há anomalias».")
        return 2

    registos = []
    for linha in registos_crus:
        registos.append({**linha, "reparacao": classificar(linha["valor"])})

    resumo = resumir(r["reparacao"] for r in registos)

    if args.aplicar:
        for registo in registos:
            reparacao = registo["reparacao"]
            if not reparacao.reparavel:
                continue
            try:
                gravou = await _escrever(db, registo, reparacao.caminho)
                registo["estado"] = "gravado" if gravou else "inalterado"
            except Exception as exc:  # noqa: BLE001
                registo["estado"] = "inalterado"
                print(f"[ERRO] {registo['coleccao']}:{registo['id']}: {exc}")

    _imprimir(registos, resumo, args.aplicar)

    if args.csv:
        destino = Path(args.csv)
        with destino.open("w", newline="", encoding="utf-8") as fh:
            escritor = csv.DictWriter(fh, fieldnames=[
                "coleccao", "id", "nome", "veredicto", "valor_cru",
                "caminho_proposto", "motivo", "estado",
            ])
            escritor.writeheader()
            for registo in registos:
                reparacao = registo["reparacao"]
                escritor.writerow({
                    "coleccao": registo["coleccao"],
                    "id": registo["id"],
                    "nome": registo["nome"],
                    "veredicto": reparacao.veredicto,
                    "valor_cru": reparacao.valor_cru,
                    "caminho_proposto": reparacao.caminho or "",
                    "motivo": reparacao.motivo,
                    "estado": registo.get("estado", "lido"),
                })
        print(f"Lista completa ({len(registos)} linhas) → {destino}")

    # Um 1 quando sobram casos que nenhuma escrita resolve: é o sinal de
    # que falta uma decisão humana, e não um erro do script.
    return 1 if resumo["exigem_decisao"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
