"""
====================================================================
BATIMENTO DOS JOBS DE BACKGROUND (Monitor de Sinais Vitais)
====================================================================
Lote 4, ponto 14 — "Espelho de Automações".

PORQUE É QUE O ESTADO TEM DE SER PERSISTIDO
  O motor não é um agendador (não há APScheduler nem Celery): são laços
  `asyncio` à mão, repartidos por DOIS processos do `render.yaml`.

    processo web (`powercell`, UVICORN_WORKERS=2)
      · background_job_monitor  — 30 min, em TODOS os workers
      · backup / CDC / auto-sync IMAP — só produção E worker PRIMÁRIO

    processo worker (`powercell-worker`)
      · scheduler_loop → run_all_tasks (alertas) — 1 h
      · lead matching — 30 min
      · sync webmail (rede de segurança) — 10 min

  O `last_runs` do `worker.py` é um DICIONÁRIO LOCAL DE UMA FUNÇÃO:
  morre em cada reinício e a API nunca o vê. Do lado web, um pedido
  servido pelo worker secundário não sabe nada das tarefas do primário —
  e é o primário que tem o lock. Um endpoint que lesse o estado local
  responderia sobre o processo que calhou atender o pedido, e diria
  "IMAP em baixo" por desenho. Um monitor que mente com ar de autoridade
  é pior do que não ter monitor.

  Uma colecção partilhada é a única coisa que os dois processos vêem.

O QUE ISTO NÃO É
  Não é um histórico. Guarda-se o ÚLTIMO batimento por job mais os
  contadores acumulados — responde às quatro perguntas (vivo? falhou?
  quando correu? quando corre?) sem pôr uma colecção a crescer.

O BATIMENTO OBSERVA, NÃO INTERCEPTA
  A excepção do ciclo é registada e RE-LEVANTADA. Falhar a GRAVAR o
  batimento, esse sim, nunca propaga: um monitor que derruba o que
  monitoriza é pior do que nenhum (mesma regra do `publish_event` e da
  revogação do Portal).
====================================================================
"""
from __future__ import annotations

import logging
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import db
from services.email_sync_cadence import get_email_auto_sync_interval_seconds

logger = logging.getLogger(__name__)

COLECCAO = "job_heartbeats"

# Um ciclo perdido é ruído (concorrência, um micro bloqueio); dois é sinal.
FACTOR_DE_ATRASO = 2

ESTADO_SAUDAVEL = "saudavel"
ESTADO_ATRASADO = "atrasado"
ESTADO_FALHOU = "falhou"
ESTADO_DESACTIVADO = "desactivado"
ESTADO_NUNCA_CORREU = "nunca_correu"
ESTADO_A_CORRER = "a_correr"

# ────────────────────────────────────────────────────────────────────
# O REGISTO DECLARADO
#
# É a lista do que DEVIA estar a correr. Sem ela, o painel listaria só o
# que está na colecção — e o job mais avariado de todos, o que nunca
# arrancou, era o único invisível. Cada entrada tem de ter um emissor no
# código; há um teste a afirmá-lo nos dois sentidos.
# ────────────────────────────────────────────────────────────────────
JOBS_DECLARADOS: list[dict[str, Any]] = [
    {
        "chave": "background_job_monitor",
        "nome": "Monitor de tarefas bloqueadas",
        "descricao": "Marca como falhados os jobs sem actualização há mais de 2 horas.",
        "interval_seconds": 1800,
        "processo": "web",
        "so_em_producao": False,
    },
    {
        "chave": "email_auto_sync",
        "nome": "Sincronização de e-mail (IMAP)",
        "descricao": "Traz o correio novo das caixas configuradas e emite os avisos em tempo real.",
        # Derivado do mesmo sítio que o laço (`email_sync_cadence`): um
        # número escrito aqui à mão ficaria para trás no dia em que a
        # cadência mudasse, e o painel anunciaria um horário que já não é.
        "interval_seconds": get_email_auto_sync_interval_seconds(),
        "processo": "web",
        "so_em_producao": True,
    },
    {
        "chave": "backup_diario",
        "nome": "Cópia de segurança diária",
        "descricao": "Exporta a base de dados para o armazenamento, às 03:00 UTC.",
        "interval_seconds": 86400,
        "processo": "web",
        "so_em_producao": True,
    },
    {
        "chave": "cdc_audit",
        "nome": "Trilho de auditoria (CDC)",
        "descricao": "Regista as alterações à base de dados para efeitos de conformidade.",
        "interval_seconds": 300,
        "processo": "web",
        "so_em_producao": True,
    },
    {
        "chave": "scheduled_tasks",
        "nome": "Alertas e limpezas",
        "descricao": (
            "Prazos a vencer, documentos a expirar, tarefas por concluir, "
            "processos parados e limpeza de notificações antigas."
        ),
        "interval_seconds": 3600,
        "processo": "worker",
        "so_em_producao": True,
    },
    {
        "chave": "lead_matching",
        "nome": "Cruzamento automático de leads",
        "descricao": "Procura imóveis compatíveis com as leads em aberto.",
        "interval_seconds": 1800,
        "processo": "worker",
        "so_em_producao": True,
    },
    {
        "chave": "webmail_worker_sync",
        "nome": "Sincronização de e-mail (rede de segurança)",
        "descricao": "Segunda passagem, mais lenta, para o caso de o processo principal estar em baixo.",
        "interval_seconds": 600,
        "processo": "worker",
        "so_em_producao": True,
    },
]

