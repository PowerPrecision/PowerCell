"""
====================================================================
TASK QUEUE SERVICE - CREDITOIMO
====================================================================
Serviço para enfileirar tarefas de forma simplificada.

Uso:
    from services.task_queue import task_queue
    
    # Enfileirar email
    await task_queue.send_email(
        to="cliente@email.com",
        subject="Bem-vindo!",
        body="Obrigado por se registar."
    )
    
    # Processar documento com IA
    await task_queue.process_document(process_id, document_data, user_id)
    
    # Sincronizar com Trello
    await task_queue.sync_trello(process_id)

====================================================================
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from arq import create_pool
from arq.connections import ArqRedis

from config import get_redis_settings

logger = logging.getLogger(__name__)


class TaskQueueService:
    """
    Serviço de fila de tarefas.
    Fornece métodos de alto nível para enfileirar tarefas.
    """
    
    def __init__(self):
        self._pool: Optional[ArqRedis] = None
        self._connected = False
    
    async def connect(self) -> bool:
        """Conecta à fila de tarefas (Redis). Retorna False se não disponível."""
        if self._connected and self._pool:
            return True
        
        try:
            redis_settings = get_redis_settings()
            
            # Se não há configuração Redis, Task Queue fica desabilitada
            if redis_settings is None:
                logger.info("ℹ️ Redis não configurado - Task Queue desabilitada (modo síncrono)")
                self._connected = False
                return False
            
            self._pool = await create_pool(redis_settings)
            self._connected = True
            logger.info("✅ Task Queue conectada ao Redis")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Redis não disponível - Task Queue desabilitada: {str(e)[:100]}")
            self._connected = False
            return False
    
    async def disconnect(self) -> None:
        """Desconecta da fila de tarefas."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._connected = False
            logger.info("Task Queue desconectada")
    
    async def _ensure_connected(self) -> bool:
        """Garante que está conectado."""
        if not self._connected:
            return await self.connect()
        return True
    
    @property
    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        return self._connected
    
    # ================================================================
    # MÉTODOS DE ENFILEIRAMENTO
    # ================================================================
    
    async def enqueue(
        self,
        function_name: str,
        *args,
        queue_name: Optional[str] = None,
        defer_by: Optional[timedelta] = None,
        defer_until: Optional[datetime] = None,
        **kwargs
    ) -> Optional[str]:
        """
        Enfileira uma tarefa genérica.
        
        Returns:
            Job ID se sucesso, None se falhar
        """
        if not await self._ensure_connected():
            logger.warning(f"Task Queue não disponível, executando {function_name} localmente")
            return None
        
        try:
            job = await self._pool.enqueue_job(
                function_name,
                *args,
                _queue_name=queue_name,
                _defer_by=defer_by,
                _defer_until=defer_until,
                **kwargs
            )
            logger.info(f"📤 Tarefa enfileirada: {function_name} (job={job.job_id})")
            return job.job_id
        except Exception as e:
            logger.error(f"❌ Erro ao enfileirar {function_name}: {str(e)}")
            return None
    
    # ================================================================
    # MÉTODOS DE CONVENIÊNCIA - EMAIL
    # ================================================================
    
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        defer_by: Optional[timedelta] = None
    ) -> Optional[str]:
        """
        Enfileira envio de email.
        
        Args:
            to: Email destinatário
            subject: Assunto
            body: Corpo texto
            html_body: Corpo HTML (opcional)
            defer_by: Atrasar envio (opcional)
        """
        return await self.enqueue(
            "send_email_task",
            to_email=to,
            subject=subject,
            body=body,
            html_body=html_body,
            defer_by=defer_by
        )
    
    async def send_registration_email(
        self,
        client_email: str,
        client_name: str,
        portal_access_code: str = None
    ) -> Optional[str]:
        """Enfileira email de confirmação de registo."""
        kwargs = {
            "client_email": client_email,
            "client_name": client_name,
        }
        if portal_access_code:
            kwargs["portal_access_code"] = portal_access_code
        return await self.enqueue(
            "send_registration_email_task",
            **kwargs
        )
    
    # ================================================================
    # MÉTODOS DE CONVENIÊNCIA - IA/DOCUMENTOS
    # ================================================================
    
    async def process_document(
        self,
        process_id: str,
        document_data: Dict[str, Any],
        user_id: str
    ) -> Optional[str]:
        """Enfileira processamento de documento com IA."""
        return await self.enqueue(
            "process_ai_document_task",
            process_id=process_id,
            document_data=document_data,
            user_id=user_id
        )
    
    # ================================================================
    # MÉTODOS DE CONVENIÊNCIA - TRELLO
    # ================================================================
    
    async def sync_trello(
        self,
        process_id: str,
        action: str = "sync"
    ) -> Optional[str]:
        """
        Enfileira sincronização com Trello.
        
        Args:
            process_id: ID do processo
            action: "sync" | "create_card" | "update_card"
        """
        return await self.enqueue(
            "sync_trello_task",
            process_id=process_id,
            action=action
        )
    
    # ================================================================
    # HEALTH CHECK
    # ================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica estado da fila de tarefas."""
        try:
            if not await self._ensure_connected():
                return {
                    "status": "disconnected",
                    "redis": False,
                    "error": "Could not connect to Redis"
                }
            
            # Ping Redis
            info = await self._pool.info()
            
            return {
                "status": "healthy",
                "redis": True,
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "unknown")
            }
            
        except Exception as e:
            return {
                "status": "error",
                "redis": False,
                "error": str(e)
            }
    
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Obtém estado de um job."""
        if not await self._ensure_connected():
            return None
        
        try:
            from arq.jobs import Job
            job = Job(job_id, self._pool)
            status = await job.status()
            result = await job.result(timeout=0)
            
            return {
                "job_id": job_id,
                "status": status.name if status else "unknown",
                "result": result
            }
        except Exception as e:
            logger.error(f"Erro ao obter status do job {job_id}: {str(e)}")
            return None


# ====================================================================
# INSTÂNCIA GLOBAL
# ====================================================================
task_queue = TaskQueueService()


# ====================================================================
# FALLBACK PARA EXECUÇÃO DIRETA
# ====================================================================
class DirectExecutionFallback:
    """
    Fallback para quando Redis não está disponível.
    Executa tarefas directamente (sem fila).
    """
    
    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Envia email directamente (sem fila)."""
        logger.warning(f"[FALLBACK] Enviando email directamente para {to}")
        
        try:
            from services.email_v2 import send_email_notification
            return await send_email_notification(to, subject, body, html_body)
        except Exception as e:
            logger.error(f"[FALLBACK] Erro ao enviar email: {str(e)}")
            return False
    
    async def send_registration_email(
        self,
        client_email: str,
        client_name: str,
        portal_access_code: str = None
    ) -> bool:
        """Envia email de registo directamente."""
        logger.warning("[FALLBACK] Enviando email de registo directamente")
        
        try:
            from services.email import send_registration_confirmation
            return await send_registration_confirmation(client_email, client_name, portal_access_code)
        except Exception as e:
            logger.error(f"[FALLBACK] Erro: {str(e)}")
            return False


# Instância de fallback
direct_executor = DirectExecutionFallback()


async def get_executor():
    """
    Retorna o executor apropriado.
    Se Redis disponível: task_queue
    Se não: direct_executor (fallback)
    """
    if await task_queue.connect():
        return task_queue
    return direct_executor
