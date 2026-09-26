"""
====================================================================
FUNIL POR MACRO-FASE — GET /api/stats/funil
====================================================================
Refinamento Analítico e SLAs (Dashboard), Camada 2.

O QUE SUBSTITUI
  O `StatisticsPage` fazia `getProcesses()` sem filtro, trazia os 12.450
  processos para o browser e contava em JavaScript — com listas de nomes
  de fases cravadas (`['concluidos', 'desistencias']`) e agrupando pelo
  valor CRU de `status`. Os 205 processos em `cpcv`/`escriturado` e as 12
  gralhas apareciam como barras próprias: o quadro resolvia-os para a
  coluna certa e o gráfico não. Duas verdades sobre os mesmos dados.

  Aqui a agregação corre no servidor, sobre um `$match` indexado, e devolve
  números. A ponte com o motor (`stats_macro_bridge`) garante que a barra
  de cada macro-fase conta o mesmo que a coluna do quadro.

A CONVERSÃO, E O QUE ELA ASSUME
  `alcancaram(etapa)` soma os processos que estão nessa etapa OU numa
  posterior — o funil é monótono: um processo em `aprovado` passou
  necessariamente por `analise`.

  `perdido` fica FORA desta soma de propósito: um processo perde-se de
  qualquer etapa e não se sabe de qual. Contá-lo em `alcancaram(novo)`
  inflacionava o denominador da primeira conversão e fazia a taxa parecer
  pior do que é; contá-lo nas etapas seguintes seria pior ainda, porque
  atribuía a cada uma uma passagem que pode não ter existido. Vai à parte,
  com o seu número à vista.

  Quando o relógio tiver história (`tempos_macro` preenchido por
  transições REAIS), esta soma pode ser substituída por "passou mesmo por
  aqui". Hoje, no dia do arranque, `tempos_macro` está vazio em toda a
  parte e a substituição não acrescentava informação nenhuma — apenas
  complexidade.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db
from services.redis_cache import cache_get, cache_set
from services.stats_macro_bridge import (
    ORDEM_DO_FUNIL,
    PonteDeMacros,
    construir_ponte,
)
from services.stats_scope import AmbitoEstatistico, com_ambito, resolver_ambito
from services.workflow_phases import (
    ETIQUETA_DESCONHECIDA,
    FASE_DESCONHECIDA,
    carregar_fases,
    macro_da_fase,
)

logger = logging.getLogger(__name__)

TTL_DA_CACHE = 900  # 15 min: o funil é uma vista de gestão, não um sino.

#: Prioridades canónicas (`process_update.VALID_PRIORIDADES`). A chave
#: `sem` não é um valor gravado: é a ausência do campo.
PRIORIDADES: tuple[str, ...] = ("alta", "media", "baixa")
SEM_PRIORIDADE = "sem"

ETIQUETAS: dict[str, str] = {
    "novo": "Novo",
    "analise": "Análise",
    "aprovado": "Aprovado",
    "concluido": "Concluído",
    "perdido": "Perdido",
    FASE_DESCONHECIDA: ETIQUETA_DESCONHECIDA,
}


def construir_correspondencia(
    ambito: AmbitoEstatistico,
    consultor_id: Optional[str] = None,
) -> dict:
    """O `$match` partilhado pelas duas agregações do funil. PURO.

    O filtro por consultor usa a condição CANÓNICA
    (`build_assigned_to_me_condition`), que cobre os dezasseis campos de
    atribuição — canónicos e legados. A página fazia isto no cliente sobre
    `p.assigned_consultor`, um campo que não existe nos processos: escolher
    um utilizador esvaziava todos os gráficos sem dar erro.
    """
    filtro: dict = {"is_deleted": {"$ne": True}}
    if consultor_id and str(consultor_id).strip() not in ("", "all"):
        from services.process_list_filters import build_assigned_to_me_condition

        # `$and` e não uma chave nova: a condição de atribuição é um `$or`
        # e fundir dicionários apagava um dos dois.
        return {"$and": [
            com_ambito(filtro, ambito),
            build_assigned_to_me_condition(str(consultor_id).strip()),
        ]}
    return com_ambito(filtro, ambito)


def construir_pipeline(
    ambito: AmbitoEstatistico,
    ponte: PonteDeMacros,
    consultor_id: Optional[str] = None,
) -> list[dict]:
    """O pipeline do funil. PURO — testável sem Mongo.

    O `$match` é o PRIMEIRO estágio, com a fronteira de rede lá dentro: um
    `$match` depois do `$group` já teria somado os processos da outra rede.
    """
    return [
        {"$match": construir_correspondencia(ambito, consultor_id)},
        {
            "$project": {
                "macro": ponte.expressao(),
                "valor_imovel": {"$ifNull": ["$property_value", 0]},
                "valor_financiado": {
                    "$ifNull": ["$credit_data.requested_amount", 0],
                },
            }
        },
        {
            "$group": {
                "_id": "$macro",
                "processos": {"$sum": 1},
                "valor_imovel": {"$sum": "$valor_imovel"},
                "valor_financiado": {"$sum": "$valor_financiado"},
            }
        },
    ]


def construir_pipeline_de_prioridade(
    ambito: AmbitoEstatistico,
    consultor_id: Optional[str] = None,
) -> list[dict]:
    """Contagem por prioridade. PURO.

    Uma segunda agregação e não uma `$facet`: são duas perguntas
    independentes sobre o mesmo `$match`, as duas são `$group` simples, e
    duas agregações leem-se — uma `$facet` com duas ramificações lê-se
    muito pior por nenhuma vantagem.

    O campo canónico é `prioridade` com valores PORTUGUESES
    (`baixa`/`media`/`alta`, ver `process_update.VALID_PRIORIDADES`). A
    página contava `p.priority === 'high'` — outro campo, outros valores:
    o gráfico de prioridades mostrava zero desde sempre.
    """
    # O `$ifNull` vive num `$project` e não na chave do `$group`: uma
    # expressão como `_id` é válida no Mongo mas ilegível, e um `$project`
    # explícito diz o que se está a normalizar.
    return [
        {"$match": construir_correspondencia(ambito, consultor_id)},
        {
            "$project": {
                "prioridade": {"$ifNull": ["$prioridade", SEM_PRIORIDADE]},
            }
        },
        {"$group": {"_id": "$prioridade", "processos": {"$sum": 1}}},
    ]


def montar_prioridades(linhas: list[dict]) -> dict[str, int]:
    """`{alta, media, baixa, sem}`. PURA.

    Um valor que não esteja no conjunto canónico entra em `sem`: não se
    inventa uma fatia nova para uma gralha de dados legados.
    """
    contagens = {p: 0 for p in (*PRIORIDADES, SEM_PRIORIDADE)}
    for linha in linhas:
        chave = str(linha.get("_id") or SEM_PRIORIDADE)
        if chave not in PRIORIDADES:
            chave = SEM_PRIORIDADE
        contagens[chave] += int(linha.get("processos") or 0)
    return contagens


def montar_funil(linhas: list[dict]) -> dict[str, Any]:
    """Traduz o resultado do `$group` no funil ordenado. PURA.

    A soma das etapas mais o `perdido` mais a reconciliação é SEMPRE o
    total — é o invariante que impede um processo de desaparecer do
    relatório por não caber em nenhuma etapa.
    """
    por_macro = {
        str(linha.get("_id") or FASE_DESCONHECIDA): {
            "processos": int(linha.get("processos") or 0),
            "valor_imovel": round(float(linha.get("valor_imovel") or 0), 2),
            "valor_financiado": round(float(linha.get("valor_financiado") or 0), 2),
        }
        for linha in linhas
    }

    def dados(macro: str) -> dict:
        return por_macro.get(macro) or {
            "processos": 0, "valor_imovel": 0.0, "valor_financiado": 0.0,
        }

    etapas: list[dict[str, Any]] = []
    for indice, macro in enumerate(ORDEM_DO_FUNIL):
        d = dados(macro)
        # Monótono: quem está numa etapa posterior passou por esta.
        alcancaram = sum(
            dados(posterior)["processos"]
            for posterior in ORDEM_DO_FUNIL[indice:]
        )
        etapas.append({
            "macro_fase": macro,
            "label": ETIQUETAS.get(macro, macro),
            "processos": d["processos"],
            "alcancaram": alcancaram,
            "valor_imovel": d["valor_imovel"],
            "valor_financiado": d["valor_financiado"],
        })

    # Conversão entre etapas consecutivas, sobre os que ALCANÇARAM.
    for indice, etapa in enumerate(etapas):
        if indice + 1 >= len(etapas):
            etapa["conversao_para_seguinte"] = None
            continue
        origem = etapa["alcancaram"]
        destino = etapas[indice + 1]["alcancaram"]
        etapa["conversao_para_seguinte"] = (
            round(destino / origem * 100, 1) if origem else None
        )

    perdidos = dados("perdido")
    desconhecidos = dados(FASE_DESCONHECIDA)
    total = (
        sum(e["processos"] for e in etapas)
        + perdidos["processos"]
        + desconhecidos["processos"]
    )

    return {
        "etapas": etapas,
        "perdidos": {
            "macro_fase": "perdido",
            "label": ETIQUETAS["perdido"],
            **perdidos,
        },
        "desconhecidos": {
            "macro_fase": FASE_DESCONHECIDA,
            "label": ETIQUETAS[FASE_DESCONHECIDA],
            **desconhecidos,
        },
        "total_processos": total,
        "taxa_de_conclusao": (
            round(dados("concluido")["processos"] / total * 100, 1)
            if total else None
        ),
    }


async def run_get_funnel(
    user: dict,
    consultor_id: Optional[str] = None,
) -> dict[str, Any]:
    """GET /api/stats/funil — contagens e conversão por macro-fase."""
    from models.permissions import resolve_capability

    if not resolve_capability(user, "STATS_VIEW"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403, detail="Sem permissão para ver estatísticas",
        )

    ambito = await resolver_ambito(user)
    # O consultor entra na CHAVE: sem isso, o primeiro pedido filtrado
    # servia os números de uma pessoa a toda a gente durante 15 minutos.
    sufixo_do_filtro = f":c={consultor_id}" if consultor_id else ""
    cache_key = ambito.chave("stats:funil:v1") + sufixo_do_filtro
    cached = await cache_get(cache_key)
    if cached:
        return cached

    ponte = await construir_ponte(ambito)
    pipeline = construir_pipeline(ambito, ponte, consultor_id)

    try:
        linhas = await db.processes.aggregate(pipeline, allowDiskUse=True).to_list(50)
    except Exception as exc:
        logger.error("[STATS-FUNIL] Erro na agregação: %s", exc)
        # Degradação: um funil vazio, nunca um 500 no Dashboard inteiro.
        return {
            "etapas": [], "perdidos": None, "desconhecidos": None,
            "total_processos": 0, "taxa_de_conclusao": None,
            "macro_fases_sem_classificacao": [],
            "por_prioridade": montar_prioridades([]),
        }

    resultado = montar_funil(linhas)

    try:
        prioridades = await db.processes.aggregate(
            construir_pipeline_de_prioridade(ambito, consultor_id),
            allowDiskUse=True,
        ).to_list(20)
        resultado["por_prioridade"] = montar_prioridades(prioridades)
    except Exception as exc:
        logger.error("[STATS-FUNIL] Erro na contagem por prioridade: %s", exc)
        resultado["por_prioridade"] = montar_prioridades([])

    # As fases que o administrador ainda não classificou. Vão na resposta
    # para a UI o poder DIZER, em vez de o utilizador descobrir que a soma
    # das barras não dá o total.
    try:
        fases = await carregar_fases()
        resultado["macro_fases_sem_classificacao"] = sorted(
            f.get("name") for f in fases
            if isinstance(f, dict) and f.get("name") and not macro_da_fase(f)
        )
    except Exception:
        resultado["macro_fases_sem_classificacao"] = []

    await cache_set(cache_key, resultado, ttl=TTL_DA_CACHE)
    return resultado
