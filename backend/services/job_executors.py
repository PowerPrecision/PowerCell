"""
====================================================================
O QUE SIGNIFICA «CORRER» CADA JOB — UM REGISTO ÚNICO
====================================================================
Lote 2, ponto 1 (botões de acção no painel «Estado do Motor»).

O PROBLEMA QUE ISTO RESOLVE
  Executar um job à mão tem de ser EXACTAMENTE o que o laço faz, senão
  o botão prova uma coisa e o horário faz outra — e o diagnóstico passa
  a depender de qual dos dois correu. Era essa a armadilha de escrever
  o disparo manual dentro do endpoint: uma segunda definição de "correr
  o job", a divergir da primeira sem dar erro. Já vimos esta forma nos
  campos de atribuição, nos papéis e nas chaves de cache.

  Aqui o registo é um só, e tanto o laço como o botão passam por ele.

PORQUE É QUE HÁ DOIS CAMINHOS, E NÃO UM
  O motor vive em DOIS processos do `render.yaml` (web e worker) e um
  não pode chamar funções do outro. Logo:

    · job do processo **web** → o endpoint corre-o ali mesmo, porque o
      pedido está a ser servido pelo próprio processo que o alberga;
    · job do processo **worker** → o endpoint deixa um PEDIDO, e o
      `scheduler_loop` reclama-o no ciclo seguinte (até 60s).

  A resposta diz qual dos dois aconteceu, porque "a correr" e "pedido
  entregue" são estados diferentes e misturá-los seria mentir ao
  utilizador. É por isto que o painel era `read_only` até agora: a
  objecção registada na docstring do `automation_api_engine` ("um
  disparo manual a partir da web não chegaria ao processo worker") está
  certa — a fila é a resposta a ela, não a sua negação.

E O PEDIDO QUE FICA PENDENTE É O DIAGNÓSTICO
  Se o Processador estiver mesmo em baixo, o pedido fica em `pendente` e
  o painel diz-o. Deixa de ser preciso adivinhar entre "o job falhou" e
  "o processo não está lá": um pedido que ninguém reclama **prova** que
  ninguém está a ouvir. É a mesma razão por que o `JOBS_DECLARADOS`
  existe — o job mais avariado de todos é o que nunca arrancou, e tem de
  ser o mais visível.

UM JOB DESLIGADO NÃO SE FORÇA
  Em dev quase tudo está desligado por kill switch (protecção de RAM, e
  a regra de nunca tocar em serviços de email reais fora de produção).
  O executor recusa um job que `job_esta_activo` dê como desactivado —
  uma guarda única em vez de um `if` por job, que é como se esquece um.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

PROCESSO_WEB = "web"
PROCESSO_WORKER = "worker"


# ────────────────────────────────────────────────────────────────────
# Os executores. Cada um é o MESMO trabalho que o laço respectivo faz —
# os imports são tardios porque este módulo é lido pelo endpoint e não
# tem de arrastar a máquina de email, de backup e de IA para o arranque.
# ────────────────────────────────────────────────────────────────────

async def _executar_monitor_de_jobs() -> None:
    from services.background_job_sweep import varrer_jobs_bloqueados

    await varrer_jobs_bloqueados()


async def _executar_auto_sync_de_email() -> None:
    from services.scheduled_tasks import ScheduledTasksService

    servico = ScheduledTasksService()
    try:
        await servico.connect()
        await servico.auto_sync_emails()
    finally:
        await servico.disconnect()


async def _executar_backup() -> None:
    # `scheduled_backup_job` e NÃO `backup_service.create_backup`: é o que
    # o laço do agendador corre, e é o que tem de ser forçado. Chamar o
    # construtor directo saltava o que o job faz à volta dele.
    from services.backup import scheduled_backup_job

    await scheduled_backup_job()


async def _executar_cdc() -> None:
    # O CDC é um listener de change streams, não um ciclo com começo e
    # fim: "forçar" significa verificar que o listener está de pé. Não há
    # trabalho a repetir, e inventar um seria pior do que recusar.
    raise NotImplementedError(
        "O trilho de auditoria (CDC) é um listener contínuo — não tem ciclo "
        "para forçar. O estado do painel já diz se está de pé."
    )


async def _executar_tarefas_agendadas() -> None:
    from services.scheduled_tasks import ScheduledTasksService

    await ScheduledTasksService().run_all_tasks()


async def _executar_matching_de_leads() -> None:
    from services.client_match import match_leads_to_clients

    await match_leads_to_clients()


async def _executar_sync_de_webmail_do_worker() -> None:
    from services.webmail_worker_sync import run_webmail_worker_sync

    await run_webmail_worker_sync()


EXECUTORES: dict[str, Callable[[], Awaitable[Any]]] = {
    "background_job_monitor": _executar_monitor_de_jobs,
    "email_auto_sync": _executar_auto_sync_de_email,
    "backup_diario": _executar_backup,
    "cdc_audit": _executar_cdc,
    "scheduled_tasks": _executar_tarefas_agendadas,
    "lead_matching": _executar_matching_de_leads,
    "webmail_worker_sync": _executar_sync_de_webmail_do_worker,
}

# Jobs que existem no painel mas não se forçam, com o motivo À VISTA. Um
# botão desactivado sem explicação manda o utilizador clicar outra vez.
SEM_EXECUCAO_MANUAL: dict[str, str] = {
    "cdc_audit": (
        "O trilho de auditoria é um listener contínuo de change streams — "
        "não tem um ciclo para repetir."
    ),
}


def pode_ser_forcado(chave: str) -> bool:
    return chave in EXECUTORES and chave not in SEM_EXECUCAO_MANUAL


def motivo_para_nao_forcar(chave: str) -> str:
    return SEM_EXECUCAO_MANUAL.get(chave, "")


async def executar_job(chave: str) -> None:
    """Corre o job. O batimento embrulha o trabalho, como no laço.

    Levanta o que o job levantar — o batimento precisa de ver a excepção
    para registar `erro`, e quem chama precisa de a reportar.
    """
    from services.job_heartbeat import JOBS_POR_CHAVE, heartbeat, job_esta_activo

    executor = EXECUTORES.get(chave)
    if executor is None:
        raise KeyError(f"Job desconhecido: {chave}")

    declarado = JOBS_POR_CHAVE.get(chave) or {}
    if not job_esta_activo(declarado):
        # Uma guarda única, e não um `if` dentro de cada executor: é assim
        # que se esquece um, e o que se esquece aqui toca em serviços reais.
        raise PermissionError(
            f"O job '{chave}' está desactivado neste ambiente — não é forçável."
        )

    intervalo = declarado.get("interval_seconds") or 0
    logger.info("[MOTOR] Execução forçada do job %s", chave)
    async with heartbeat(chave, interval_seconds=intervalo):
        await executor()
