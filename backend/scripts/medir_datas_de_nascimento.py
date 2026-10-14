#!/usr/bin/env python3
"""D-15 — quanta data de nascimento está em texto simples? (só leitura)

Serve a decisão do dono do produto com o DPO (encriptar e perder o filtro Sub35,
ou manter): em que colecções e campos a data existe, quantas estão em claro e
quantos valores não são nem data ISO nem valor encriptado. A classificação vive
em `services/birthdate_exposure_audit.py` (puro, com testes).

ESTRITAMENTE SÓ DE LEITURA e sem valores no output — só contagens. Corre contra
produção DE PROPÓSITO (NÃO chama `require_non_production_db`).

CÓDIGOS DE SAÍDA: 0 a leitura aconteceu; 2 a base de dados não respondeu (zero
documentos lidos leria-se como «não há datas em claro»).

USO: MONGO_URL=... DB_NAME=... python scripts/medir_datas_de_nascimento.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo.errors import PyMongoError  # noqa: E402
from services.birthdate_exposure_audit import (  # noqa: E402
    ESTADOS,
    SECCOES_POR_COLECCAO,
    Relatorio,
    projeccao,
    resumir,
    auditar,
)

MAX_TIME_MS = 120_000


async def medir() -> Relatorio:
    from database import db

    relatorio = Relatorio()
    for colecao in SECCOES_POR_COLECCAO:
        cursor = getattr(db, colecao).find({}, projeccao(colecao)).max_time_ms(MAX_TIME_MS)
        auditar(colecao, [d async for d in cursor], relatorio)
    return relatorio


def main() -> int:
    try:
        relatorio = asyncio.run(medir())
    except PyMongoError as exc:
        print("D-15 — MEDIÇÃO NÃO REALIZADA")
        print(f"  A base de dados não respondeu: {exc}")
        return 2
    resumo = resumir(relatorio)
    print("=" * 72)
    print("D-15 — DATAS DE NASCIMENTO EM TEXTO SIMPLES (só leitura, só contagens)")
    print("=" * 72)
    for colecao, n in resumo["documentos"].items():
        print(f"{colecao}: {n} documento(s) lido(s), {resumo['com_data_em_claro'].get(colecao, 0)} com data em claro")
    if not any(resumo["documentos"].values()):
        print("→ NENHUM documento lido: confirmar DB_NAME (zero não é «sem datas em claro»).")
    for colecao, caminhos in resumo["por_colecao"].items():
        print(f"\n{colecao}")
        print(f"  {'caminho':<36}" + "".join(f"{e:>10}" for e in ESTADOS))
        for caminho, contagem in caminhos.items():
            print(f"  {caminho:<36}" + "".join(f"{contagem[e]:>10}" for e in ESTADOS))
    print(f"\nTOTAL em claro: {resumo['total_em_claro']}  |  valores que não são data nem cifra: {resumo['total_outro']}")
    if resumo["total_outro"]:
        print("  ⚠ Uma migração para encriptar teria de tratar estes valores à mão.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
