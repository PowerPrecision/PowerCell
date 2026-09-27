"""
====================================================================
COMPARAÇÃO ENTRE REDES — GET /api/stats/redes
====================================================================
Refinamento Analítico e SLAs (Dashboard), Camada 2.

A DECISÃO DE SEGURANÇA QUE ISTO RESPEITA
  "A tolerância zero mantém-se. A Direção só poderá comparar a Domus e a
  Power se a conta de utilizador deles os credenciar nas três empresas. A
  segurança sobrepõe-se à vaidade do relatório."

  Portanto: este endpoint compara **as redes que o utilizador autenticado
  já pode ver**, derivadas do MESMO `resolve_tenant_scope` de todas as
  listagens. Não há aqui nenhuma cláusula de excepção, nenhum papel que
  veja tudo, nenhum parâmetro que amplie o âmbito.

  Se a conta só tiver associação a uma rede, vê UMA linha. Isso é
  comportamento correcto, não um defeito — e é dito na resposta
  (`redes_no_ambito`), para ninguém interpretar uma linha só como uma
  falha de dados.

SÓ AGREGADOS
  Contagens, somas e médias. Nunca um processo, nunca um cliente, nunca um
  nome. Uma comparação de eficiência operacional não precisa de saber de
  QUEM é o processo — e se precisasse, não era uma comparação de redes.

A PILHA POR CARIMBAR
  Os documentos sem `network_id` entram no âmbito de quem detém a rede de
  omissão (regra do Lote 4) e aparecem agrupados como `(sem rede)`. Em
  produção a medição diz que são zero; deixar o grupo visível é o que
  garante que, se voltarem a existir, ninguém os confunde com uma rede.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any

from database import db
from services.redis_cache import cache_get, cache_set
from services.stats_macro_bridge import (
    ORDEM_DO_FUNIL,
    PonteDeMacros,
    construir_ponte,
)
from services.stats_scope import AmbitoEstatistico, com_ambito, resolver_ambito
from services.tenant_network import CAMPO_REDE
from services.workflow_phases import FASE_DESCONHECIDA

logger = logging.getLogger(__name__)

TTL_DA_CACHE = 900
SEM_REDE = "(sem rede)"


def construir_pipeline(ambito: AmbitoEstatistico, ponte: PonteDeMacros) -> list[dict]:
    """Um `$group` por rede E macro-fase. PURO.

    Duas chaves no mesmo `$group` em vez de duas agregações: a matriz
    rede × macro-fase é o que a comparação precisa, e uma segunda passagem
    pela colecção para obter os totais por rede seria trabalho a dobrar
    sobre os mesmos documentos.
    """
    return [
        {"$match": com_ambito({"is_deleted": {"$ne": True}}, ambito)},
        {
            "$project": {
                "rede": {"$ifNull": [f"${CAMPO_REDE}", SEM_REDE]},
                "macro": ponte.expressao(),
                "valor_financiado": {
                    "$ifNull": ["$credit_data.requested_amount", 0],
                },
            }
        },
        {
            "$group": {
                "_id": {"rede": "$rede", "macro": "$macro"},
                "processos": {"$sum": 1},
                "valor_financiado": {"$sum": "$valor_financiado"},
            }
        },
    ]


def montar_comparacao(linhas: list[dict]) -> list[dict[str, Any]]:
    """A matriz rede × macro-fase traduzida em linhas comparáveis. PURA."""
    por_rede: dict[str, dict[str, Any]] = {}

    for linha in linhas:
        chave = linha.get("_id") or {}
        rede = str(chave.get("rede") or SEM_REDE)
        macro = str(chave.get("macro") or FASE_DESCONHECIDA)
        processos = int(linha.get("processos") or 0)
        valor = float(linha.get("valor_financiado") or 0)

        alvo = por_rede.setdefault(rede, {
            "rede": rede,
            "processos": 0,
            "valor_financiado": 0.0,
            "por_macro": {},
        })
        alvo["processos"] += processos
        alvo["valor_financiado"] += valor
        alvo["por_macro"][macro] = alvo["por_macro"].get(macro, 0) + processos

    resultado: list[dict[str, Any]] = []
    for rede, dados in por_rede.items():
        por_macro = dados["por_macro"]
        concluidos = por_macro.get("concluido", 0)
        perdidos = por_macro.get("perdido", 0)
        decididos = concluidos + perdidos

        # Em curso = as etapas do funil antes do fecho. A reconciliação
        # fica FORA: são processos cuja fase o motor não conhece, e
        # contá-los como "em curso" era afirmar algo que não se sabe.
        em_curso = sum(
            por_macro.get(macro, 0)
            for macro in ORDEM_DO_FUNIL
            if macro != "concluido"
        )

        resultado.append({
            "rede": rede,
            "processos": dados["processos"],
            "valor_financiado": round(dados["valor_financiado"], 2),
            "em_curso": em_curso,
            "concluidos": concluidos,
            "perdidos": perdidos,
            "desconhecidos": por_macro.get(FASE_DESCONHECIDA, 0),
            # Taxa sobre os DECIDIDOS e não sobre o total: com o total no
            # denominador, uma rede jovem com muitos processos em curso
            # parecia pior do que uma antiga — mediria a idade da carteira,
            # não a eficiência.
            "taxa_de_conclusao": (
                round(concluidos / decididos * 100, 1) if decididos else None
            ),
            "por_macro": por_macro,
        })

    resultado.sort(key=lambda r: -r["processos"])
    return resultado


async def run_get_network_comparison(user: dict) -> dict[str, Any]:
    """GET /api/stats/redes — comparação entre as redes do ÂMBITO de quem pede."""
    from models.permissions import resolve_capability

    if not resolve_capability(user, "STATS_VIEW"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403, detail="Sem permissão para ver estatísticas",
        )

    ambito = await resolver_ambito(user)
    cache_key = ambito.chave("stats:redes:v1")
    cached = await cache_get(cache_key)
    if cached:
        return cached

    ponte = await construir_ponte(ambito)

    try:
        linhas = await db.processes.aggregate(
            construir_pipeline(ambito, ponte), allowDiskUse=True,
        ).to_list(200)
    except Exception as exc:
        logger.error("[STATS-REDES] Erro na agregação: %s", exc)
        linhas = []

    resultado = {
        "redes": montar_comparacao(linhas),
        # Quantas redes o âmbito de quem pede abrange. Uma linha só é
        # comportamento correcto — e é preciso dizê-lo, senão parece falta
        # de dados.
        "redes_no_ambito": len(ambito.scope.network_ids),
    }
    await cache_set(cache_key, resultado, ttl=TTL_DA_CACHE)
    return resultado