JOBS_POR_CHAVE = {job["chave"]: job for job in JOBS_DECLARADOS}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _para_datetime(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def job_esta_activo(declarado: dict) -> bool:
    """O job está ligado neste ambiente, ou desligado por um kill switch?

    Esta distinção é a mais importante do painel: em dev quase tudo está
    desligado DE PROPÓSITO (kill switches por RAM), e um monitor a gritar
    vermelho em dev ensina toda a gente a ignorá-lo.
    """
    if "activo" in declarado:
        return bool(declarado["activo"])
    if not declarado.get("so_em_producao"):
        return True

    em_producao = os.environ.get("ENVIRONMENT") == "production"
    if em_producao:
        return True
    # O auto-sync de email tem um interruptor próprio para dev.
    if declarado.get("chave") in ("email_auto_sync", "webmail_worker_sync"):
        return os.environ.get("EMAIL_SYNC_ENABLED", "").lower() == "true"
    return False


def _intervalo_efectivo(declarado: dict, registo: Optional[dict]) -> int:
    """Segundos entre ciclos — o do BATIMENTO manda, o declarado é recurso.

    `JOBS_DECLARADOS` é a EXPECTATIVA (o que o painel mostra a um job que
    ainda não bateu); o batimento traz o `interval_seconds` que o laço usou
    de facto. Quando os dois discordam — porque alguém afinou
    `EMAIL_AUTO_SYNC_INTERVAL_SECONDS` no Render, ou porque a omissão do
    laço mudou antes da constante — é o laço que tem razão. Ler a constante
    punha o monitor a gritar `atrasado` a um job que está a cumprir o seu
    horário, e um monitor que mente com ar de autoridade é pior do que não
    ter monitor.
    """
    if registo:
        real = registo.get("interval_seconds")
        try:
            real = int(real or 0)
        except (TypeError, ValueError):
            real = 0
        if real > 0:
            return real
    try:
        return int(declarado.get("interval_seconds") or 0)
    except (TypeError, ValueError):
        return 0


def estado_do_job(
    declarado: dict,
    registo: Optional[dict],
    *,
    agora: Optional[datetime] = None,
) -> str:
    """Estado derivado de um job, para o painel."""
    if not job_esta_activo(declarado):
        # Desligar um job deixa o último batimento a envelhecer para
        # sempre; mostrá-lo como "atrasado" mentiria sobre a causa.
        return ESTADO_DESACTIVADO

    if not registo:
        return ESTADO_NUNCA_CORREU

    momento_agora = agora or _agora()
    fim = _para_datetime(registo.get("finished_at"))

    if not fim:
        # Ciclo em curso: o sync de IMAP pode demorar minutos e não pode
        # aparecer como atrasado enquanto está a trabalhar.
        inicio = _para_datetime(registo.get("started_at"))
        return ESTADO_A_CORRER if inicio else ESTADO_NUNCA_CORREU

    if registo.get("status") == "erro":
        # A falha vence o atraso: um job que bate a horas mas rebenta em
        # cada ciclo está pior do que um que se atrasou.
        return ESTADO_FALHOU

    intervalo = _intervalo_efectivo(declarado, registo)
    if intervalo > 0:
        limite = timedelta(seconds=intervalo * FACTOR_DE_ATRASO)
        if momento_agora - fim > limite:
            return ESTADO_ATRASADO

    return ESTADO_SAUDAVEL


def proxima_execucao(declarado: dict, registo: Optional[dict]) -> Optional[str]:
    """Quando o job volta a correr, ou ``None`` se não se sabe.

    Uma data inventada dá uma falsa sensação de normalidade a um job que
    nunca arrancou.
    """
    if not job_esta_activo(declarado) or not registo:
        return None
    fim = _para_datetime(registo.get("finished_at"))
    intervalo = _intervalo_efectivo(declarado, registo)
    if not fim or intervalo <= 0:
        return None
    return (fim + timedelta(seconds=intervalo)).isoformat()


@asynccontextmanager
async def heartbeat(chave: str, *, interval_seconds: Optional[int] = None):
    """Envelope de um ciclo de um job.

    Uso::

        async with heartbeat("email_auto_sync", interval_seconds=300):
            await fazer_o_trabalho()

    Emissores são pontos de estrangulamento, não código espalhado — a
    mesma decisão de `services/task_events.py`.
    """
    declarado = JOBS_POR_CHAVE.get(chave, {})
    intervalo = interval_seconds or declarado.get("interval_seconds") or 0
    inicio = _agora()

    await _marcar_inicio(chave, inicio, intervalo)
    try:
        yield
    except BaseException as exc:
        # Regista e RE-LEVANTA: o batimento observa, não intercepta.
        await _marcar_fim(chave, inicio, intervalo, erro=exc)
        raise
    else:
        await _marcar_fim(chave, inicio, intervalo, erro=None)


async def _marcar_inicio(chave: str, inicio: datetime, intervalo: int) -> None:
    await _gravar(
        chave,
        {
            "$set": {
                "chave": chave,
                "started_at": inicio.isoformat(),
                "finished_at": None,
                "status": ESTADO_A_CORRER,
                "interval_seconds": intervalo,
                "processo": os.environ.get("POWERCELL_PROCESS", "web"),
                "host": socket.gethostname(),
                "pid": os.getpid(),
            },
        },
    )


async def _marcar_fim(
    chave: str,
    inicio: datetime,
    intervalo: int,
    *,
    erro: Optional[BaseException],
) -> None:
    fim = _agora()
    actualizacao: dict[str, Any] = {
        "$set": {
            "chave": chave,
            "started_at": inicio.isoformat(),
            "finished_at": fim.isoformat(),
            "status": "erro" if erro else "ok",
            "error": f"{type(erro).__name__}: {erro}" if erro else None,
            "duration_ms": int((fim - inicio).total_seconds() * 1000),
            "interval_seconds": intervalo,
        },
        "$inc": {"run_count": 1, "failure_count": 1 if erro else 0},
    }
    await _gravar(chave, actualizacao)


async def _gravar(chave: str, actualizacao: dict) -> None:
    """Escreve o batimento. NUNCA propaga."""
    try:
        await db[COLECCAO].update_one({"chave": chave}, actualizacao, upsert=True)
    except Exception as exc:
        logger.warning("[BATIMENTO] Falha a registar o job %s: %s", chave, exc)


async def ler_batimentos() -> dict[str, dict]:
    """Último batimento de cada job, por chave. NUNCA levanta."""
    try:
        registos = await db[COLECCAO].find({}, {"_id": 0}).to_list(200)
    except Exception as exc:
        logger.warning("[BATIMENTO] Falha a ler os batimentos: %s", exc)
        return {}
    return {r.get("chave"): r for r in registos if r.get("chave")}
