"""
====================================================================
MEDIÇÃO: o relógio de fases dos processos em produção
====================================================================
Refinamento Analítico e SLAs (Dashboard), Passo Zero.
Ver `services/phase_clock_coverage.py`.

PARA QUE SERVE
  O raio-x concluiu que não existe relógio: nenhum processo sabe quando
  entrou na fase em que está. O carimbo (`fase_desde`) resolve isso para
  o futuro, mas os processos que já existem só têm o `updated_at` — que
  muda com qualquer escrita — como aproximado.

  Antes de semear essa estimativa em produção é preciso saber quão má
  ela é, e em que sentido erra. É isso que este script mede. Corre-se
  OUTRA VEZ depois do backfill: a secção "cobertura do relógio" passa de
  zero para o número de processos carimbados, e a mesma saída serve de
  prova de que o backfill fez o que disse.

ESTE SCRIPT NÃO ESCREVE NADA
  Não tem `--aplicar`, tal como o `medir_status_producao`. O que se faz
  com o retrato — semear estimativas, com que marca, a partir de que
  campo — é uma decisão de produto, e uma decisão dessas não se toma
  dentro do mesmo comando que a mede. Há uma guarda sobre o código-fonte
  deste ficheiro em `tests/unit/test_phase_clock_coverage.py` a afirmar
  que nenhuma operação de escrita aparece aqui.

  E NÃO chama `scripts/env_guard.py`: esse guarda existe para impedir
  que um seed escreva em produção, e é contra produção que isto tem de
  correr.

PORQUE LÊ OS PROCESSOS EM VEZ DE OS AGREGAR NO MONGO
  A agregação seria mais rápida, mas obrigava a reimplementar em
  expressões `$switch` a resolução de `cpcv`, `escriturado` e
  `"Concluidos "` que o `resolver_nome` já faz. Duas implementações da
  mesma regra divergem no primeiro alias novo, e passámos o Épico 10
  inteiro a fechar exactamente esse género de divergência. A projecção
  traz nove campos pequenos por processo; num só cursor, é uma passagem.

EXECUÇÃO (no ambiente de PRODUÇÃO, com MONGO_URL/DB_NAME reais)
  cd backend && python -m scripts.medir_relogio_de_fases
  cd backend && python -m scripts.medir_relogio_de_fases --json relogio.json

  Flags:
    --json FICHEIRO   Escreve o retrato completo (é este que me devolve)
    --incluir-eliminados  Analisa também os soft-deleted (por omissão, não)
====================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402
from services.phase_clock_coverage import (  # noqa: E402
    CAMPO_ESTIMADO,
    CAMPO_FASE_DESDE,
    CAMPO_MACRO_DESDE,
    CAMPO_TEMPOS,
    analisar,
    formatar_relatorio,
    para_json,
)

# Projecção mínima. Ler o processo inteiro traria `personal_data`
# encriptado e os arrays de documentos — centenas de megabytes para
# responder a uma pergunta sobre datas.
PROJECCAO = {
    "_id": 0,
    "status": 1,
    "created_at": 1,
    "updated_at": 1,
    CAMPO_FASE_DESDE: 1,
    CAMPO_MACRO_DESDE: 1,
    CAMPO_ESTIMADO: 1,
    CAMPO_TEMPOS: 1,
    "network_id": 1,
    "company_id": 1,
    "company": 1,
    "company_name": 1,
}


async def ler_processos(*, eliminados: bool) -> list[dict]:
    """As linhas cruas, sem enriquecimento nem desencriptação."""
    correspondencia = (
        {"is_deleted": True} if eliminados else {"is_deleted": {"$ne": True}}
    )
    return await db.processes.find(correspondencia, PROJECCAO).to_list(None)


async def carregar_fases() -> list[dict]:
    """As fases do motor, por ordem — a lista que o Kanban desenha."""
    return await db.workflow_statuses.find(
        {}, {"_id": 0},
    ).sort("order", 1).to_list(500)


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="ficheiro_json", default=None,
                        help="Escreve o retrato completo em JSON")
    parser.add_argument("--incluir-eliminados", action="store_true",
                        help="Analisa também os processos com is_deleted")
    args = parser.parse_args()

    print("A ler as fases configuradas …")
    fases = await carregar_fases()
    print(f"  {len(fases)} fase(s) em workflow_statuses.")
    if not fases:
        print(
            "AVISO: a colecção está VAZIA. Sem fases nenhum valor de status "
            "se resolve e tudo aparece como desconhecido — o retrato abaixo "
            "diz isso, não um defeito de dados."
        )

    print("A ler os processos (projecção de datas e carimbos) …")
    linhas = await ler_processos(eliminados=args.incluir_eliminados)
    print(f"  {len(linhas)} processo(s).")

    agora = datetime.now(timezone.utc)
    retrato = analisar(linhas, fases, agora=agora)
    print(formatar_relatorio(retrato))

    if args.ficheiro_json:
        saida = para_json(retrato)
        saida["medido_em"] = agora.isoformat()
        saida["inclui_eliminados"] = bool(args.incluir_eliminados)
        Path(args.ficheiro_json).write_text(
            json.dumps(saida, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Retrato escrito em {args.ficheiro_json}")
    else:
        print(
            "Sem --json só viu o resumo. Corra com "
            "`--json relogio.json` para o retrato completo."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
