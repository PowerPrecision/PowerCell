#!/usr/bin/env python3
"""D-15 — cifra as datas de nascimento que ainda estão em texto simples.

Para cada pessoa de `processes` e `clients` (titular 1, 2.º titular,
`co_buyers`, `co_applicants` e a raiz dos processos antigos) cifra o valor e
grava o ANO (`birth_year`, inteiro, em claro) ao lado — é o ano que mantém o
filtro Sub35 a funcionar sem a data à vista. A lógica de decisão vive em
`services/birthdate_migration.py` (pura, com testes).

SEGURANÇA DA OPERAÇÃO
  * Omissão: SÓ LÊ e conta. `--aplicar` escreve.
  * **A chave tem de ser a de produção.** Antes de escrever, o script tenta
    decifrar valores JÁ cifrados na base (NIFs): se nenhum abre, a chave deste
    ambiente não é a que cifrou aquilo e escrever aqui produziria dados que a
    aplicação não consegue ler. Aborta com código 4.
  * Recusa-se se a cifra não está disponível (escreveria texto simples e
    contá-lo-ia como migrado): código 3.
  * Cada escrita leva no filtro o valor que se leu: uma edição que chegue a
    meio da migração não é pisada (conta como `concorrencia` e fica para a
    passagem seguinte).
  * Idempotente: a segunda passagem dá «0 a fazer». Não toca em `updated_at`
    (não é uma edição do utilizador).
  * Só contagens no output — nunca valores, nunca ids de documentos.

CÓDIGOS DE SAÍDA: 0 feito (ou descrito); 2 a base de dados não respondeu;
3 a cifra não está disponível; 4 a chave não abre dados já cifrados.

Corre contra produção DE PROPÓSITO (NÃO chama `require_non_production_db`).

USO (a partir de `backend/`):
    python -m scripts.migrar_datas_de_nascimento             # descreve
    python -m scripts.migrar_datas_de_nascimento --aplicar   # cifra
    python scripts/medir_datas_de_nascimento.py              # confirma: «em claro: 0»
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import UpdateOne  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from services.birthdate_migration import (  # noqa: E402
    PROJECCAO,
    filtro_de_escrita,
    planear,
)
from services.encryption import encryption_service, is_encrypted  # noqa: E402

COLECCOES = ("processes", "clients")
MAX_TIME_MS = 300_000
LOTE = 200
#: Quantos valores já cifrados se experimentam para provar que a chave é a certa.
AMOSTRA_DA_CHAVE = 20

#: Onde procurar valores já cifrados (o NIF é o que existe em todo o lado).
_CAMINHOS_DA_PROVA = {
    "processes": ("personal_data.nif", "client_nif"),
    "clients": ("dados_pessoais.nif",),
}


def _valor(doc: dict, caminho: str):
    actual = doc
    for parte in caminho.split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(parte)
    return actual


async def a_chave_abre_o_que_ja_esta_cifrado(db) -> tuple[int, int]:
    """(experimentados, abertos): decifra uma amostra de NIFs já cifrados."""
    experimentados = abertos = 0
    for colecao, caminhos in _CAMINHOS_DA_PROVA.items():
        for caminho in caminhos:
            cursor = getattr(db, colecao).find(
                {caminho: {"$regex": "^ENC:"}}, {"_id": 0, caminho: 1}
            ).limit(AMOSTRA_DA_CHAVE)
            async for doc in cursor:
                valor = _valor(doc, caminho)
                if not (isinstance(valor, str) and is_encrypted(valor)):
                    continue
                experimentados += 1
                if not is_encrypted(encryption_service.decrypt(valor)):
                    abertos += 1
    return experimentados, abertos


async def migrar(*, aplicar: bool) -> dict:
    from database import db

    relatorio: dict = {"documentos": Counter(), "com_pendencias": Counter(),
                       "escritos": Counter(), "concorrencia": Counter(),
                       "campos": {c: Counter() for c in COLECCOES}}
    for colecao in COLECCOES:
        operacoes: list = []
        cursor = (
            getattr(db, colecao)
            .find({}, {"_id": 1, **PROJECCAO})
            .batch_size(LOTE)
            .max_time_ms(MAX_TIME_MS)
        )

        async def descarregar():
            if not operacoes:
                return
            resultado = await getattr(db, colecao).bulk_write(operacoes, ordered=False)
            escritos = resultado.modified_count
            relatorio["escritos"][colecao] += escritos
            relatorio["concorrencia"][colecao] += len(operacoes) - escritos
            operacoes.clear()

        async for doc in cursor:
            relatorio["documentos"][colecao] += 1
            plano = planear(doc)
            relatorio["campos"][colecao].update(plano.contagem)
            if plano.vazio:
                continue
            relatorio["com_pendencias"][colecao] += 1
            if aplicar:
                operacoes.append(UpdateOne(
                    filtro_de_escrita(doc["_id"], plano), {"$set": plano.definir},
                ))
                if len(operacoes) >= LOTE:
                    await descarregar()
        if aplicar:
            await descarregar()
    return relatorio


def imprimir(relatorio: dict, *, aplicar: bool) -> None:
    print("=" * 72)
    print("D-15 — MIGRAÇÃO DAS DATAS DE NASCIMENTO "
          + ("(APLICADA)" if aplicar else "(só descrição: nada foi escrito)"))
    print("=" * 72)
    for colecao in COLECCOES:
        lidos = relatorio["documentos"][colecao]
        campos = relatorio["campos"][colecao]
        print(f"\n{colecao}: {lidos} documento(s) lido(s), "
              f"{relatorio['com_pendencias'][colecao]} com algo a fazer")
        print(f"  datas a cifrar ........... {campos['a_cifrar']}")
        print(f"  anos a carimbar .......... {campos['ano_a_carimbar']}")
        print(f"  anos a limpar ............ {campos['ano_a_limpar']}")
        print(f"  já migradas .............. {campos['ja_migrados']}")
        print(f"  cifradas e ILEGÍVEIS ..... {campos['ilegiveis']}  (não se tocam)")
        if aplicar:
            print(f"  documentos escritos ...... {relatorio['escritos'][colecao]}")
            print(f"  perdidos para edições .... {relatorio['concorrencia'][colecao]}  "
                  "(correr outra vez)")
    if not any(relatorio["documentos"].values()):
        print("\n→ NENHUM documento lido: confirmar DB_NAME (zero não é «nada a migrar»).")
    ilegiveis = sum(relatorio["campos"][c]["ilegiveis"] for c in COLECCOES)
    if ilegiveis:
        print(f"\n⚠ {ilegiveis} data(s) cifrada(s) que esta chave não abre — ver ENCRYPTION_KEY.")
    if not aplicar:
        print("\nPara escrever: --aplicar")
    print("=" * 72)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--aplicar", action="store_true", help="escreve (omissão: só descreve)")
    args = parser.parse_args(argv)

    if args.aplicar and not encryption_service.is_available():
        print("D-15 — RECUSADO: a cifra não está disponível neste ambiente.")
        print("  Escrever agora gravaria as datas em texto simples e contá-las-ia como migradas.")
        return 3

    async def correr() -> int:
        from database import db

        if args.aplicar:
            experimentados, abertos = await a_chave_abre_o_que_ja_esta_cifrado(db)
            if experimentados and not abertos:
                print(f"D-15 — RECUSADO: a chave deste ambiente não abre nenhum dos "
                      f"{experimentados} NIF(s) já cifrados que se experimentaram.")
                print("  Não é a ENCRYPTION_KEY de produção; escrever tornaria as datas ilegíveis.")
                return 4
            if not experimentados:
                print("  (aviso: não há valores cifrados na base para provar a chave.)")
        relatorio = await migrar(aplicar=args.aplicar)
        imprimir(relatorio, aplicar=args.aplicar)
        return 0

    try:
        return asyncio.run(correr())
    except PyMongoError as exc:
        print("D-15 — MIGRAÇÃO NÃO REALIZADA")
        print(f"  A base de dados não respondeu: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
