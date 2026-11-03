#!/usr/bin/env python3
"""A que Index está este processo, e quem o podia receber? (só leitura)

Para correr no Shell do serviço web do Render:

    cd backend && python scripts/diagnosticar_index_do_processo.py "Larisa Dordea"

Aceita o nome do cliente (parte dele chega, sem maiúsculas) ou o id do processo.

O QUE MOSTRA, POR PROCESSO
  * a rede (ou «sem carimbo»), a fase, se está indexado;
  * o Index atribuído (id e nome) — ou que NÃO há nenhum;
  * o estado da análise IA (`index_job_*`);
  * os indexadores activos (cargo na conta OU num acesso por empresa) e a
    carga de cada um, para se escolher a quem atribuir.

O QUE NÃO FAZ: não escreve nada. Atribuir faz-se no ecrã (Gerir atribuições).
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402
from services.process_assignment import (  # noqa: E402
    MAX_ACTIVE_PROCESSES_PER_INDEXER,
    _cargas_dos_indexadores,
)
from services.role_ucr import PAPEIS_DO_INDEX, filtro_de_papel  # noqa: E402

CAMPOS = {
    "_id": 0, "id": 1, "process_number": 1, "client_name": 1, "status": 1,
    "network_id": 1, "company_id": 1, "is_indexed": 1, "assigned_indexacao_id": 1,
    "indexacao_name": 1, "index_assigned_at": 1, "index_job_key": 1,
    "index_job_heartbeat_at": 1, "index_job_rerun": 1, "is_deleted": 1,
}


async def principal(alvo: str) -> int:
    procura = {"$or": [
        {"id": alvo},
        {"client_name": {"$regex": re.escape(alvo), "$options": "i"}},
    ]}
    processos = await db.processes.find(procura, CAMPOS).to_list(20)
    if not processos:
        print(f"Nenhum processo encontrado para «{alvo}».")
        return 1

    for p in processos:
        print("=" * 66)
        print(f"Processo {p.get('process_number') or '?'}  id={p['id']}  cliente={p.get('client_name')}")
        print(f"  rede: {p.get('network_id') or 'SEM CARIMBO (conta como a rede de omissão)'}")
        print(f"  fase: {p.get('status')}   indexado: {bool(p.get('is_indexed'))}"
              f"   eliminado: {bool(p.get('is_deleted'))}")
        idx = p.get("assigned_indexacao_id")
        if idx:
            u = await db.users.find_one({"id": idx}, {"_id": 0, "name": 1, "is_active": 1})
            estado = "inexistente" if not u else ("ACTIVO" if u.get("is_active", True) else "INACTIVO")
            print(f"  Index atribuído: {p.get('indexacao_name') or (u or {}).get('name') or '?'}"
                  f" ({idx}) — conta {estado}")
        else:
            print("  Index atribuído: NENHUM — os ficheiros na pasta Index não têm quem os trate.")
        if p.get("index_job_key"):
            print(f"  análise IA: a correr ({p['index_job_key']}), último sinal {p.get('index_job_heartbeat_at')}"
                  f"{' — repetição pedida' if p.get('index_job_rerun') else ''}")

    query = {"$and": [{"is_active": True}, await filtro_de_papel(PAPEIS_DO_INDEX, db)]}
    indexadores = await db.users.find(
        query, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
    ).to_list(200)
    cargas = await _cargas_dos_indexadores(indexadores)
    print("=" * 66)
    print(f"Indexadores activos (cargo na conta ou num acesso por empresa): {len(cargas)}")
    for c in sorted(cargas, key=lambda c: c["active_count"]):
        cheio = "  (CHEIO)" if c["active_count"] >= MAX_ACTIVE_PROCESSES_PER_INDEXER else ""
        print(f"  {c['name']:<30} {c['active_count']:>3}/{MAX_ACTIVE_PROCESSES_PER_INDEXER}{cheio}  {c['id']}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(principal(sys.argv[1])))
