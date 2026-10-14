#!/usr/bin/env python3
"""Migra os `co_buyers` gravados pelo mapeador do CPCV antigo: retira o titular 1 repetido (D-18).

    # ler e contar (omissão — NÃO escreve)
    python scripts/migrar_co_buyers_adicionais.py

    # escrever só o que se PROVA migrável
    python scripts/migrar_co_buyers_adicionais.py --aplicar

CORRE CONTRA PRODUÇÃO DE PROPÓSITO (como o `diagnose_assignment_drift.py`): produção é o único sítio
onde estes registos existem. Em troca:

  * a omissão é LER e contar — a escrita exige `--aplicar`;
  * só se retira o elemento 0 quando `co_buyers_migration.classificar` PROVA que é o titular 1
    (a bandeira autoriza a escrita, não substitui a prova); `ambiguo` nunca é tocado;
  * cada escrita é condicional ao array EXACTAMENTE como foi lido (`co_buyers: <o que li>`): se alguém
    editou o processo entretanto, o filtro não casa e nada se grava;
  * idempotente: uma segunda passagem não encontra nada a migrar.

ORDEM: o mapeador novo (que só grava adicionais) tem de estar em produção ANTES — senão cada CPCV
analisado recria o problema. Só depois de uma passagem limpa se pode simplificar a desduplicação de
`sub35.compradores_que_bloqueiam`.

CÓDIGOS DE SAÍDA
    0  nada a fazer, ou `--aplicar` correu sem falhas
    1  há casos `ambiguo` que EXIGEM DECISÃO humana
    2  a leitura não aconteceu (sem base de dados)
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.co_buyers_migration import (  # noqa: E402
    ROTULOS,
    VEREDICTO_AMBIGUO,
    VEREDICTO_RETIRAR_O_TITULAR_1,
    classificar,
    resumir,
    sem_o_primeiro,
)

PROJECCAO = {
    "_id": 0, "id": 1, "client_name": 1, "process_number": 1, "personal_data": 1,
    "dados_pessoais": 1, "co_buyers": 1,
}


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aplicar", action="store_true",
                   help="escreve a migração dos casos PROVADOS (sem esta bandeira apenas lê e conta)")
    return p.parse_args()


async def _carregar(db) -> list[dict]:
    """Os processos com pelo menos um `co_buyers`, na forma ENCRIPTADA em que estão gravados."""
    return await db.processes.find(
        {"co_buyers.0": {"$exists": True}, "is_deleted": {"$ne": True}}, PROJECCAO,
    ).to_list(None)


def _decifrado(doc: dict) -> dict:
    """O documento desencriptado (o NIF/CC dos `co_buyers` estão cifrados); o original não se altera."""
    from services.encryption import decrypt_process_data

    return decrypt_process_data(copy.deepcopy(doc))


async def migrar(db, *, aplicar: bool) -> dict:
    """Classifica todos os processos com `co_buyers` e, com ``aplicar``, migra os provados."""
    registos = []
    for doc in await _carregar(db):
        registos.append({
            "id": doc.get("id"),
            "nome": doc.get("client_name") or "",
            # Cópia: o array lido é a CONDIÇÃO da escrita, e tem de ficar como foi lido mesmo que
            # o objecto de origem seja mutado entretanto.
            "bruto": copy.deepcopy(doc.get("co_buyers")),
            "veredicto": classificar(_decifrado(doc)),
            "estado": "lido",
        })

    if aplicar:
        for r in registos:
            if r["veredicto"] != VEREDICTO_RETIRAR_O_TITULAR_1:
                continue
            resto = sem_o_primeiro(r["bruto"])
            operacao = {"$set": {"co_buyers": resto}} if resto else {"$unset": {"co_buyers": ""}}
            # Condicional ao array tal como foi lido: edição concorrente → não casa → não grava.
            resultado = await db.processes.update_one({"id": r["id"], "co_buyers": r["bruto"]}, operacao)
            r["estado"] = "gravado" if getattr(resultado, "modified_count", 0) else "inalterado"
        gravados = [r["id"] for r in registos if r["estado"] == "gravado"]
        if gravados:
            await db.audit_logs.insert_one({
                "action": "co_buyers_migrados",
                "source": "script:migrar_co_buyers_adicionais",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {"processos": gravados, "total": len(gravados)},
            })

    return {"registos": registos, "resumo": resumir([r["veredicto"] for r in registos])}


def _imprimir(relatorio: dict, aplicado: bool) -> None:
    resumo = relatorio["resumo"]
    print("=" * 72)
    print("co_buyers — UM SIGNIFICADO (os compradores ADICIONAIS)")
    print("=" * 72)
    print(f"Processos com co_buyers: {len(relatorio['registos'])}")
    print("-" * 72)
    for veredicto, rotulo in ROTULOS.items():
        if resumo.get(veredicto):
            print(f"  {resumo[veredicto]:>5}  {rotulo}")
    print("-" * 72)
    if not aplicado and resumo.get(VEREDICTO_RETIRAR_O_TITULAR_1):
        print("  → Nada foi gravado. Correr outra vez com --aplicar.")
    for r in relatorio["registos"]:
        if r["veredicto"] in (VEREDICTO_AMBIGUO, VEREDICTO_RETIRAR_O_TITULAR_1):
            marca = {"gravado": "✔", "inalterado": "✖"}.get(r["estado"], "·")
            print(f"  {marca} {r['veredicto']:<22} processo {r['id']}  {r['nome']}")
    print("=" * 72)


async def principal() -> int:
    args = _argumentos()
    try:
        from database import db
        relatorio = await migrar(db, aplicar=args.aplicar)
    except Exception as exc:  # noqa: BLE001
        print("LEITURA NÃO REALIZADA")
        print(f"Não foi possível ler a base de dados: {exc}")
        print("Sem leitura não há contagem — e um 0 aqui leria-se como «não há nada a migrar».")
        return 2
    _imprimir(relatorio, args.aplicar)
    return 1 if relatorio["resumo"].get(VEREDICTO_AMBIGUO) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
