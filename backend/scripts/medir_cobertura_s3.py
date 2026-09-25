"""
====================================================================
MEDIÇÃO: cobertura do mapeamento pasta S3 ↔ processo
====================================================================
Épico 10, Gestor de Ficheiros S3, Passo 2. Ver `services/s3_folder_coverage.py`.

PARA QUE SERVE
  O isolamento por rede do Explorador resolve-se por
  pasta → `processes.s3_folder` → `processes.network_id`. Uma pasta que
  nenhum processo reclame não tem rede e **falha fechada**: fica invisível
  a toda a gente excepto admin/CEO.

  Isso é correcto em segurança e pode ser péssimo em produto. Este script
  diz, com números do ambiente REAL, quanto é que isso custa — antes de se
  ligar o isolamento, não depois.

LEITURA POR OMISSÃO. Só escreve com `--aplicar`.

EXECUÇÃO
  cd backend && python -m scripts.medir_cobertura_s3
  cd backend && python -m scripts.medir_cobertura_s3 --aplicar

  Flags:
    --aplicar        Grava os mapeamentos propostos (só os inequívocos)
    --json FICHEIRO  Escreve o retrato completo para análise posterior
    --limite N       Máximo de pastas a listar (diagnóstico; 0 = tudo)

O QUE O `--aplicar` FAZ, E O QUE NUNCA FAZ
  Preenche `processes.s3_folder` para as pastas órfãs cujo nome corresponda
  a UM ÚNICO processo sem pasta. Recusa-se a escolher quando há mais do que
  um candidato — a mesma regra do `rede_consensual` do Lote 4. Um mapeamento
  errado torna a pasta visível à rede errada, e a execução seguinte
  aceitá-lo-ia como verdade.

  Nunca apaga, nunca reescreve um mapeamento existente, nunca toca no S3.
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
from services.s3_explorer_paths import RAIZ_DO_EXPLORADOR  # noqa: E402
from services.s3_folder_coverage import (  # noqa: E402
    analisar,
    formatar_relatorio,
)

PROJECCAO = {"_id": 0, "id": 1, "s3_folder": 1, "network_id": 1, "client_name": 1}


def listar_pastas_do_s3(limite: int = 0) -> list[str]:
    """Todas as pastas de cliente no bucket, com paginação.

    Sem `ContinuationToken` ficaria pelas primeiras 1000 e o denominador
    viria errado — que é exactamente o defeito que o Passo 1 corrigiu na
    listagem do Explorador.
    """
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise SystemExit(
            "S3 não está configurado neste ambiente.\n"
            "Este script tem de correr onde o bucket REAL é alcançável — "
            "em dev os serviços externos estão mockados por desenho."
        )

    prefixo = f"{RAIZ_DO_EXPLORADOR}/"
    pastas: list[str] = []
    token = None

    while True:
        kwargs = {"Bucket": s3_service.bucket_name, "Prefix": prefixo, "Delimiter": "/"}
        if token:
            kwargs["ContinuationToken"] = token
        resposta = s3_service.s3_client.list_objects_v2(**kwargs)

        for cp in resposta.get("CommonPrefixes", []):
            caminho = (cp.get("Prefix") or "").rstrip("/")
            if caminho and caminho != RAIZ_DO_EXPLORADOR:
                pastas.append(caminho)

        if limite and len(pastas) >= limite:
            return pastas[:limite]
        if not resposta.get("IsTruncated"):
            break
        token = resposta.get("NextContinuationToken")
        if not token:
            print("AVISO: o S3 diz 'truncado' sem cursor — listagem incompleta.")
            break

    return pastas


async def carregar_processos() -> list[dict]:
    return await db.processes.find({}, PROJECCAO).to_list(200000)


async def aplicar_propostas(propostas: dict[str, str]) -> int:
    """Grava só os mapeamentos inequívocos. Devolve quantos escreveu."""
    escritos = 0
    for pasta, process_id in propostas.items():
        resultado = await db.processes.update_one(
            # A condição impede corrida: se entretanto ganhou pasta, não se
            # sobrepõe o que lá está.
            {"id": process_id, "$or": [
                {"s3_folder": {"$exists": False}},
                {"s3_folder": None},
                {"s3_folder": ""},
            ]},
            {"$set": {"s3_folder": pasta}},
        )
        if resultado.modified_count:
            escritos += 1
    return escritos


async def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true",
                        help="Grava os mapeamentos propostos (só os inequívocos)")
    parser.add_argument("--json", dest="ficheiro_json", default=None,
                        help="Escreve o retrato completo em JSON")
    parser.add_argument("--limite", type=int, default=0,
                        help="Máximo de pastas a listar (0 = tudo)")
    args = parser.parse_args()

    print(f"A listar pastas em '{RAIZ_DO_EXPLORADOR}/' …")
    pastas = listar_pastas_do_s3(args.limite)
    print(f"  {len(pastas)} pasta(s).")

    print("A ler processos …")
    processos = await carregar_processos()
    print(f"  {len(processos)} processo(s).")

    cobertura = analisar(pastas, processos)
    print(formatar_relatorio(cobertura))

    if args.ficheiro_json:
        Path(args.ficheiro_json).write_text(json.dumps({
            "pastas_no_s3": cobertura.pastas_no_s3,
            "mapeadas": cobertura.mapeadas,
            "percentagem_mapeada": cobertura.percentagem_mapeada,
            "orfas": cobertura.orfas,
            "ambiguas": cobertura.ambiguas,
            "ligacoes_partidas": cobertura.ligacoes_partidas,
            "orfas_resoluveis": cobertura.orfas_resoluveis,
            "processos_totais": cobertura.processos_totais,
            "processos_com_pasta": cobertura.processos_com_pasta,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Retrato escrito em {args.ficheiro_json}")

    if not args.aplicar:
        if cobertura.orfas_resoluveis:
            print(
                f"{len(cobertura.orfas_resoluveis)} órfã(s) têm correspondência "
                "inequívoca. Correr com --aplicar para as mapear."
            )
        return 0

    print(f"A aplicar {len(cobertura.orfas_resoluveis)} mapeamento(s) …")
    escritos = await aplicar_propostas(cobertura.orfas_resoluveis)
    print(f"  {escritos} processo(s) actualizado(s).")
    print(
        "As órfãs restantes NÃO foram adivinhadas: ou não têm candidato, ou "
        "têm mais do que um. Ficam para decisão humana."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
