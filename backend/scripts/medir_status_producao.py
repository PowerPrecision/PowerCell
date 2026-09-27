"""
====================================================================
MEDIÇÃO: `processes.status` contra a configuração do workflow
====================================================================
Épico 10, Parte 3 (Estado & Workflow), Passo Zero.
Ver `services/workflow_status_coverage.py`.

PARA QUE SERVE
  O raio-x encontrou cinco vocabulários de fases no código, dois dos quais
  não existem no motor. Mas isso é o que o CÓDIGO acredita. Antes de
  promover `workflow_statuses` a Única Fonte da Verdade é preciso saber o
  que essa promoção torna invisível — e isso só a base de dados real sabe.

  A saída responde a quatro perguntas:
    1. Que valores de `status` existem mesmo, e com que peso.
    2. Quantos processos estão HOJE invisíveis no Kanban (status sem fase).
    3. Desses, quantos um alias resolve sem adivinhar — e quantos não.
    4. Que fases o agrupamento em macro-fases ainda não cobre.

ESTE SCRIPT NÃO ESCREVE NADA
  Não tem `--aplicar` e não o vai ter. O `medir_cobertura_s3` podia propor
  escritas porque a correspondência pasta↔processo era inequívoca; aqui o
  passo seguinte é uma decisão de produto (que macro-fase leva cada fase),
  e uma máquina não a fecha sozinha. Há uma guarda sobre o código-fonte
  deste ficheiro em `tests/unit/test_workflow_status_coverage.py` a
  afirmar que nenhuma operação de escrita aparece aqui.

  Por isso mesmo NÃO chama `scripts/env_guard.py`: o guarda existe para
  impedir que um seed escreva em produção, e é contra produção que este
  script tem de correr.

EXECUÇÃO (no ambiente de PRODUÇÃO, com MONGO_URL/DB_NAME reais)
  cd backend && python -m scripts.medir_status_producao
  cd backend && python -m scripts.medir_status_producao --json status.json

  Flags:
    --json FICHEIRO  Escreve o retrato completo (é este que me devolve)
    --incluir-eliminados  Conta também os soft-deleted, à parte
====================================================================
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import db  # noqa: E402
from services.workflow_status_coverage import (  # noqa: E402
    analisar,
    formatar_relatorio,
    para_json,
)


async def contar_por_status(*, eliminados: bool) -> tuple[dict[str, int], int]:
    """``status -> contagem`` numa só agregação. Devolve também os sem status.

    Agregação e não `distinct` + N contagens: `idx_status` cobre o
    agrupamento e uma passagem chega. Num ambiente com centenas de
    milhares de processos a diferença não é cosmética.

    `status` ausente e `status: None` são o MESMO caso (uma lead do
    formulário público) e contam juntos — `LEAD_STATUS_VALUES` já os trata
    assim em `process_status.py`.
    """
    correspondencia = (
        {"is_deleted": True} if eliminados else {"is_deleted": {"$ne": True}}
    )
    pipeline = [
        {"$match": correspondencia},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    contagens: dict[str, int] = {}
    sem_status = 0
    async for linha in db.processes.aggregate(pipeline):
        chave = linha.get("_id")
        quantos = int(linha.get("n") or 0)
        if chave is None or chave == "":
            sem_status += quantos
        else:
            contagens[str(chave)] = contagens.get(str(chave), 0) + quantos
    return contagens, sem_status


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
                        help="Conta também os processos com is_deleted")
    args = parser.parse_args()

    print("A ler as fases configuradas …")
    fases = await carregar_fases()
    print(f"  {len(fases)} fase(s) em workflow_statuses.")
    if not fases:
        print(
            "AVISO: a colecção está VAZIA. Sem fases o Kanban não tem colunas "
            "e todo o processo aparece como órfão — o retrato abaixo diz isso, "
            "não um defeito de dados."
        )

    print("A contar processos por status …")
    contagens, sem_status = await contar_por_status(eliminados=False)
    print(f"  {sum(contagens.values()) + sem_status} processo(s) activo(s).")

    contagens_eliminados: dict[str, int] = {}
    if args.incluir_eliminados:
        contagens_eliminados, _ = await contar_por_status(eliminados=True)
        print(f"  {sum(contagens_eliminados.values())} eliminado(s), à parte.")

    retrato = analisar(
        contagens,
        fases,
        contagens_eliminados=contagens_eliminados,
        sem_status=sem_status,
    )
    print(formatar_relatorio(retrato))

    if args.ficheiro_json:
        Path(args.ficheiro_json).write_text(
            json.dumps(para_json(retrato), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Retrato escrito em {args.ficheiro_json}")
    else:
        print(
            "Sem --json só viu o resumo. Corra com "
            "`--json status.json` para o retrato completo."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
