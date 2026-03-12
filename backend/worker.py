"""
====================================================================
WORKER - Processador de Tarefas Assíncronas
====================================================================
Refatorizado para usar LAZY LOADING nos módulos pesados.
Isto reduz significativamente o consumo de memória no arranque (idle).

Módulos carregados APENAS quando necessário:
- services.scraper (BeautifulSoup/Playwright -> Pesado)
- services.trello (Cliente HTTP -> Médio)
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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("worker")

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
# - services.trello (trello_service)
# - services.email_service (email_service)
# - services.client_match (match_leads_to_clients)
# - services.scheduled_tasks (ScheduledTasksService)
# ====================================================================

# Flag para paragem graciosa
shutdown_event = asyncio.Event()


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
                # Se for lead, atualizar dados
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
        # SYNC TRELLO - Importa Trello service apenas quando necessário
        # ============================================================
        elif task_type == "sync_trello":
            # LAZY IMPORT: Carrega o serviço Trello
            from services.trello import trello_service
            
            result = await trello_service.sync_board()
        
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
            # Buscar próxima tarefa pendente
            task = await task_queue.get_next_task()
            
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


async def run_scheduled_tasks():
    """
    Executa as tarefas agendadas (carrega o serviço apenas quando necessário).
    LAZY LOADING: O módulo pesado scheduled_tasks só é carregado aqui.
    """
    try:
        # LAZY IMPORT: Carrega o serviço de tarefas agendadas
        from services.scheduled_tasks import ScheduledTasksService
        
        service = ScheduledTasksService()
        await service.run_all_tasks()
    except Exception as e:
        logger.error(f"Erro ao executar tarefas agendadas: {e}")


async def scheduler_loop():
    """
    Loop para tarefas agendadas (Cron jobs).
    """
    logger.info("Agendador iniciado.")
    
    # Horários da última execução
    last_runs = {
        "scheduled": 0,
        "matching": 0
    }
    
    while not shutdown_event.is_set():
        try:
            now = time.time()
            
            # Executar tarefas agendadas (a cada 1 hora)
            if now - last_runs["scheduled"] > 3600:
                logger.info("Executando tarefas agendadas...")
                await run_scheduled_tasks()
                last_runs["scheduled"] = now

            # Matching automático de Leads (a cada 30 minutos)
            # Nota: O import pesado só acontece quando a tarefa for processada
            if now - last_runs["matching"] > 1800:
                logger.info("Agendando matching automático...")
                await task_queue.add_task("match_leads", {})
                last_runs["matching"] = now
            
            await asyncio.sleep(60)  # Verificar a cada minuto
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no agendador: {e}")
            await asyncio.sleep(60)


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
