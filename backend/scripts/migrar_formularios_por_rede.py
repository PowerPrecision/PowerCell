"""
====================================================================
MIGRAÇÃO: um formulário público POR REDE (multi-tenant, Out 2026, D-37)
====================================================================
O `form_config` (campos, passos, rótulos e opções do registo público) era UM
documento global. Passa a haver um por rede (`network_id`), editável pelo
Admin/CEO dessa rede. Este script DUPLICA o formulário global actual para todas
as redes existentes e carimba os modelos personalizados (`form_templates`) que
ainda não pertencem a nenhuma.

O QUE FAZ
  1. **Cópias por rede** — para cada rede (as das empresas, mais a de omissão
     `TENANT_DEFAULT_NETWORK_ID`) sem formulário próprio, cria-o a partir do MODELO
     (o documento sem `network_id`). **Nunca altera** um formulário que a rede já
     tenha — correr outra vez não desfaz uma edição de um administrador. É a MESMA
     função que a edição usa (`form_config_scope.garantir_formulario_da_rede`).
  2. **Modelos personalizados** (`form_templates` sem `network_id`) — carimba-os
     com a rede de omissão (eram do único formulário que havia). Sem rede de
     omissão não adivinha: deixa-os como estão (continuam visíveis a todas).

O QUE NÃO FAZ
  * não apaga o MODELO: é a semente das redes novas e o recurso das que ainda não
    têm o seu;
  * não toca nos registos já feitos — o cliente guarda os valores, não o formulário;
  * não inventa redes: só as que existem em `companies` (ou a de omissão).

SEGURANÇA
  Corre contra PRODUÇÃO de propósito (não chama `require_non_production_db`): é para
  isso que existe. Em troca, a omissão é LER e CONTAR; só `--aplicar` escreve.
  Idempotente: a segunda passagem escreve 0. Sem modelo, as cópias nascem dos
  defaults do código (o que o formulário já mostrava).

EXECUÇÃO
  cd backend && python -m scripts.migrar_formularios_por_rede            # só mostra
  cd backend && python -m scripts.migrar_formularios_por_rede --aplicar
====================================================================
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("migrar_formularios_por_rede")

SEM_REDE = {"$in": [None, ""]}


async def planear(base) -> dict:
    """O que a migração faria, sem escrever nada."""
    from services.tenant_network import rede_de_omissao
    from services.workflow_scope import redes_que_existem

    redes = set(await redes_que_existem())
    omissao = rede_de_omissao()
    if omissao:
        redes.add(omissao)

    modelo = await base.form_config.find_one({"type": "public_form", "network_id": SEM_REDE}, {"_id": 0, "fields": 1})
    sem_formulario = []
    for rede in sorted(redes):
        proprio = await base.form_config.find_one({"type": "public_form", "network_id": rede}, {"_id": 0, "type": 1})
        if not proprio:
            sem_formulario.append(rede)

    modelos_soltos = await base.form_templates.count_documents({"network_id": SEM_REDE})
    return {
        "modelo_existe": bool(modelo),
        "campos_do_modelo": len((modelo or {}).get("fields") or []),
        "redes": sorted(redes),
        "redes_sem_formulario": sem_formulario,
        "rede_de_omissao": omissao or None,
        "templates_sem_rede": modelos_soltos,
    }


async def aplicar(base) -> dict:
    """Executa a migração (ver o módulo). Devolve o que escreveu."""
    from services.form_config_scope import garantir_formulario_da_rede

    plano = await planear(base)
    escrito: dict[str, Any] = {"formularios_criados": [], "templates_carimbados": 0}

    for rede in plano["redes_sem_formulario"]:
        if await garantir_formulario_da_rede(rede):
            escrito["formularios_criados"].append(rede)

    omissao = plano["rede_de_omissao"]
    if omissao and plano["templates_sem_rede"]:
        resultado = await base.form_templates.update_many(
            {"network_id": SEM_REDE}, {"$set": {"network_id": omissao}},
        )
        escrito["templates_carimbados"] = getattr(resultado, "modified_count", 0)
    return escrito


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="Escreve. Sem isto só mostra.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from database import db

    plano = await planear(db)
    prefixo = "" if args.aplicar else "[SÓ LEITURA] "
    logger.info(
        "%sModelo: %s (%d campos). Redes: %s",
        prefixo, "existe" if plano["modelo_existe"] else "NÃO existe (nascem dos defaults)",
        plano["campos_do_modelo"], ", ".join(plano["redes"]) or "—",
    )
    logger.info("%sRedes sem formulário próprio: %s", prefixo, plano["redes_sem_formulario"] or "nenhuma")
    logger.info("%sModelos personalizados sem rede: %d", prefixo, plano["templates_sem_rede"])
    if not plano["rede_de_omissao"] and plano["templates_sem_rede"]:
        logger.warning("TENANT_DEFAULT_NETWORK_ID por definir: os modelos sem rede ficam como estão.")

    if not args.aplicar:
        logger.info("Nada foi escrito. Repita com --aplicar para migrar.")
        return 0

    escrito = await aplicar(db)
    logger.info("Escrito: %s", escrito)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
