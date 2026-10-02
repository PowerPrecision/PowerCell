"""
====================================================================
WORKER - Processador de Tarefas Assíncronas
====================================================================
Refatorizado para usar LAZY LOADING nos módulos pesados.
Isto reduz significativamente o consumo de memória no arranque (idle).

Módulos carregados APENAS quando necessário:
- services.scraper (BeautifulSoup/Playwright -> Pesado)
- services.email_service (SMTP/API -> Médio)
- services.client_match (Pandas/Fuzzy -> MUITO PESADO)
====================================================================
"""
import os
import sys
import logging
import asyncio
import signal
import time
import tempfile
from datetime import datetime, timezone, timedelta

# Configurar logging (usar utils/logger.py para formato padronizado com Render)
from utils.logger import get_logger
logger = get_logger("worker")

# Adicionar caminho do backend ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ====================================================================
# IMPORTS ESSENCIAIS (Leves - carregados no arranque)
# ====================================================================
try:
    from database import db
    from services.task_queue import task_queue
except ImportError as e:
    logger.error(f"Erro ao importar módulos essenciais: {e}")
    sys.exit(1)

# ====================================================================
# NOTA: Os seguintes módulos NÃO são importados aqui (Lazy Loading):
# - services.scraper (scrape_property_url)
# - services.email_service (email_service)
# - services.client_match (match_leads_to_clients)
# - services.scheduled_tasks (ScheduledTasksService)
# ====================================================================

# Flag para paragem graciosa
shutdown_event = asyncio.Event()


def _jobs_do_processador() -> dict:
    """Os jobs deste processo e o intervalo de cada um, em segundos.

    DERIVADO de `job_heartbeat.JOBS_DECLARADOS` (Lote 2, ponto 1). Os
    números estavam escritos à mão aqui (3600/1800/600) **e** lá — duas
    cópias da mesma cadência, que divergem na primeira vez que alguém
    afinar uma delas, e aí o painel anuncia um horário que não é o que
    este laço cumpre. A ordem é a do registo declarado.
    """
    from services.job_heartbeat import JOBS_DECLARADOS

    return {
        job["chave"]: int(job.get("interval_seconds") or 0)
        for job in JOBS_DECLARADOS
        if job.get("processo") == "worker" and int(job.get("interval_seconds") or 0) > 0
    }


