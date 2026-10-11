"""
====================================================================
MIGRAÇÃO: um workflow POR REDE (multi-tenant, Out 2026)
====================================================================
O workflow (as fases, as flags de propósito, as macro-fases e os modelos de
tarefas) era GLOBAL: uma única colecção `workflow_statuses` sem noção de
rede. Passa a ter um conjunto por rede (`network_id`), editável pelo Admin/CEO
dessa rede. Este script DUPLICA o workflow global actual para todas as redes
existentes.

O QUE FAZ  (nesta ordem — a ordem é o que o torna seguro)
  1. **Índice único por `name`** — se existir (o `idx_workflow_name` que o
     restauro de cópias de segurança criava), é removido ANTES de copiar:
     recusaria as cópias, que repetem os nomes por rede. É substituído por
     um único `(network_id, name)` no fim, SE não houver duplicados.
  2. **Cópias por rede** — para cada rede (as das empresas, mais a de
     omissão `TENANT_DEFAULT_NETWORK_ID`), cria as fases do MODELO que a rede
     ainda não tem (por nome), com `id` novo e `network_id`. **Nunca altera
     uma fase que a rede já tenha** — correr outra vez não desfaz uma
     edição de um administrador. É a MESMA função que a edição usa
     (`workflow_scope.garantir_workflow_da_rede`): duas implementações da
     regra da cópia divergem.
  3. **`is_hub`** (opcional, `--limpar-is-hub`) — a flag global do Hub
     desapareceu (a capacidade de Index vem da equipa); retira-a das
     empresas onde ficou gravada. É inofensiva se ficar.

O QUE NÃO FAZ
  * não apaga o MODELO (as fases sem `network_id`): é a semente de que as
    redes novas nascem, e o recurso das que ainda não têm as suas;
  * não toca em processos — o `status` de um processo é um NOME, e o nome
    existe na cópia da rede dona;
  * não inventa redes: só as que existem em `companies` (ou a de omissão).

SEGURANÇA
  * Corre contra PRODUÇÃO de propósito (não chama `require_non_production_db`):
    é para isso que existe. Em troca, a omissão é LER e CONTAR; só
    `--aplicar` escreve.
  * Idempotente: a segunda passagem escreve 0.
  * Recusa-se a correr se o modelo estiver vazio, ou tiver nomes repetidos
    (copiar duplicados multiplicava o defeito por todas as redes): resolva
    primeiro com `POST /admin/workflow-statuses/fix-duplicates`.

EXECUÇÃO
  cd backend && python -m scripts.migrar_workflow_por_rede                  # só mostra
  cd backend && python -m scripts.migrar_workflow_por_rede --aplicar
  cd backend && python -m scripts.migrar_workflow_por_rede --aplicar --limpar-is-hub
====================================================================
"""
import argparse
import asyncio
import logging
import os
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("migrar_workflow_por_rede")

SEM_REDE = {"$in": [None, ""]}
NOME_DO_INDICE_NOVO = "idx_workflow_network_name"


class MigracaoRecusada(Exception):
    """O estado actual não permite migrar sem piorar as coisas."""


def _nome_do_indice_unico_por_nome(informacao: dict) -> list[str]:
    """Os índices ÚNICOS cuja chave é exactamente `name` (os que recusam as cópias)."""
    nomes = []
    for nome, definicao in (informacao or {}).items():
        chaves = [tuple(k) for k in (definicao or {}).get("key", [])]
        if definicao.get("unique") and chaves == [("name", 1)]:
            nomes.append(nome)
    return nomes


