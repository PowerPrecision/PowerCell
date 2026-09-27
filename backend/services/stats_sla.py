"""
====================================================================
SLAs E GARGALOS — GET /api/stats/sla
====================================================================
Refinamento Analítico e SLAs (Dashboard), Camada 2.

DUAS PERGUNTAS DIFERENTES, DOIS NÚMEROS
  1. **Quem está preso AGORA** — `agora - macro_fase_desde`. É a accionável:
     aponta processos concretos e é sobre ela que faz sentido um limiar de
     SLA.
  2. **Quanto tempo demorou, em média** — o acumulador `tempos_macro`, que
     o relógio incrementa À SAÍDA. É a histórica, e só existe para
     transições MEDIDAS (um carimbo estimado nunca entra no acumulador).

  Misturar as duas num só número era o erro fácil: a primeira mede o que
  está a acontecer, a segunda o que aconteceu.

PORQUE `$bucket` E NÃO SÓ A MÉDIA
  Num gargalo a média mente sempre no mesmo sentido: um processo esquecido
  há 400 dias arrasta-a e esconde que 80% passa em 9 dias. O histograma
  mostra a forma da distribuição, e a mediana ao lado diz onde está o
  processo típico. A média vai também, para quem a quiser — mas nunca
  sozinha.

  As bandas são as MESMAS do script de medição
  (`phase_clock_coverage.LIMITES_DAS_BANDAS`). Bandas diferentes fariam o
  retrato de produção e o gráfico contar histórias distintas sobre os
  mesmos dados.

AS MACRO-FASES TERMINAIS NÃO ENTRAM
  Um processo concluído não "demora" em concluído, fica lá. A medição
  mostra-o em bruto: 3.200 processos na banda `61+` de `concluido`. Incluí-
  las fazia o painel gritar sobre processos que estão exactamente onde
  devem estar — e um painel que grita sem razão ensina toda a gente a
  ignorá-lo (a lição do `desactivado ≠ em baixo`, Lote 4 ponto 14).

AS ESTIMATIVAS ABERRANTES NÃO ENTRAM NAS MÉDIAS
  O backfill classificou cada estimativa em `plausivel`, `nunca_tocado`
  (sobrestima) e `tocado_apos_fecho` (subestima). As duas últimas ficam
  fora da amostra — erram para lados OPOSTOS, pelo que não se anulam. A
  resposta traz as duas contagens para a UI poder dizer quantos processos
  ficaram de fora, em vez de o utilizador ver uma média sobre um universo
  que não sabe qual é.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db
from services.phase_clock_coverage import (
    ETIQUETAS_DAS_BANDAS,
    LIMITES_DAS_BANDAS,
    QUALIDADES_ABERRANTES,
)
from services.process_phase_clock import (
    CAMPO_MACRO_DESDE,
    CAMPO_TEMPOS,
)
from services.phase_clock_backfill import CAMPO_QUALIDADE
from services.redis_cache import cache_get, cache_set
from services.stats_macro_bridge import (
    MACROS_COM_SLA,
    PonteDeMacros,
    construir_ponte,
)
from services.stats_scope import AmbitoEstatistico, com_ambito, resolver_ambito

logger = logging.getLogger(__name__)

TTL_DA_CACHE = 900
_MS_POR_DIA = 1000 * 60 * 60 * 24

#: Limites do `$bucket`. O `$bucket` exige fronteiras crescentes e manda
#: para o `default` tudo o que fique fora — é exactamente a última banda.
FRONTEIRAS_DO_BUCKET: list[int] = [0, *LIMITES_DAS_BANDAS]
BANDA_DE_EXCESSO = ETIQUETAS_DAS_BANDAS[-1]


def expressao_de_dias() -> dict[str, Any]:
    """Dias desde a entrada na macro-fase actual.

    Recurso ao `created_at` quando não há carimbo: para um processo nascido
    depois do relógio, a entrada na primeira fase É a criação. Mesma regra
    do `process_phase_clock._segundos_na_macro`, aqui em expressão de
    agregação porque o Mongo é que tem de a avaliar.
    """
    return {
        "$divide": [
            {
                "$subtract": [
                    "$$NOW",
                    {"$toDate": {
                        "$ifNull": [f"${CAMPO_MACRO_DESDE}", "$created_at"],
                    }},
                ]
            },
            _MS_POR_DIA,
        ]
    }


def construir_pipeline_de_presos(
    ambito: AmbitoEstatistico,
    ponte: PonteDeMacros,
) -> list[dict]:
    """Histograma de permanência dos processos que estão AGORA em cada macro.

    `$facet` com um `$bucket` por macro-fase: o `$bucket` agrupa por UMA
    chave numérica e não sabe agrupar também por macro. As etapas
    partilhadas (`$match`, `$project`) correm uma vez.
    """
    valores_por_macro = {
        macro: ponte.valores_de(macro) for macro in MACROS_COM_SLA
    }

    todos = sorted({v for vs in valores_por_macro.values() for v in vs})
    base: list[dict] = [
        {
            "$match": com_ambito(
                {
                    "is_deleted": {"$ne": True},
                    # Só as macro-fases com SLA: as terminais não têm
                    # permanência a medir.
                    "status": {"$in": todos},
                    # As estimativas aberrantes ficam fora da amostra.
                    CAMPO_QUALIDADE: {"$nin": list(QUALIDADES_ABERRANTES)},
                },
                ambito,
            )
        },
        {
            "$project": {
                "macro": ponte.expressao(),
                "dias": expressao_de_dias(),
            }
        },
        # Uma permanência negativa é dado corrompido, não zero dias.
        {"$match": {"dias": {"$gte": 0}}},
    ]

    facetas: dict[str, list[dict]] = {}
    for macro, valores in valores_por_macro.items():
        if not valores:
            continue
        facetas[macro] = [
            {"$match": {"macro": macro}},
            {
                "$bucket": {
                    "groupBy": "$dias",
                    "boundaries": FRONTEIRAS_DO_BUCKET,
                    "default": BANDA_DE_EXCESSO,
                    "output": {
                        "processos": {"$sum": 1},
                        "dias_medios": {"$avg": "$dias"},
                    },
                }
            },
        ]

    if not facetas:
        return []
    return [*base, {"$facet": facetas}]


def construir_pipeline_de_historico(
    ambito: AmbitoEstatistico,
) -> list[dict]:
    """Média e amostra do tempo ACUMULADO por macro-fase.

    Sobre o `tempos_macro`, que só tem transições MEDIDAS. Um `$group`
    único com um `$avg` por macro-fase: os campos ausentes são ignorados
    pelo `$avg`, o que é o comportamento certo — um processo que nunca
    passou por `aprovado` não tem de contar como zero dias lá.
    """
    acumuladores: dict[str, Any] = {"_id": None}
    for macro in MACROS_COM_SLA:
        acumuladores[f"media_{macro}"] = {"$avg": f"${CAMPO_TEMPOS}.{macro}"}
        acumuladores[f"amostra_{macro}"] = {
            "$sum": {
                "$cond": [
                    {"$gt": [{"$ifNull": [f"${CAMPO_TEMPOS}.{macro}", None]}, None]},
                    1,
                    0,
                ]
            }
        }
    return [
        {"$match": com_ambito({"is_deleted": {"$ne": True}}, ambito)},
        {"$group": acumuladores},
    ]


def _mediana_das_bandas(baldes: list[dict], total: int) -> Optional[str]:
    """A BANDA onde cai o processo mediano.

    Uma mediana exacta obrigava a ordenar todas as permanências; a banda
    responde à pergunta de negócio ("onde está o processo típico") com os
    dados que o histograma já traz. E é honesta: devolve um intervalo, que
    é o que se sabe.
    """
    if not total:
        return None
    meio = total / 2
    acumulado = 0
    for balde in baldes:
        acumulado += balde["processos"]
        if acumulado >= meio:
            return balde["banda"]
    return baldes[-1]["banda"] if baldes else None


def _etiqueta_da_fronteira(valor: Any) -> str:
    """O `_id` que o `$bucket` devolve é a fronteira INFERIOR do balde."""
    if valor == BANDA_DE_EXCESSO:
        return BANDA_DE_EXCESSO
    try:
        inferior = int(valor)
    except (TypeError, ValueError):
        return str(valor)
    indice = FRONTEIRAS_DO_BUCKET.index(inferior) if inferior in FRONTEIRAS_DO_BUCKET else None
    if indice is None or indice >= len(ETIQUETAS_DAS_BANDAS):
        return BANDA_DE_EXCESSO
    return ETIQUETAS_DAS_BANDAS[indice]


def montar_sla(
    presos: dict[str, list[dict]],
    historico: dict[str, Any],
    limiares: dict[str, int],
) -> list[dict[str, Any]]:
    """Traduz as duas agregações na resposta por macro-fase. PURA."""
    resposta: list[dict[str, Any]] = []

    for macro in MACROS_COM_SLA:
        baldes_crus = presos.get(macro) or []
        baldes = [
            {
                "banda": _etiqueta_da_fronteira(b.get("_id")),
                "processos": int(b.get("processos") or 0),
                "dias_medios": round(float(b.get("dias_medios") or 0), 1),
            }
            for b in baldes_crus
        ]
        # Bandas vazias entram com zero: um histograma com buracos lê-se
        # como se a banda não existisse.
        por_banda = {b["banda"]: b for b in baldes}
        baldes = [
            por_banda.get(etq, {"banda": etq, "processos": 0, "dias_medios": 0.0})
            for etq in ETIQUETAS_DAS_BANDAS
        ]

        total = sum(b["processos"] for b in baldes)
        dias_totais = sum(b["processos"] * b["dias_medios"] for b in baldes)
        limiar = limiares.get(macro)

        # "Presos" = acima do limiar. Conta-se pelas bandas cuja fronteira
        # INFERIOR já passou o limiar, mais a fracção da banda que o
        # contém — que não se sabe, e por isso não se inventa: a banda que
        # contém o limiar não entra, e a resposta di-lo no `limiar_dias`.
        acima = 0
        for indice, etq in enumerate(ETIQUETAS_DAS_BANDAS):
            fronteira = FRONTEIRAS_DO_BUCKET[indice]
            if limiar is not None and fronteira >= limiar:
                acima += baldes[indice]["processos"]

        media_segundos = historico.get(f"media_{macro}")
        resposta.append({
            "macro_fase": macro,
            "limiar_dias": limiar,
            "em_curso": total,
            "acima_do_limiar": acima,
            "bandas": baldes,
            "dias_medios_em_curso": (
                round(dias_totais / total, 1) if total else None
            ),
            "banda_mediana_em_curso": _mediana_das_bandas(baldes, total),
            "dias_medios_historico": (
                round(float(media_segundos) / 86400.0, 1)
                if media_segundos else None
            ),
            "amostra_historico": int(historico.get(f"amostra_{macro}") or 0),
        })

    return resposta


async def _limiares() -> dict[str, int]:
    """Limiares de SLA do painel de admin. NUNCA cravados no código."""
    try:
        from services.system_config import get_system_config

        config = await get_system_config()
        slas = config.dashboard_slas
        return {macro: int(getattr(slas, macro)) for macro in MACROS_COM_SLA}
    except Exception as exc:
        logger.warning(
            "[STATS-SLA] Falha a ler os limiares (%s); a resposta vai sem eles.",
            exc,
        )
        return {}


async def run_get_sla(user: dict) -> dict[str, Any]:
    """GET /api/stats/sla — gargalos por macro-fase."""
    from models.permissions import resolve_capability

    if not resolve_capability(user, "STATS_VIEW"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403, detail="Sem permissão para ver estatísticas",
        )

    ambito = await resolver_ambito(user)
    cache_key = ambito.chave("stats:sla:v1")
    cached = await cache_get(cache_key)
    if cached:
        return cached

    ponte = await construir_ponte(ambito)
    limiares = await _limiares()

    presos: dict[str, list[dict]] = {}
    historico: dict[str, Any] = {}

    pipeline_presos = construir_pipeline_de_presos(ambito, ponte)
    if pipeline_presos:
        try:
            saida = await db.processes.aggregate(
                pipeline_presos, allowDiskUse=True,
            ).to_list(1)
            presos = saida[0] if saida else {}
        except Exception as exc:
            logger.error("[STATS-SLA] Erro no histograma: %s", exc)

    try:
        saida = await db.processes.aggregate(
            construir_pipeline_de_historico(ambito), allowDiskUse=True,
        ).to_list(1)
        historico = saida[0] if saida else {}
    except Exception as exc:
        logger.error("[STATS-SLA] Erro no acumulado: %s", exc)

    resultado = {
        "macro_fases": montar_sla(presos, historico, limiares),
        "bandas": list(ETIQUETAS_DAS_BANDAS),
        "excluidos_da_amostra": list(QUALIDADES_ABERRANTES),
    }
    await cache_set(cache_key, resultado, ttl=TTL_DA_CACHE)
    return resultado