async def process_task(task: dict):
    """
    Processa uma tarefa individual da fila.
    
    LAZY LOADING: Os módulos pesados são importados APENAS dentro
    do bloco que precisa deles, reduzindo o consumo de RAM no idle.
    """
    task_id = task.get("id")
    task_type = task.get("type")
    payload = task.get("payload", {})
    
    logger.info(f"Processando tarefa {task_id} ({task_type})")
    
    try:
        start_time = time.time()
        result = None
        
        # ============================================================
        # SCRAPE PROPERTY - Importa scraper apenas quando necessário
        # ============================================================
        if task_type == "scrape_property":
            # LAZY IMPORT: Carrega o scraper pesado apenas agora
            from services.scraper import scrape_property_url
            
            url = payload.get("url")
            if url:
                result = await scrape_property_url(url)
                # Se for lead, actualizar dados
                lead_id = payload.get("lead_id")
                if lead_id and result:
                    await db.property_leads.update_one(
                        {"id": lead_id},
                        {"$set": {
                            "title": result.get("titulo"),
                            "price": result.get("preco"),
                            "location": result.get("localizacao"),
                            "scraped_data": result,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
        
        # ============================================================
        # MATCH LEADS - Importa Pandas/Fuzzy apenas quando necessário
        # ============================================================
        elif task_type == "match_leads":
            # LAZY IMPORT: Carrega o módulo pesado de matching (Pandas)
            from services.client_match import match_leads_to_clients
            
            result = await match_leads_to_clients()
        
        # ============================================================
        # SEND EMAIL - Importa email service apenas quando necessário
        # ============================================================
        elif task_type == "send_email":
            # LAZY IMPORT: Carrega o serviço de email
            from services.email_service import email_service
            
            to_email = payload.get("to")
            subject = payload.get("subject")
            content = payload.get("content")
            if to_email and subject and content:
                result = await email_service.send_email(to_email, subject, content)
        
        # ============================================================
        # TIPO DESCONHECIDO
        # ============================================================
        else:
            logger.warning(f"Tipo de tarefa desconhecido: {task_type}")
            result = {"error": "Unknown task type"}
            
        # Marcar como concluída
        duration = time.time() - start_time
        await task_queue.complete_task(task_id, result=result)
        logger.info(f"Tarefa {task_id} concluída em {duration:.2f}s")
        
    except Exception as e:
        logger.error(f"Erro ao processar tarefa {task_id}: {e}", exc_info=True)
        await task_queue.fail_task(task_id, error=str(e))


async def worker_loop():
    """
    Loop principal do worker.
    Verifica e processa tarefas da fila.
    """
    logger.info("Worker iniciado. Aguardando tarefas...")
    
    while not shutdown_event.is_set():
        try:
            # Buscar próxima tarefa pendente. `excluir_tipos` é o par
            # complementar do `tipos` que o `scheduler_loop` usa: os dois
            # laços consomem a MESMA fila, e sem o filtro cada um reclamava
            # tarefas que não sabe tratar e gastava-lhes as tentativas.
            from services.task_queue_mongo import TIPO_FORCAR_JOB

            task = await task_queue.get_next_task(excluir_tipos=[TIPO_FORCAR_JOB])
            
            if task:
                await process_task(task)
            else:
                # Se não há tarefas, esperar um pouco
                await asyncio.sleep(2)
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no loop do worker: {e}")
            await asyncio.sleep(5)  # Esperar antes de tentar novamente


# `run_scheduled_tasks` foi REMOVIDA no Lote 2 (ponto 1), não desligada: o
# trabalho é agora `job_executors.EXECUTORES["scheduled_tasks"]`, que o laço
# e o botão «Forçar Execução» partilham. O kill switch de produção que ela
# tinha passou a viver em `executar_job` (via `job_esta_activo`), uma guarda
# única em vez de um `if` por job — que é como se esquece um. Deixá-la aqui
# a chamar o mesmo serviço era a segunda cópia que este lote existe para
# eliminar, e código adormecido é um convite a religá-lo.


async def scheduler_loop():
    """Laço das tarefas agendadas do Processador.

    REESTRUTURADO no Lote 2 (ponto 1). O que estava mal não era a
    cadência — era a ESTRUTURA:

      · Os três jobs partilhavam UM `try`. O `task_queue.add_task` do
        matching não existe (`AttributeError`), a excepção subia por
        dentro do `async with heartbeat(...)` e saltava tudo o que vinha
        depois. O bloco de sincronização de webmail estava DEPOIS, logo
        **nunca era alcançado** — e é por isso, e não por o Processador
        estar em baixo, que `webmail_worker_sync` aparecia como «Nunca
        correu» no painel.

      · `last_runs[...]` era escrito DEPOIS do trabalho. Um job que
        falhasse não registava a passagem e voltava a tentar 60 segundos
        depois, para sempre, em vez de esperar o seu intervalo.

    Hoje cada job é independente: um `try` por job (`_correr_job`), o
    relógio avança mesmo quando o trabalho falha, e o trabalho em si vem
    de `job_executors.EXECUTORES` — o MESMO registo que o botão «Forçar
    Execução» do painel usa. Duas definições de "correr este job"
    divergiriam sem dar erro.

    BLOQUEIO RADICAL: só produção permite o agendador.
    """
    import os
    if os.environ.get('ENVIRONMENT') != 'production':
        logger.info("[scheduler_loop] BLOCKED — ENVIRONMENT != production — scheduler will NOT start")
        return

    logger.info("Agendador iniciado.")

    # `last_runs` vive na memória DESTE processo e a API nunca o vê — o
    # batimento (colecção partilhada) é a única coisa que atravessa a
    # fronteira entre o worker e a web.
    jobs = _jobs_do_processador()
    last_runs = {chave: 0.0 for chave in jobs}

    while not shutdown_event.is_set():
        try:
            agora = time.time()

            for chave, intervalo in jobs.items():
                if agora - last_runs[chave] <= intervalo:
                    continue
                # O relógio avança ANTES do trabalho: um job que rebente
                # tem de esperar o seu intervalo, não voltar dentro de 60s.
                last_runs[chave] = agora
                await _correr_job(chave)

            await _atender_pedidos_de_execucao()

            await asyncio.sleep(60)  # Verificar a cada minuto

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no agendador: {e}")
            await asyncio.sleep(60)


async def _correr_job(chave: str) -> None:
    """Corre um job do Processador, isolado dos outros.

    O `try` é POR JOB de propósito: com um `try` partilhado, o primeiro a
    rebentar levava os seguintes consigo — foi exactamente assim que a
    sincronização de webmail deixou de correr.
    """
    from services.job_executors import executar_job

    logger.info("[Agendador] A correr %s...", chave)
    try:
        await executar_job(chave)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        # O batimento já registou `erro` e o painel mostra-o; aqui fica o
        # log para quem está a ler a consola do Render.
        logger.error("[Agendador] Job %s falhou: %s", chave, e, exc_info=True)


async def _atender_pedidos_de_execucao() -> None:
    """Reclama os pedidos de «Forçar Execução» vindos do painel.

    A web não consegue invocar este processo (são serviços distintos do
    `render.yaml`), logo o painel deixa um pedido na fila persistente e é
    aqui que ele é atendido. Um pedido que fique pendente PROVA que este
    laço não está a correr — é esse o valor de diagnóstico que o painel
    não tinha.
    """
    from services.task_queue_mongo import (
        TIPO_FORCAR_JOB,
        complete_task,
        fail_task,
        get_next_task,
    )

    for _ in range(5):  # tecto por ciclo: não deixa o laço preso na fila
        # `tipos` e não um filtro depois de reclamar: reclamar uma tarefa do
        # `worker_loop` para a devolver gastava-lhe uma tentativa, e três
        # ciclos matavam-na sem ela nunca ter chegado a quem a sabe correr.
        tarefa = await get_next_task(tipos=[TIPO_FORCAR_JOB])
        if not tarefa:
            return
        task_id = tarefa.get("id")
        chave = (tarefa.get("payload") or {}).get("chave") or ""
        logger.info("[Agendador] Pedido de execução forçada: %s", chave)
        try:
            from services.job_executors import executar_job

            await executar_job(chave)
            await complete_task(task_id, result={"chave": chave})
        except Exception as e:
            logger.error("[Agendador] Execução forçada de %s falhou: %s", chave, e)
            await fail_task(task_id, error=str(e))



async def cleanup_temp_files():
    """Limpa ficheiros temporários antigos."""
    logger.info("A executar limpeza de ficheiros temporários...")
    
    # CORREÇÃO DE SEGURANÇA: Usar caminhos dinâmicos
    sys_temp = tempfile.gettempdir()
    
    # Lista de diretorias a limpar
    temp_dirs = [
        os.path.join(sys_temp, "creditoimo"),
        os.path.join(os.getcwd(), "backend", "temp")  # Caminho relativo seguro
    ]
    
    files_deleted = 0
    
    for temp_dir in temp_dirs:
        if os.path.exists(temp_dir):
            try:
                for filename in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, filename)
                    try:
                        # Se ficheiro tem mais de 24h
                        if os.path.isfile(file_path):
                            if time.time() - os.path.getmtime(file_path) > 86400:
                                os.remove(file_path)
                                files_deleted += 1
                    except Exception as e:
                        logger.warning(f"Erro ao apagar {file_path}: {e}")
            except Exception as e:
                logger.warning(f"Erro ao listar {temp_dir}: {e}")
                
    logger.info(f"Limpeza concluída. {files_deleted} ficheiros removidos.")


def handle_shutdown(signum, frame):
    """Handler para sinais de paragem."""
    logger.info("Sinal de paragem recebido. A terminar graciosamente...")
    shutdown_event.set()


async def shutdown_async():
    """Paragem assíncrona."""
    shutdown_event.set()


async def main():
    """Ponto de entrada principal do worker."""

    # ==================================================================
    # KILL SWITCH — BLOQUEIO RADICAL: SÓ PRODUÇÃO PERMITE WORKER
    # ==================================================================
    # REGRA ABSOLUTA: O worker SÓ arranca em ENVIRONMENT=production.
    # Qualquer outro valor bloqueia o worker inteiro — sem event loop,
    # sem DB connection, sem RAM consumption.
    # ==================================================================
    import os
    is_production = os.environ.get('ENVIRONMENT', 'dev') == 'production'
    if not is_production:
        logger.info("=" * 60)
        logger.info("🛑 RADICAL KILL SWITCH: Worker process NOT starting")
        logger.info("   ENVIRONMENT = '%s' (only 'production' enables worker)", os.environ.get('ENVIRONMENT', ''))
        logger.info("   All scheduled tasks (webmail sync, matching, etc.)")
        logger.info("   are BLOCKED. Use on-demand endpoints instead.")
        logger.info("=" * 60)
        return  # Exit immediately — no event loop, no DB connection, no RAM

    # Registar handlers de sinais (SIGINT, SIGTERM)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown_async()))

    logger.info("=" * 60)
    logger.info("Worker iniciado com LAZY LOADING ativo")
    logger.info("Módulos pesados serão carregados apenas quando necessário")
    logger.info("=" * 60)

    # Iniciar tarefas concorrentes
    worker_task = asyncio.create_task(worker_loop())
    scheduler_task = asyncio.create_task(scheduler_loop())
    
    # Aguardar sinal de paragem
    await shutdown_event.wait()
    
    # Aguardar finalização das tarefas
    worker_task.cancel()
    scheduler_task.cancel()
    try:
        await asyncio.gather(worker_task, scheduler_task)
    except asyncio.CancelledError:
        pass
        
    logger.info("Worker desligado.")


if __name__ == "__main__":
    asyncio.run(main())