async def planear(base) -> dict:
    """O que a migração faria, sem escrever nada. Levanta `MigracaoRecusada`."""
    from services.tenant_network import rede_de_omissao
    from services.workflow_scope import redes_que_existem

    modelo = await base.workflow_statuses.find(
        {"network_id": SEM_REDE}, {"_id": 0, "name": 1},
    ).to_list(1000)
    nomes = [m.get("name") for m in modelo if m.get("name")]
    if not nomes:
        raise MigracaoRecusada("O modelo de workflow está vazio: não há o que copiar.")
    repetidos = sorted(n for n, c in Counter(nomes).items() if c > 1)
    if repetidos:
        raise MigracaoRecusada(
            f"O modelo tem nomes repetidos ({repetidos}): resolva com "
            "POST /admin/workflow-statuses/fix-duplicates antes de migrar."
        )

    redes = set(await redes_que_existem())
    omissao = rede_de_omissao()
    if omissao:
        redes.add(omissao)

    por_rede: dict[str, dict] = {}
    for rede in sorted(redes):
        proprias = await base.workflow_statuses.find(
            {"network_id": rede}, {"_id": 0, "name": 1},
        ).to_list(1000)
        tem = {p.get("name") for p in proprias if p.get("name")}
        por_rede[rede] = {"tem": len(tem), "em_falta": [n for n in nomes if n not in tem]}

    try:
        informacao = await base.workflow_statuses.index_information()
    except Exception as exc:  # noqa: BLE001 — o plano não depende dos índices
        logger.warning("Não foi possível ler os índices de workflow_statuses: %s", exc)
        informacao = {}

    com_is_hub = await base.companies.count_documents({"is_hub": {"$exists": True}})
    return {
        "modelo": len(nomes),
        "redes": por_rede,
        "indices_unicos_por_nome": _nome_do_indice_unico_por_nome(informacao),
        "indice_novo_existe": NOME_DO_INDICE_NOVO in (informacao or {}),
        "empresas_com_is_hub": com_is_hub,
    }


async def aplicar(base, *, limpar_is_hub: bool = False) -> dict:
    """Executa a migração (ver o módulo). Devolve o que escreveu."""
    from services.workflow_scope import garantir_workflow_da_rede

    plano = await planear(base)
    escrito: dict[str, Any] = {
        "indices_removidos": [], "fases_criadas": {}, "indice_criado": False,
        "is_hub_removido": 0, "indice_nao_criado": None,
    }

    # 1) O único por `name` recusava as cópias: sai ANTES de copiar.
    for nome in plano["indices_unicos_por_nome"]:
        await base.workflow_statuses.drop_index(nome)
        escrito["indices_removidos"].append(nome)

    # 2) As cópias (só as fases que a rede ainda não tem).
    for rede, estado in plano["redes"].items():
        if estado["em_falta"]:
            escrito["fases_criadas"][rede] = await garantir_workflow_da_rede(rede)

    # 3) O único novo, se for possível — senão diz-se e não se força.
    if not plano["indice_novo_existe"]:
        # (a colecção tem dezenas de documentos: ler e contar em Python é
        # mais simples do que uma agregação, e não depende do Mongo usado)
        todas = await base.workflow_statuses.find({}, {"_id": 0, "network_id": 1, "name": 1}).to_list(50000)
        contagem = Counter(((f.get("network_id") or ""), f.get("name")) for f in todas)
        duplicados = [par for par, c in contagem.items() if c > 1]
        if duplicados:
            escrito["indice_nao_criado"] = (
                f"há {len(duplicados)} par(es) (rede, nome) repetido(s): corrija-os e volte a correr"
            )
        else:
            await base.workflow_statuses.create_index(
                [("network_id", 1), ("name", 1)], name=NOME_DO_INDICE_NOVO, unique=True,
            )
            escrito["indice_criado"] = True

    if limpar_is_hub and plano["empresas_com_is_hub"]:
        resultado = await base.companies.update_many(
            {"is_hub": {"$exists": True}}, {"$unset": {"is_hub": ""}},
        )
        escrito["is_hub_removido"] = getattr(resultado, "modified_count", 0)
    return escrito


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="Escreve. Sem isto só mostra.")
    parser.add_argument("--limpar-is-hub", action="store_true", help="Retira `is_hub` das empresas.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from database import db

    try:
        plano = await planear(db)
    except MigracaoRecusada as exc:
        logger.error("RECUSADO: %s", exc)
        return 2

    prefixo = "" if args.aplicar else "[SÓ LEITURA] "
    logger.info("%sModelo: %d fases.", prefixo, plano["modelo"])
    for rede, estado in plano["redes"].items():
        logger.info("%s  rede %-32s tem %2d, faltam %2d", prefixo, rede, estado["tem"], len(estado["em_falta"]))
    if plano["indices_unicos_por_nome"]:
        logger.info("%sÍndice(s) único(s) por nome a remover: %s", prefixo, plano["indices_unicos_por_nome"])
    logger.info("%sEmpresas com is_hub gravado: %d", prefixo, plano["empresas_com_is_hub"])

    if not args.aplicar:
        logger.info("Nada foi escrito. Repita com --aplicar para migrar.")
        return 0

    escrito = await aplicar(db, limpar_is_hub=args.limpar_is_hub)
    logger.info("Escrito: %s", escrito)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
