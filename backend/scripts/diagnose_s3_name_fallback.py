#!/usr/bin/env python3
"""Mede o custo de apagar o recurso por NOME na leitura de documentos (D-19).

A PERGUNTA
==========
O Lote 6 fez a pasta documental derivar do ID e despromoveu a procura por
nome: perdeu o score, ficou só com o match EXACTO e serve a LEITURA de uma
ficha legada sem `s3_folder` gravado. Falta apagá-la — e apagar às cegas
esconde documentos que existem. **Quantas fichas deixam de ver os seus
documentos, e quantos ficheiros são?**

É esse número que decide, e é esse número que este script imprime. A
classificação vive em `services/s3_name_fallback_audit.py` (puro, com
testes); aqui só se lê a base de dados e o bucket.

ESTE SCRIPT CORRE CONTRA PRODUÇÃO — DE PROPÓSITO
================================================
Como o `diagnose_assignment_drift.py`, NÃO chama `require_non_production_db`:
a dívida que mede está nos dados reais. Em troca é **só de leitura** — não
tem nenhuma bandeira de escrita e não toca em `s3_folder` nenhum. O
religamento é uma decisão humana, feita no painel de Administração
(`/configuracoes` → Manutenção → Religamento de Pastas S3), que é
precisamente onde a colisão se resolve escolhendo de quem é a pasta.

OS CINCO VEREDICTOS
===================
    mapeado           tem `s3_folder` e a pasta existe → o corte não lhe toca
    mapeado_quebrado  tem `s3_folder` e a pasta NÃO existe → já partido hoje
    sem_pasta         sem mapeamento e o nome não resolve → nada a perder
    depende_do_nome   sem mapeamento, o nome resolve, a pasta TEM ficheiros
                      → **perde documentos no corte**, religável
    colisao_de_nome   o mesmo, com DUAS OU MAIS fichas na mesma pasta
                      → a D-19 pura: uma pessoa tem de decidir de quem é

SEM BUCKET NÃO HÁ CONCLUSÃO
===========================
A primeira execução deste script correu em dev, onde o S3 não está
configurado: o inventário saiu vazio, todas as fichas caíram em
«sem_pasta» e o relatório imprimiu «o recurso por nome pode ser apagado
sem esconder documento nenhum» — a frase mais perigosa que aqui podia
aparecer, e produzida por uma medição que não aconteceu. Hoje sai com
código 2 e diz o que falta. É a mesma regra do `rede_consensual` do
`backfill_network_id`: perante uma pergunta sem resposta, não adivinhar.

A SUPERFÍCIE QUE NÃO SE MEDE AQUI
=================================
`GET /onedrive/files/{client_name}` chamava o `list_files` **sem**
`s3_folder`, logo tomava o recurso por nome SEMPRE, mesmo para uma ficha
correctamente mapeada. Não entra nesta contagem porque não é um custo do
corte: era uma porta aberta, e foi fechada no mesmo lote em que esta
medição nasceu.

USO
===
    MONGO_URL=... DB_NAME=... python scripts/diagnose_s3_name_fallback.py
    MONGO_URL=... DB_NAME=... python scripts/diagnose_s3_name_fallback.py \
        --csv /tmp/d19.csv --limite-exemplos 50
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo.errors import PyMongoError  # noqa: E402
from services.s3_document_root import RAIZ  # noqa: E402
from services.s3_name_fallback_audit import (  # noqa: E402
    InventarioIndisponivel,
    VEREDICTO_ANOMALIA,
    VEREDICTO_COLISAO,
    VEREDICTO_DEPENDE_DO_NOME,
    VEREDICTO_MAPEADO,
    VEREDICTO_MAPEADO_QUEBRADO,
    VEREDICTO_SEM_PASTA,
    Ficha,
    Pasta,
    auditar,
    para_religar,
    resumir,
)

ORDEM_DOS_VEREDICTOS = [
    VEREDICTO_ANOMALIA,
    VEREDICTO_COLISAO,
    VEREDICTO_DEPENDE_DO_NOME,
    VEREDICTO_MAPEADO_QUEBRADO,
    VEREDICTO_SEM_PASTA,
    VEREDICTO_MAPEADO,
]

ROTULOS = {
    VEREDICTO_ANOMALIA: "ANOMALIA: s3_folder não é texto (rebenta HOJE)",
    VEREDICTO_COLISAO: "colisão de nome (duas fichas, uma pasta)",
    VEREDICTO_DEPENDE_DO_NOME: "depende do nome (perde documentos no corte)",
    VEREDICTO_MAPEADO_QUEBRADO: "mapeado quebrado (já partido hoje)",
    VEREDICTO_SEM_PASTA: "sem pasta (nada a perder)",
    VEREDICTO_MAPEADO: "mapeado (o corte não lhe toca)",
}

#: Só os campos precisos. Um processo inteiro traz o cliente desencriptado
#: e não há motivo nenhum para o ler aqui — é a regra do
#: `diagnose_assignment_drift`.
PROJECCAO_PROCESSO = {
    "_id": 0, "id": 1, "client_name": 1, "second_client_name": 1,
    "titular2_data": 1, "s3_folder": 1, "process_number": 1, "is_deleted": 1,
}
PROJECCAO_CLIENTE = {
    "_id": 0, "id": 1, "nome": 1, "name": 1, "client_name": 1,
    "s3_folder": 1, "is_deleted": 1,
}


def _argumentos():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--limite-exemplos", type=int, default=20,
        help="Quantas linhas accionáveis imprimir (default 20). A lista "
             "completa sai com --csv.",
    )
    p.add_argument(
        "--csv", default=None,
        help="Escreve a lista accionável completa neste ficheiro, pronta "
             "para percorrer no painel de religamento.",
    )
    p.add_argument(
        "--incluir-eliminados", action="store_true",
        help="Inclui fichas com is_deleted. Por omissão ficam fora: um "
             "processo eliminado não tem separador de documentos para "
             "esvaziar, e contá-lo inflacionava o custo do corte.",
    )
    return p.parse_args()


async def _carregar_fichas(incluir_eliminados: bool) -> list[Ficha]:
    from database import db

    filtro = {} if incluir_eliminados else {"is_deleted": {"$ne": True}}

    fichas: list[Ficha] = []
    processos = await db.processes.find(filtro, PROJECCAO_PROCESSO).to_list(100000)
    for doc in processos:
        if not doc.get("id"):
            continue
        segundo = doc.get("second_client_name") or (
            (doc.get("titular2_data") or {}).get("nome")
        )
        fichas.append(Ficha(
            tipo="processo",
            id=doc["id"],
            nome=doc.get("client_name") or "",
            s3_folder=doc.get("s3_folder"),
            segundo_nome=segundo,
            etiqueta=doc.get("process_number") or "",
        ))

    clientes = await db.clients.find(filtro, PROJECCAO_CLIENTE).to_list(100000)
    for doc in clientes:
        if not doc.get("id"):
            continue
        fichas.append(Ficha(
            tipo="cliente",
            id=doc["id"],
            nome=doc.get("nome") or doc.get("name") or doc.get("client_name") or "",
            s3_folder=doc.get("s3_folder"),
        ))

    return fichas


def _carregar_pastas() -> list[Pasta] | None:
    """Inventário das pastas de TOPO com a contagem de documentos úteis.

    Uma listagem com `Delimiter="/"` dá os nomes mas não os ficheiros, e é
    o número de ficheiros que decide se o corte custa algo. Logo percorre-se
    o prefixo inteiro uma vez e agrega-se pelo primeiro segmento — os
    `.keep` ficam de fora (ver `conta_ficheiros_uteis`), senão uma pasta
    criada e vazia aparecia com seis documentos a perder.
    """
    from services.s3_name_fallback_audit import MARCADOR_DE_PASTA
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        return None

    contagens: dict[str, int] = {}
    try:
        paginator = s3_service.s3_client.get_paginator("list_objects_v2")
        paginas = list(paginator.paginate(
            Bucket=s3_service.bucket_name, Prefix=RAIZ,
        ))
    except Exception as exc:
        print(f"⚠  Falha a listar o bucket: {exc}")
        return None
    for pagina in paginas:
        for objecto in pagina.get("Contents", []) or []:
            chave = objecto.get("Key") or ""
            relativo = chave[len(RAIZ):]
            if not relativo or "/" not in relativo:
                continue
            topo = relativo.split("/")[0]
            if not topo:
                continue
            contagens.setdefault(topo, 0)
            if not chave.endswith(MARCADOR_DE_PASTA):
                contagens[topo] += 1

    return [Pasta(nome=nome, ficheiros=n) for nome, n in contagens.items()]


def _imprimir(resultados, pastas, args) -> None:
    resumo = resumir(resultados)
    linhas = para_religar(resultados)

    print("=" * 70)
    print("D-19 — CUSTO DE APAGAR O RECURSO POR NOME NA LEITURA")
    print("=" * 70)
    print(f"Fichas auditadas: {resumo['total']}  "
          f"(pastas de topo no bucket: {len(pastas)})")
    print("-" * 70)
    for veredicto in ORDEM_DOS_VEREDICTOS:
        quantos = resumo["por_veredicto"].get(veredicto, 0)
        print(f"  {quantos:>6}  {ROTULOS[veredicto]}")
    print("-" * 70)
    print(f"  FICHAS EM RISCO NO CORTE: {resumo['fichas_em_risco']}")
    print(f"  PASTAS ENVOLVIDAS:        {resumo['pastas_em_risco']}")
    print(f"  DOCUMENTOS QUE DESAPARECEM DO ECRÃ: {resumo['ficheiros_em_risco']}")
    if resumo["fichas_em_risco"] == 0:
        print("\n  → O recurso por nome pode ser apagado sem esconder "
              "documento nenhum.")
    else:
        print("\n  → Religar estas fichas no painel de Administração "
              "ANTES de apagar o recurso.")
    print("-" * 70)

    # Bloco PRÓPRIO e depois da conclusão do corte, de propósito: a
    # anomalia não é um custo do corte (estas fichas nunca chegam ao ramo
    # do nome, logo contá-la lá inflacionava o número que decide), mas é
    # uma aba Documentos que responde 500 HOJE. Misturar as duas coisas
    # fazia perder as duas: ou o corte parecia mais caro do que é, ou a
    # avaria passava despercebida debaixo de um "pode apagar-se".
    if resumo["anomalias"]:
        print(f"  ⚠ ANOMALIAS DE DADOS: {resumo['anomalias']} ficha(s) com "
              "`s3_folder` gravado com o tipo errado.")
        print("    Estas fichas rebentam a aba Documentos hoje "
              "(AttributeError no list_files).")
        print("    Corrigir o registo (ou religar no painel) — "
              "independentemente do corte.")
        print("-" * 70)

    if linhas:
        print(f"ACCIONÁVEIS (pior caso primeiro, {min(len(linhas), args.limite_exemplos)}"
              f" de {len(linhas)}):")
        for linha in linhas[:args.limite_exemplos]:
            partilha = (
                f"  ⚠ partilhada com {', '.join(linha['partilhada_com'])}"
                if linha["partilhada_com"] else ""
            )
            etiqueta = f" [{linha['etiqueta']}]" if linha["etiqueta"] else ""
            print(f"  {linha['veredicto']:<16} {linha['tipo']}:{linha['id']}"
                  f"{etiqueta} «{linha['nome']}»")
            if linha["valor_cru"] is not None:
                # Sem o valor cru, quem corrige vai ao Mongo à mão
                # descobrir o que lá está.
                print(f"      → gravado: {linha['valor_cru']}")
            else:
                print(f"      → {linha['s3_folder_sugerido']}  "
                      f"({linha['ficheiros']} ficheiro(s)){partilha}")

    if args.csv:
        destino = Path(args.csv)
        with destino.open("w", newline="", encoding="utf-8") as fh:
            escritor = csv.DictWriter(fh, fieldnames=[
                "veredicto", "tipo", "id", "etiqueta", "nome",
                "s3_folder_sugerido", "ficheiros", "partilhada_com", "valor_cru",
            ])
            escritor.writeheader()
            for linha in linhas:
                escritor.writerow({
                    **linha,
                    "partilhada_com": ";".join(linha["partilhada_com"]),
                })
        print(f"\nLista completa ({len(linhas)} linhas) → {destino}")
    print("=" * 70)


async def principal() -> int:
    args = _argumentos()
    # LOTE 9 — o contrato de códigos de saída deste ficheiro prometia 2 para
    # «a leitura não aconteceu (sem base de dados)» e só o cumpria para o
    # inventário do bucket. Uma base de dados que não responde saía com um
    # traceback e código 1, que se lê como «o script está partido» e não como
    # «não mediste nada»: é o mesmo erro que o `InventarioIndisponivel`
    # existe para evitar, na outra metade da leitura.
    try:
        fichas = await _carregar_fichas(args.incluir_eliminados)
    except PyMongoError as exc:
        print("=" * 70)
        print("D-19 — MEDIÇÃO NÃO REALIZADA")
        print("=" * 70)
        print(f"  A base de dados não respondeu: {exc}")
        print(
            "\n  Nenhuma ficha foi lida, logo não há contagem nenhuma — e um\n"
            "  relatório de zero fichas leria-se como «não há risco».\n"
            "  Confirmar MONGO_URL/DB_NAME e repetir."
        )
        print("=" * 70)
        return 2
    pastas = _carregar_pastas()
    try:
        resultados = auditar(fichas, pastas)
    except InventarioIndisponivel as exc:
        print("=" * 70)
        print("D-19 — MEDIÇÃO NÃO REALIZADA")
        print("=" * 70)
        print(f"  {exc}")
        print(
            "\n  Faltou o inventário do bucket. Em dev o S3 não está "
            "configurado;\n  esta medição corre contra o ambiente que tem "
            "o bucket real (as\n  credenciais vêm das variáveis de "
            "ambiente, nunca do código).\n"
            f"  Fichas que teriam sido auditadas: {len(fichas)}."
        )
        print("=" * 70)
        return 2
    _imprimir(resultados, pastas, args)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
