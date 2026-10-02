"""
====================================================================
QUANDO É QUE O RELATÓRIO SEMANAL SAI — A AGENDA, EM CÓDIGO
====================================================================
Lote 2, ponto 1 (fecho da D-7).

A DOCSTRING DIZIA UMA COISA E O CÓDIGO FAZIA OUTRA
  O `send_weekly_ceo_report` abria com:

      «Corre todas as Segundas-feiras às ~06:00 (quando run_all_tasks é
       invocado pelo worker/scheduler).»

  Nada no código implementava isso. A guarda inteira era:

      if today.weekday() != 0:
          return False

  E o `run_all_tasks` corre de HORA A HORA. Consequências, as duas
  invisíveis sem ler o código:

  1. **Não havia hora nenhuma.** O relatório saía à hora em que o ciclo
     horário calhasse — isto é, à hora a que o Processador tivesse
     arrancado. Um deploy às 14h punha o relatório semanal a sair às
     14h, para sempre, e a docstring continuava a prometer 06:00.

  2. **Saía 24 VEZES.** `weekday() == 0` é verdade durante as 24 horas da
     segunda-feira, e não havia marca de "já enviei esta semana". Cada
     ciclo horário gerava e enviava o relatório outra vez. O
     `send_weekly_ai_report` tem a mesma forma (`current_weekday ==
     send_day`) e o mesmo resultado.

  Um horário escrito só numa docstring não é um horário — é uma
  intenção. É a forma do defeito que este projecto já viu nas cascatas
  de `||` sobre campos inexistentes: a descrição e o comportamento
  divergem, e quem lê acredita na descrição.

PORQUE É QUE A MARCA TEM DE SER PERSISTIDA
  O `last_runs` do `scheduler_loop` é um dicionário local a uma função:
  morre em cada reinício. Com a marca em memória, um reinício numa
  segunda-feira às 10h mandava o relatório outra vez — e o Render
  reinicia por deploy, por OOM e por manutenção. A marca vive em
  `db.job_schedule_marks`, que é a mesma razão por que o batimento dos
  jobs vive numa colecção e não no processo.

A SEMANA É A SEMANA ISO
  A chave é `(ano, semana ISO)`, não "há mais de 7 dias": "há 7 dias"
  faz o relatório deslizar de dia a cada envio até sair à quarta-feira.
  Uma semana do calendário é uma semana do calendário.

O ÂMBITO É CONSOLIDADO, E É UMA DECISÃO (D-7)
  `generate_weekly_team_report` sem `user` atravessa todas as redes. Isso
  era dívida registada (D-7) à espera de decisão; a decisão tomada é que
  a Direcção quer o consolidado. Fica aqui dito para não voltar a ser
  lido como esquecimento, porque é a ÚNICA excepção deliberada ao
  isolamento por rede do Lote 4/5 — e, por isso, os destinatários têm de
  ser gente credenciada nas três empresas.
====================================================================
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from database import db

logger = logging.getLogger(__name__)

COLECCAO = "job_schedule_marks"

# Segunda-feira. `datetime.weekday()` conta de 0 (segunda) a 6 (domingo).
SEGUNDA_FEIRA = 0

# Hora a partir da qual o relatório pode sair, em UTC. "A partir de" e não
# "às": o ciclo é horário, logo a hora exacta não é garantível — o que é
# garantível é não sair ANTES. Uma condição de igualdade (`hora == 6`)
# perdia a semana inteira se o ciclo das 06h falhasse ou o processo
# estivesse a reiniciar nesse minuto.
HORA_MINIMA_UTC = 6


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def etiqueta_da_semana(momento: datetime) -> str:
    """`2026-W40` — ano e semana ISO.

    A semana ISO, e não "há mais de 7 dias": a segunda forma faz o envio
    deslizar de dia a cada semana até o relatório sair à quarta.
    """
    ano, semana, _ = momento.isocalendar()
    return f"{ano}-W{semana:02d}"


def etiqueta_do_periodo(frequencia: str, momento: datetime) -> str:
    """A etiqueta do período, pela periodicidade configurada.

    O relatório de IA é configurável (diário / semanal / mensal) pelo
    painel de administração e tem a MESMA falha de origem: uma condição
    `weekday == send_day` que é verdade durante 24 ciclos horários. Mas
    "uma vez" significa coisas diferentes em cada periodicidade, e usar a
    etiqueta semanal num relatório diário fazia-o sair uma vez por semana
    — trocar 24 emails a mais por 6 a menos não é uma correcção.
    """
    normalizada = (frequencia or "weekly").strip().lower()
    if normalizada == "daily":
        return momento.strftime("%Y-%m-%d")
    if normalizada == "monthly":
        return momento.strftime("%Y-%m")
    return etiqueta_da_semana(momento)


async def ja_enviado_no_periodo(
    chave: str,
    frequencia: str,
    momento: Optional[datetime] = None,
) -> bool:
    """Como `ja_enviado_esta_semana`, mas para a periodicidade dada."""
    agora = momento or _agora()
    etiqueta = etiqueta_do_periodo(frequencia, agora)
    try:
        marca = await db[COLECCAO].find_one({"chave": chave}, {"_id": 0, "semana": 1})
    except Exception as e:
        logger.warning("[AGENDA] Falha a ler a marca de %s: %s", chave, e)
        return True
    return bool(marca) and marca.get("semana") == etiqueta


async def marcar_enviado_no_periodo(
    chave: str,
    frequencia: str,
    momento: Optional[datetime] = None,
) -> None:
    agora = momento or _agora()
    try:
        await db[COLECCAO].update_one(
            {"chave": chave},
            {"$set": {
                "chave": chave,
                "semana": etiqueta_do_periodo(frequencia, agora),
                "frequencia": (frequencia or "weekly").strip().lower(),
                "enviado_em": agora.isoformat(),
            }},
            upsert=True,
        )
    except Exception as e:
        logger.warning("[AGENDA] Falha a marcar %s como enviado: %s", chave, e)


def esta_na_janela(momento: Optional[datetime] = None) -> bool:
    """É segunda-feira e já passou a hora mínima?"""
    agora = momento or _agora()
    return agora.weekday() == SEGUNDA_FEIRA and agora.hour >= HORA_MINIMA_UTC


async def ja_enviado_esta_semana(chave: str, momento: Optional[datetime] = None) -> bool:
    """A marca persistida. Em caso de dúvida de leitura, diz que JÁ enviou.

    Falha fechada de propósito: com a base inacessível, o custo de não
    enviar é um relatório em atraso que se nota; o custo de enviar é um
    ciclo horário a mandar 24 emails ao CEO, que é como se ensina alguém
    a ignorar o relatório.
    """
    semana = etiqueta_da_semana(momento or _agora())
    try:
        marca = await db[COLECCAO].find_one({"chave": chave}, {"_id": 0, "semana": 1})
    except Exception as e:
        logger.warning("[AGENDA] Falha a ler a marca de %s: %s", chave, e)
        return True
    return bool(marca) and marca.get("semana") == semana


async def marcar_enviado(chave: str, momento: Optional[datetime] = None) -> None:
    """Grava que esta semana já saiu."""
    agora = momento or _agora()
    try:
        await db[COLECCAO].update_one(
            {"chave": chave},
            {"$set": {
                "chave": chave,
                "semana": etiqueta_da_semana(agora),
                "enviado_em": agora.isoformat(),
            }},
            upsert=True,
        )
    except Exception as e:
        # Não propaga: o email já saiu, e levantar aqui faria o chamador
        # tratar um envio bem-sucedido como falha. O preço de uma falha
        # de escrita é um email repetido no ciclo seguinte.
        logger.warning("[AGENDA] Falha a marcar %s como enviado: %s", chave, e)


async def deve_enviar_relatorio_semanal(
    chave: str,
    *,
    momento: Optional[datetime] = None,
    forcado: bool = False,
) -> bool:
    """A pergunta completa: está na janela E ainda não saiu esta semana?

    `forcado=True` salta a janela mas **não** a marca da semana — é o que
    o botão «Forçar Execução» precisa (correr fora de segunda-feira) sem
    abrir a porta a 24 emails.
    """
    agora = momento or _agora()
    if not forcado and not esta_na_janela(agora):
        return False
    if await ja_enviado_esta_semana(chave, agora):
        logger.info("[AGENDA] %s já saiu em %s — a ignorar", chave, etiqueta_da_semana(agora))
        return False
    return True


def destinatarios_configurados() -> list[str]:
    """Os emails de `CEO_EMAIL`, separados por vírgula."""
    bruto = os.environ.get("CEO_EMAIL", "").strip()
    return [e.strip() for e in bruto.split(",") if e.strip()]
