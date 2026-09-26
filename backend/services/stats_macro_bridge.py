"""
====================================================================
A PONTE ENTRE O `status` GRAVADO E A MACRO-FASE — para agregações
====================================================================
Refinamento Analítico e SLAs (Dashboard), Camada 2.

O PROBLEMA
  A `macro_fase` vive nos 14 documentos de `workflow_statuses`; o `status`
  vive nos 12.450 processos. Para agrupar por macro-fase numa agregação
  falta a ponte, e as duas formas óbvias são ambas más:

  1. `$lookup` por processo — doze mil junções para ler uma colecção de
     catorze documentos.
  2. Reimplementar a resolução (`cpcv`, `escriturado`, `"Concluidos "`) em
     expressões `$switch` de Mongo. Seria uma SEGUNDA implementação do
     `resolver_nome`, e as duas divergiam no primeiro alias novo. Passámos
     o Épico 10 inteiro a fechar exactamente esse género de divergência.

A SOLUÇÃO
  Um `$distinct` sobre `status` (campo indexado por `idx_status`) devolve
  as dezenas de valores que existem mesmo. Esses valores passam pelo
  resolvedor REAL — o mesmo que o quadro usa — e o resultado é um mapa
  explícito `valor gravado → macro-fase`, que se traduz num `$switch` com
  listas literais.

  Uma consulta indexada barata, a regra de resolução num só sítio, e os
  205 processos em `cpcv`/`escriturado` mais as 12 gralhas a contar na
  macro-fase certa — a mesma coluna que o quadro lhes desenha.

PORQUE O `$distinct` LEVA O ÂMBITO DE REDE
  Se não levasse, a ponte revelava que valores de `status` existem noutra
  rede. É um detalhe pequeno — nomes de fases, não dados de cliente — mas
  a fronteira aplica-se a tudo o que atravessa a agregação, e um `$switch`
  com um ramo a mais também custa.
====================================================================
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from database import db
from services.process_phase_clock import MACROS_SEM_PERMANENCIA
from services.stats_scope import AmbitoEstatistico, com_ambito
from services.workflow_phases import (
    FASE_DESCONHECIDA,
    MACRO_FASES_VALIDAS,
    carregar_fases,
    macro_da_fase,
    resolver_muitos,
)

logger = logging.getLogger(__name__)

#: A ordem do funil. É a ordem do produto, não a alfabética nem a do
#: enum: `perdido` fica FORA do caminho (um processo perde-se de qualquer
#: etapa) e por isso não entra nas conversões entre etapas consecutivas.
ORDEM_DO_FUNIL: tuple[str, ...] = ("novo", "analise", "aprovado", "concluido")

#: Macro-fases onde a permanência mede eficiência. Derivada, não escrita:
#: `MACROS_SEM_PERMANENCIA` é a lista canónica e vive no relógio.
MACROS_COM_SLA: tuple[str, ...] = tuple(
    m for m in MACRO_FASES_VALIDAS if m not in MACROS_SEM_PERMANENCIA
)


@dataclass(frozen=True)
class PonteDeMacros:
    """`valor de status gravado → macro-fase`, resolvido pelo motor."""

    mapa: dict[str, Optional[str]]

    def valores_de(self, *macros: str) -> list[str]:
        """Os valores GRAVADOS que pertencem a estas macro-fases.

        Inclui os aliases e as gralhas — é isso que o distingue do
        `nomes_por_macro`, que só devolve nomes que o motor conhece.
        """
        pedidas = set(macros)
        return sorted(
            valor for valor, macro in self.mapa.items()
            if valor and macro in pedidas
        )

    def expressao(self) -> dict[str, Any]:
        """Expressão de agregação que devolve a macro-fase de um documento.

        `default` é a coluna de reconciliação: um valor que o motor não
        conhece NUNCA é somado a um grupo onde não está. Foi essa a
        política aprovada no Épico 10 — não esconder os problemas varrendo
        para baixo do tapete.
        """
        ramos = []
        for macro in MACRO_FASES_VALIDAS:
            valores = self.valores_de(macro)
            if valores:
                ramos.append({
                    "case": {"$in": ["$status", valores]},
                    "then": macro,
                })
        if not ramos:
            # Sem ramos, um `$switch` é inválido no Mongo. Tudo cai na
            # reconciliação, que é a verdade: nenhum valor se resolve.
            return {"$literal": FASE_DESCONHECIDA}
        return {"$switch": {"branches": ramos, "default": FASE_DESCONHECIDA}}

    @property
    def macros_presentes(self) -> list[str]:
        """As macro-fases que têm mesmo valores gravados, pela ordem do funil."""
        presentes = {m for m in self.mapa.values() if m}
        return [m for m in MACRO_FASES_VALIDAS if m in presentes]


async def construir_ponte(ambito: AmbitoEstatistico) -> PonteDeMacros:
    """A ponte para o âmbito de quem pede. Uma consulta indexada + o motor.

    Nunca levanta: sem fases ou sem valores, devolve uma ponte vazia, cuja
    expressão manda tudo para a reconciliação. Um dashboard que rebenta
    porque a colecção de fases está vazia é pior do que um dashboard que
    diz "nada classificado".
    """
    try:
        fases = await carregar_fases()
    except Exception as exc:
        logger.warning("[STATS-PONTE] Falha a ler as fases (%s).", exc)
        fases = []

    try:
        valores = await db.processes.distinct(
            "status", com_ambito({"is_deleted": {"$ne": True}}, ambito),
        )
    except Exception as exc:
        logger.warning("[STATS-PONTE] Falha a ler os valores de status (%s).", exc)
        valores = []

    por_nome = {
        f.get("name"): f for f in fases
        if isinstance(f, dict) and f.get("name")
    }
    resolucoes = resolver_muitos(valores, fases)

    mapa: dict[str, Optional[str]] = {}
    for valor, resolucao in resolucoes.items():
        fase = por_nome.get(resolucao.fase) if resolucao.resolvida else None
        mapa[valor] = macro_da_fase(fase) if fase else None

    return PonteDeMacros(mapa=mapa)
