"""
====================================================================
BACKFILL DO RELÓGIO DE FASES — semear a estimativa, com a verdade ao lado
====================================================================
Refinamento Analítico e SLAs (Dashboard), Camada 1.5.
Lógica PURA. Quem escreve é `scripts/semear_relogio_de_fases.py`.

O PROBLEMA
  O carimbo de transição só começa a contar no dia em que entrou. Os
  12.450 processos que já existem não têm relógio, e o melhor aproximado
  para a data de entrada na fase é o `updated_at` — que muda com qualquer
  escrita.

  A medição disse quão mau é: **3.105 nunca tocados** (a estimativa cai na
  data de criação e sobrestima) e **1.840 tocados depois de fechar**
  (subestima). Quase 5.000 aproximações falsas em 12.450.

PORQUE TRÊS NÍVEIS E NÃO UM BOOLEANO
  Um `estimado: true` cego obrigava o BI a escolher entre duas coisas
  igualmente más: ignorar 12.450 processos (e não ter história nenhuma) ou
  usá-los todos (e desenhar médias sobre 5.000 valores aberrantes).

  Com `fase_desde_qualidade` o BI ignora os aberrantes e aproveita os
  plausíveis. E os dois aberrantes erram para lados OPOSTOS — um
  sobrestima, o outro subestima —, pelo que não se anulam em média:
  juntá-los numa só classe perdia exactamente a informação que permite
  excluí-los.

O QUE SE ESCREVE
  `fase_desde`                  = `updated_at`
  `macro_fase_desde`            = `updated_at`
  `fase_desde_estimado`         = True
  `macro_fase_desde_estimado`   = True
  `fase_desde_qualidade`        = plausivel | nunca_tocado | tocado_apos_fecho

  As bandeiras são o que impede o acumulador de se contaminar: o relógio
  nunca soma segundos a partir de um carimbo estimado. A qualidade é para
  o BI DECIDIR O QUE MOSTRA — são coisas diferentes e por isso são campos
  diferentes.

IDEMPOTÊNCIA, E ONDE ELA VIVE
  A condição de ausência está na QUERY de cada escrita, não num `if` em
  Python: entre a leitura e a escrita pode ter havido uma transição real, e
  é ela que manda. Um processo que já tenha `fase_desde` NUNCA é tocado —
  correr isto duas vezes não desfaz uma medição.

A CLASSIFICAÇÃO É A MESMA DA MEDIÇÃO
  `phase_clock_coverage.classificar_estimativa`. Se o script que conta e o
  script que escreve classificassem à sua maneira, o relatório deixava de
  descrever os dados escritos — e a discrepância só aparecia meses depois,
  num gráfico. Há um teste a afirmar que as contagens do retrato são
  exactamente o que este módulo carimbaria.
====================================================================
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from services.phase_clock_coverage import (
    QUALIDADES,
    QUALIDADE_SEM_ESTIMATIVA,
    classificar_estimativa,
    instante,
)
from services.process_phase_clock import (
    CAMPO_FASE_DESDE,
    CAMPO_FASE_ESTIMADO,
    CAMPO_MACRO_DESDE,
    CAMPO_MACRO_ESTIMADO,
)

logger = logging.getLogger(__name__)

CAMPO_QUALIDADE = "fase_desde_qualidade"

#: O que o backfill precisa de ler. Sem `personal_data`: semear datas não
#: tem de tocar em dados de cliente.
PROJECCAO_DO_BACKFILL: dict = {
    "_id": 0,
    "id": 1,
    "status": 1,
    "created_at": 1,
    "updated_at": 1,
    CAMPO_FASE_DESDE: 1,
}


@dataclass
class Plano:
    """O que o backfill faria (ou fez). Contagens, nunca amostras de dados."""

    lidos: int = 0
    a_carimbar: int = 0
    ja_tinham_relogio: int = 0
    sem_estimativa: int = 0
    por_qualidade: dict[str, int] = field(
        default_factory=lambda: {nivel: 0 for nivel in QUALIDADES}
    )
    escritos: int = 0


def campos_do_backfill(linha: dict, qualidade: str) -> Optional[dict]:
    """Os campos `$set` de um processo legado, ou `None` se não houver o quê.

    `None` quando não há `updated_at` legível: semear o `created_at` no seu
    lugar seria inventar um terceiro nível de má qualidade sem o dizer.
    """
    if qualidade == QUALIDADE_SEM_ESTIMATIVA:
        return None

    tocado = instante(linha.get("updated_at"))
    if tocado is None:
        return None

    marca = tocado.isoformat()
    return {
        CAMPO_FASE_DESDE: marca,
        CAMPO_MACRO_DESDE: marca,
        CAMPO_FASE_ESTIMADO: True,
        CAMPO_MACRO_ESTIMADO: True,
        CAMPO_QUALIDADE: qualidade,
    }


def preparar(
    linhas: Iterable[dict],
    macro_por_valor: dict[str, Optional[str]],
    *,
    agora: datetime,
) -> tuple[list[tuple[str, dict]], Plano]:
    """Constrói o plano de escrita. PURA: não toca na base de dados.

    Devolve `[(process_id, campos_$set), …]` e as contagens. `agora` é
    injectado — uma classificação que dependa do relógio da máquina não se
    afirma num teste, e esta decide o que se escreve em 12.450 documentos.
    """
    plano = Plano()
    escritas: list[tuple[str, dict]] = []

    for linha in linhas:
        plano.lidos += 1

        # Já tem relógio REAL ou estimado de uma passagem anterior: não se
        # toca. A verificação repete-se na query da escrita — aqui é para
        # o relatório, lá é para a corrida.
        if linha.get(CAMPO_FASE_DESDE):
            plano.ja_tinham_relogio += 1
            continue

        macro = macro_por_valor.get(linha.get("status") or "")
        qualidade = classificar_estimativa(
            criado=instante(linha.get("created_at")),
            tocado=instante(linha.get("updated_at")),
            macro=macro,
            agora=agora,
        )
        plano.por_qualidade[qualidade] = plano.por_qualidade.get(qualidade, 0) + 1

        campos = campos_do_backfill(linha, qualidade)
        if campos is None:
            plano.sem_estimativa += 1
            continue

        identificador = str(linha.get("id") or "")
        if not identificador:
            # Um processo sem `id` não se consegue endereçar. Não se
            # inventa um filtro alternativo: uma escrita por `_id` aqui
            # saltava a condição de idempotência.
            logger.warning("[BACKFILL-RELOGIO] Processo sem `id`; ignorado.")
            continue

        escritas.append((identificador, campos))
        plano.a_carimbar += 1

    return escritas, plano


def formatar_plano(plano: Plano, *, aplicado: bool) -> str:
    """Relatório legível do que se fez (ou faria)."""
    linhas: list[str] = []
    ad = linhas.append

    ad("")
    ad("=" * 68)
    ad("BACKFILL DO RELÓGIO DE FASES — " + ("APLICADO" if aplicado else "SIMULAÇÃO"))
    ad("=" * 68)
    ad(f"  processos lidos              : {plano.lidos}")
    ad(f"  já tinham relógio (intactos) : {plano.ja_tinham_relogio}")
    ad(f"  a carimbar                   : {plano.a_carimbar}")
    ad(f"  sem `updated_at` utilizável  : {plano.sem_estimativa}")
    ad("")
    ad("  Qualidade da estimativa:")
    for nivel, quantos in plano.por_qualidade.items():
        ad(f"    {nivel:<22} {quantos}")
    ad("")
    ad("  Só o `plausivel` serve para médias no BI. Os outros dois erram")
    ad("  para lados OPOSTOS — um sobrestima, o outro subestima — pelo que")
    ad("  nem se anulam: ficam carimbados para os poder excluir.")
    if aplicado:
        ad("")
        ad(f"  documentos escritos          : {plano.escritos}")
    else:
        ad("")
        ad("  NADA foi escrito. Repita com `--aplicar`.")
    ad("=" * 68)
    return "\n".join(linhas)


def para_json(plano: Plano, *, aplicado: bool) -> dict[str, Any]:
    return {
        "aplicado": aplicado,
        "lidos": plano.lidos,
        "a_carimbar": plano.a_carimbar,
        "ja_tinham_relogio": plano.ja_tinham_relogio,
        "sem_estimativa": plano.sem_estimativa,
        "por_qualidade": plano.por_qualidade,
        "escritos": plano.escritos,
    }
