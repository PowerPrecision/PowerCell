"""
====================================================================
TAREFAS AGENDADAS (CRON JOBS) - CREDITOIMO
====================================================================
Sistema de tarefas agendadas para execução diária.

Tarefas incluídas:
- Verificação de documentos a expirar
- Verificação de prazos a aproximar-se
- Limpeza de notificações antigas
- Geração de alertas automáticos

Uso:
    # Executar manualmente
    python -m services.scheduled_tasks
    
    # Ou via cron (Linux) - executar diariamente às 8h:
    0 8 * * * cd /app/backend && python -m services.scheduled_tasks
    
    # Ou iniciar como processo em background:
    python -m services.scheduled_tasks --daemon
====================================================================
"""

import asyncio
import logging
import argparse
import random
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import uuid
import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# Load env
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from motor.motor_asyncio import AsyncIOMotorClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScheduledTasksService:
    """Serviço de tarefas agendadas."""
    
    def __init__(self):
        self.mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.db_name = os.environ.get('DB_NAME', 'test_database')
        self.client = None
        self.db = None
    
    async def connect(self):
        """Conectar à base de dados."""
        self.client = AsyncIOMotorClient(self.mongo_url)
        self.db = self.client[self.db_name]
        logger.info(f"Conectado à base de dados: {self.db_name}")
    
    async def disconnect(self):
        """Desconectar da base de dados."""
        if self.client:
            self.client.close()
            logger.info("Desconectado da base de dados")
    
    async def create_notification(
        self,
        user_id: str,
        message: str,
        notification_type: str,
        process_id: str = None,
        client_name: str = None,
        link: str = None
    ):
        """Criar uma notificação na base de dados."""
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "message": message,
            "type": notification_type,
            "process_id": process_id,
            "client_name": client_name,
            "link": link,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db.notifications.insert_one(notification)
        return notification
    
    async def check_expiring_documents(self) -> int:
        """
        Verificar documentos a expirar nos próximos 7 dias.
        Criar notificações para os utilizadores responsáveis.
        """
        logger.info("A verificar documentos a expirar...")
        
        today = datetime.now(timezone.utc)
        warning_date = today + timedelta(days=7)
        
        # Buscar processos com documentos
        processes = await self.db.processes.find(
            {"documents": {"$exists": True, "$ne": []}},
            {"_id": 0}
        ).to_list(1000)
        
        notifications_created = 0
        
        for process in processes:
            documents = process.get("documents", [])
            
            for doc in documents:
                expiry_date_str = doc.get("expiry_date")
                if not expiry_date_str:
                    continue
                
                try:
                    expiry_date = datetime.fromisoformat(expiry_date_str.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    continue
                
                # Verificar se expira nos próximos 7 dias
                if today <= expiry_date <= warning_date:
                    days_until = (expiry_date - today).days
                    
                    # Notificar consultor e mediador
                    users_to_notify = []
                    if process.get("consultor_id"):
                        users_to_notify.append(process["consultor_id"])
                    if process.get("mediador_id"):
                        users_to_notify.append(process["mediador_id"])
                    
                    for user_id in users_to_notify:
                        # Verificar se já existe notificação similar recente
                        existing = await self.db.notifications.find_one({
                            "user_id": user_id,
                            "process_id": process.get("id"),
                            "type": "document_expiry",
                            "created_at": {"$gte": (today - timedelta(days=1)).isoformat()}
                        })
                        
                        if not existing:
                            await self.create_notification(
                                user_id=user_id,
                                message=f"Documento '{doc.get('name', 'Sem nome')}' expira em {days_until} dias",
                                notification_type="document_expiry",
                                process_id=process.get("id"),
                                client_name=process.get("client_name"),
                                link=f"/process/{process.get('id')}"
                            )
                            notifications_created += 1
        
        logger.info(f"Documentos a expirar: {notifications_created} notificações criadas")
        return notifications_created
    
    async def check_upcoming_deadlines(self) -> int:
        """
        Verificar prazos/eventos nas próximas 24 horas.
        Criar notificações para os participantes.
        """
        logger.info("A verificar prazos próximos...")
        
        today = datetime.now(timezone.utc)
        tomorrow = today + timedelta(days=1)
        
        # Buscar deadlines próximos
        deadlines = await self.db.deadlines.find({
            "date": {
                "$gte": today.isoformat(),
                "$lte": tomorrow.isoformat()
            }
        }, {"_id": 0}).to_list(500)
        
        notifications_created = 0
        
        for deadline in deadlines:
            participants = deadline.get("participants", [])
            
            for user_id in participants:
                # Verificar se já existe notificação similar
                existing = await self.db.notifications.find_one({
                    "user_id": user_id,
                    "type": "deadline_reminder",
                    "message": {"$regex": deadline.get("title", "")},
                    "created_at": {"$gte": (today - timedelta(hours=12)).isoformat()}
                })
                
                if not existing:
                    await self.create_notification(
                        user_id=user_id,
                        message=f"Lembrete: {deadline.get('title', 'Evento')} - amanhã",
                        notification_type="deadline_reminder",
                        process_id=deadline.get("process_id"),
                        link="/admin?tab=calendar"
                    )
                    notifications_created += 1
        
        logger.info(f"Prazos próximos: {notifications_created} notificações criadas")
        return notifications_created
    
    async def check_tasks_due_soon(self) -> int:
        """
        Verificar tarefas com prazo próximo (3 dias ou menos) ou atrasadas.
        Enviar alertas para os utilizadores atribuídos.
        
        Alertas:
        - 3 dias antes: "Tarefa vence em 3 dias"
        - 1 dia antes: "Tarefa vence amanhã"
        - No dia: "Tarefa vence hoje!"
        - Atrasada: "Tarefa atrasada!"
        """
        logger.info("A verificar tarefas com prazo próximo...")
        
        today = datetime.now(timezone.utc)
        
        # Buscar tarefas não concluídas com due_date
        tasks = await self.db.tasks.find({
            "completed": False,
            "due_date": {"$exists": True, "$ne": None}
        }, {"_id": 0}).to_list(500)
        
        notifications_created = 0
        
        for task in tasks:
            due_date_str = task.get("due_date")
            if not due_date_str:
                continue
            
            try:
                due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                continue
            
            days_until_due = (due_date.date() - today.date()).days
            
            # Definir mensagem baseada nos dias
            if days_until_due < 0:
                # Atrasada
                message = f"🚨 TAREFA ATRASADA ({abs(days_until_due)} dias): {task.get('title', 'Sem título')}"
                notification_type = "task_overdue"
            elif days_until_due == 0:
                # Vence hoje
                message = f"⚠️ Tarefa vence HOJE: {task.get('title', 'Sem título')}"
                notification_type = "task_due_today"
            elif days_until_due == 1:
                # Vence amanhã
                message = f"📅 Tarefa vence amanhã: {task.get('title', 'Sem título')}"
                notification_type = "task_due_tomorrow"
            elif days_until_due <= 3:
                # Vence em 3 dias ou menos
                message = f"📋 Tarefa vence em {days_until_due} dias: {task.get('title', 'Sem título')}"
                notification_type = "task_due_soon"
            else:
                # Ainda não está perto do prazo
                continue
            
            # Notificar todos os utilizadores atribuídos
            for user_id in task.get("assigned_to", []):
                # Verificar se já existe notificação similar nas últimas 12 horas
                existing = await self.db.notifications.find_one({
                    "user_id": user_id,
                    "type": notification_type,
                    "message": {"$regex": task.get("id", "")},
                    "created_at": {"$gte": (today - timedelta(hours=12)).isoformat()}
                })
                
                if not existing:
                    link = f"/process/{task['process_id']}" if task.get("process_id") else "/staff?tab=tasks"
                    
                    await self.create_notification(
                        user_id=user_id,
                        message=message,
                        notification_type=notification_type,
                        process_id=task.get("process_id"),
                        link=link
                    )
                    notifications_created += 1
        
        logger.info(f"Tarefas com prazo próximo: {notifications_created} notificações criadas")
        return notifications_created
    
    async def check_pre_approval_countdown(self) -> int:
        """
        Verificar processos com pré-aprovação a expirar (90 dias).
        Alertar quando faltam 30, 15, 7 e 3 dias.
        """
        logger.info("A verificar countdowns de pré-aprovação...")
        
        today = datetime.now(timezone.utc)
        alert_days = [30, 15, 7, 3]
        
        # Buscar processos com data de pré-aprovação
        processes = await self.db.processes.find({
            "credit_data.bank_approval_date": {"$exists": True, "$ne": None}
        }, {"_id": 0}).to_list(1000)
        
        notifications_created = 0
        
        for process in processes:
            approval_date_str = process.get("credit_data", {}).get("bank_approval_date")
            if not approval_date_str:
                continue
            
            try:
                approval_date = datetime.fromisoformat(approval_date_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                continue
            
            # Calcular dias restantes (90 dias desde aprovação)
            expiry_date = approval_date + timedelta(days=90)
            days_remaining = (expiry_date - today).days
            
            if days_remaining in alert_days:
                users_to_notify = []
                if process.get("consultor_id"):
                    users_to_notify.append(process["consultor_id"])
                if process.get("mediador_id"):
                    users_to_notify.append(process["mediador_id"])
                
                for user_id in users_to_notify:
                    existing = await self.db.notifications.find_one({
                        "user_id": user_id,
                        "process_id": process.get("id"),
                        "type": "pre_approval_countdown",
                        "created_at": {"$gte": (today - timedelta(days=1)).isoformat()}
                    })
                    
                    if not existing:
                        await self.create_notification(
                            user_id=user_id,
                            message=f"⏰ Pré-aprovação expira em {days_remaining} dias!",
                            notification_type="pre_approval_countdown",
                            process_id=process.get("id"),
                            client_name=process.get("client_name"),
                            link=f"/process/{process.get('id')}"
                        )
                        notifications_created += 1
        
        logger.info(f"Countdown pré-aprovação: {notifications_created} notificações criadas")
        return notifications_created
    
    async def cleanup_old_notifications(self, days: int = 30) -> int:
        """
        Limpar notificações lidas com mais de X dias.
        """
        logger.info(f"A limpar notificações com mais de {days} dias...")
        
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        result = await self.db.notifications.delete_many({
            "read": True,
            "created_at": {"$lt": cutoff_date}
        })
        
        logger.info(f"Notificações removidas: {result.deleted_count}")
        return result.deleted_count
    
    async def check_clients_waiting_too_long(self, days: int = 15) -> int:
        """
        Verificar clientes no estado "em espera" há mais de X dias.
        Alerta CEO e Diretores.
        """
        logger.info(f"A verificar clientes em espera há mais de {days} dias...")
        
        today = datetime.now(timezone.utc)
        cutoff_date = (today - timedelta(days=days)).isoformat()
        
        # Buscar processos em estado "clientes_espera" há muito tempo
        processes = await self.db.processes.find({
            "status": "clientes_espera",
            "created_at": {"$lte": cutoff_date}
        }, {"_id": 0}).to_list(500)
        
        if not processes:
            logger.info("Nenhum cliente em espera há muito tempo")
            return 0
        
        from services.role_query import deep_role_in_filter
        managers = await self.db.users.find({
            "$and": [deep_role_in_filter(["ceo", "diretor", "admin"]), {"is_active": {"$ne": False}}]
        }, {"_id": 0, "id": 1, "name": 1}).to_list(50)
        
        notifications_created = 0
        
        for manager in managers:
            # Verificar se já enviou notificação hoje
            existing = await self.db.notifications.find_one({
                "user_id": manager["id"],
                "type": "clients_waiting",
                "created_at": {"$gte": (today - timedelta(hours=24)).isoformat()}
            })
            
            if not existing:
                await self.create_notification(
                    user_id=manager["id"],
                    message=f"⚠️ {len(processes)} cliente(s) em espera há mais de {days} dias. Requer atenção!",
                    notification_type="clients_waiting",
                    link="/admin?tab=overview"
                )
                notifications_created += 1
        
        logger.info(f"Clientes em espera: {notifications_created} notificações criadas para {len(processes)} clientes")
        return notifications_created
    
    async def check_document_expirations_watchdog(self, days_ahead: int = 60) -> int:
        """
        WATCHDOG DE VALIDADE DE DOCUMENTOS
        
        Verifica documentos (da colecção document_metadata) que expiram nos próximos X dias.
        Cria notificações para os consultores/intermediários responsáveis.
        
        Níveis de urgência:
        - Vermelho: < 7 dias
        - Laranja: 7-29 dias
        - Amarelo: 30-60 dias
        
        Args:
            days_ahead: Dias a verificar à frente (default 60)
        
        Returns:
            Número de notificações criadas
        """
        logger.info(f"[WATCHDOG] A verificar documentos a expirar nos próximos {days_ahead} dias...")
        
        today = datetime.now(timezone.utc)
        future_date = today + timedelta(days=days_ahead)
        
        # Buscar documentos com data de expiração dentro do período
        # Que ainda não tiveram alerta enviado
        expiring_docs = await self.db.document_metadata.find({
            "expiry_date": {
                "$ne": None,
                "$gte": today.strftime("%Y-%m-%d"),
                "$lte": future_date.strftime("%Y-%m-%d")
            },
            "expiry_alert_sent": {"$ne": True}
        }, {"_id": 0}).to_list(500)
        
        logger.info(f"[WATCHDOG] Encontrados {len(expiring_docs)} documentos a expirar")
        
        notifications_created = 0
        
        for doc in expiring_docs:
            try:
                expiry_date = datetime.strptime(doc["expiry_date"], "%Y-%m-%d")
                days_until = (expiry_date - today).days
                
                # Determinar urgência visual
                if days_until < 7:
                    urgency_emoji = "🔴"
                elif days_until < 30:
                    urgency_emoji = "🟠"
                else:
                    urgency_emoji = "🟡"
                
                # Obter o processo para identificar os responsáveis
                process = await self.db.processes.find_one(
                    {"id": doc["process_id"]},
                    {"_id": 0, "client_name": 1, "assigned_consultor_id": 1, 
                     "consultor_id": 1, "assigned_mediador_id": 1, "mediador_id": 1}
                )
                
                if not process:
                    continue
                
                client_name = doc.get("client_name") or process.get("client_name", "Cliente")
                doc_category = doc.get("ai_category") or doc.get("ai_subcategory") or "Documento"
                
                # Identificar utilizadores a notificar
                users_to_notify = set()
                if process.get("assigned_consultor_id"):
                    users_to_notify.add(process["assigned_consultor_id"])
                if process.get("consultor_id"):
                    users_to_notify.add(process["consultor_id"])
                if process.get("assigned_mediador_id"):
                    users_to_notify.add(process["assigned_mediador_id"])
                if process.get("mediador_id"):
                    users_to_notify.add(process["mediador_id"])
                
                # Notificar cada utilizador
                for user_id in users_to_notify:
                    # Verificar se já existe notificação recente para este documento
                    existing = await self.db.notifications.find_one({
                        "user_id": user_id,
                        "type": "document_expiry_watchdog",
                        "message": {"$regex": doc.get("id", "")},
                        "created_at": {"$gte": (today - timedelta(days=1)).isoformat()}
                    })
                    
                    if not existing:
                        message = f"{urgency_emoji} {doc_category} de {client_name} expira em {days_until} dias ({expiry_date.strftime('%d/%m/%Y')})"
                        
                        await self.create_notification(
                            user_id=user_id,
                            message=message,
                            notification_type="document_expiry_watchdog",
                            process_id=doc["process_id"],
                            client_name=client_name,
                            link=f"/process/{doc['process_id']}"
                        )
                        notifications_created += 1
                
                # Marcar documento como alerta enviado
                await self.db.document_metadata.update_one(
                    {"id": doc["id"]},
                    {"$set": {"expiry_alert_sent": True, "expiry_alert_sent_at": today.isoformat()}}
                )
                
            except Exception as e:
                logger.error(f"[WATCHDOG] Erro ao processar documento {doc.get('id')}: {e}")
                continue
        
        logger.info(f"[WATCHDOG] Documentos a expirar: {notifications_created} notificações criadas")
        return notifications_created
    
    async def send_monthly_document_reminder(self) -> int:
        """
        No 1º dia de cada mês, enviar alerta para consultores e intermediários
        para pedirem recibo e extrato de conta ao cliente.
        Também envia email ao cliente.
        """
        today = datetime.now(timezone.utc)
        
        # Verificar se é o 1º dia do mês
        if today.day != 1:
            logger.info("Não é o 1º dia do mês - ignorando alerta mensal")
            return 0
        
        logger.info("A enviar lembretes mensais de documentação...")
        
        # Mês anterior
        if today.month == 1:
            prev_month = 12
            prev_year = today.year - 1
        else:
            prev_month = today.month - 1
            prev_year = today.year
        
        month_names = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }
        prev_month_name = month_names[prev_month]
        
        # Buscar processos ativos (não concluídos ou desistidos)
        active_statuses = [
            "clientes_espera", "fase_documental", "fase_documental_ii",
            "enviado_bruno", "enviado_luis", "enviado_bcp_rui",
            "entradas_precision", "fase_bancaria", "fase_visitas",
            "ch_aprovado", "fase_escritura", "escritura_agendada"
        ]
        
        processes = await self.db.processes.find({
            "status": {"$in": active_statuses}
        }, {"_id": 0}).to_list(1000)
        
        notifications_created = 0
        
        for process in processes:
            users_to_notify = []
            
            # Consultor
            if process.get("assigned_consultor_id"):
                users_to_notify.append(process["assigned_consultor_id"])
            elif process.get("consultor_id"):
                users_to_notify.append(process["consultor_id"])
            
            # Intermediário
            if process.get("assigned_mediador_id"):
                users_to_notify.append(process["assigned_mediador_id"])
            elif process.get("mediador_id"):
                users_to_notify.append(process["mediador_id"])
            
            client_name = process.get("client_name", "Cliente")
            
            for user_id in set(users_to_notify):
                await self.create_notification(
                    user_id=user_id,
                    message=f"📄 Pedir recibo de vencimento e extrato bancário de {prev_month_name} ao cliente {client_name}",
                    notification_type="monthly_document_reminder",
                    process_id=process.get("id"),
                    client_name=client_name,
                    link=f"/process/{process.get('id')}"
                )
                notifications_created += 1
            
            # Enviar email ao cliente
            client_email = process.get("client_email")
            if client_email:
                try:
                    await self.send_monthly_reminder_email(
                        to_email=client_email,
                        client_name=client_name,
                        month_name=prev_month_name,
                        year=prev_year
                    )
                except Exception as e:
                    logger.error(f"Erro ao enviar email para {client_email}: {e}")
        
        logger.info(f"Lembretes mensais: {notifications_created} notificações criadas")
        return notifications_created
    
    async def send_monthly_reminder_email(
        self, 
        to_email: str, 
        client_name: str, 
        month_name: str, 
        year: int
    ):
        """Enviar email ao cliente a pedir documentos mensais."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        smtp_server = os.environ.get('SMTP_SERVER')
        smtp_port = int(os.environ.get('SMTP_PORT', 465))
        smtp_email = os.environ.get('SMTP_EMAIL')
        smtp_password = os.environ.get('SMTP_PASSWORD')
        
        if not all([smtp_server, smtp_email, smtp_password]):
            logger.warning("SMTP não configurado - email não enviado")
            return
        
        subject = f"Documentação Mensal - {month_name} {year}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #1e3a5f; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f9f9f9; }}
                .docs-list {{ background: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Power Real Estate & Precision Crédito</h1>
                </div>
                <div class="content">
                    <p>Exmo(a). Sr(a). <strong>{client_name}</strong>,</p>
                    
                    <p>Para manter o seu processo de crédito atualizado, solicitamos o envio dos seguintes documentos referentes ao mês de <strong>{month_name} de {year}</strong>:</p>
                    
                    <div class="docs-list">
                        <h3>📄 Documentos Necessários:</h3>
                        <ul>
                            <li><strong>Recibo de Vencimento</strong> - Mês de {month_name}</li>
                            <li><strong>Extrato Bancário</strong> - Mês de {month_name}</li>
                        </ul>
                    </div>
                    
                    <p>Por favor, envie estes documentos assim que possível para que possamos dar continuidade ao seu processo.</p>
                    
                    <p>Pode enviar os documentos em resposta a este email ou através do seu consultor/intermediário.</p>
                    
                    <p>Com os melhores cumprimentos,<br>
                    <strong>Equipa Power Real Estate & Precision Crédito</strong></p>
                </div>
                <div class="footer">
                    <p>Este email foi enviado automaticamente. Por favor não responda diretamente.</p>
                    <p>Em caso de dúvidas, contacte o seu consultor ou intermediário.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_email
        msg['To'] = to_email
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        
        logger.info(f"Email mensal enviado para {to_email}")
    
    async def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """
        Limpar ficheiros temporários antigos.
        
        Remove ficheiros de directórios temporários que tenham mais de X horas.
        
        Directórios limpos:
        - /tmp/creditoimo_*
        - /app/backend/temp/
        - Ficheiros de upload temporários
        
        Args:
            max_age_hours: Idade máxima dos ficheiros em horas
            
        Returns:
            Número de ficheiros eliminados
        """
        import shutil
        
        logger.info(f"A limpar ficheiros temporários com mais de {max_age_hours}h...")
        
        files_deleted = 0
        bytes_freed = 0
        
        # Usar tempfile.gettempdir() para diretório temporário do sistema
        temp_dirs = [
            Path(tempfile.gettempdir()),  # nosec B108 - using secure tempfile module
            Path("/app/backend/temp"),
            Path("/app/backend/uploads/temp"),
        ]
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        for temp_dir in temp_dirs:
            if not temp_dir.exists():
                continue
            
            try:
                for item in temp_dir.iterdir():
                    # Apenas limpar ficheiros/pastas que comecem com creditoimo_ ou sejam .tmp
                    if not (
                        item.name.startswith("creditoimo_") or
                        item.name.startswith("tmp_") or
                        item.name.endswith(".tmp") or
                        item.name.endswith(".temp")
                    ):
                        continue
                    
                    try:
                        # Verificar idade
                        mtime = datetime.fromtimestamp(item.stat().st_mtime)
                        
                        if mtime < cutoff_time:
                            if item.is_file():
                                bytes_freed += item.stat().st_size
                                item.unlink()
                                files_deleted += 1
                            elif item.is_dir():
                                for f in item.rglob("*"):
                                    if f.is_file():
                                        bytes_freed += f.stat().st_size
                                shutil.rmtree(item)
                                files_deleted += 1
                            
                            logger.debug(f"Removido: {item}")
                    
                    except Exception as e:
                        logger.debug(f"Erro ao remover {item}: {e}")
                        continue
            
            except Exception as e:
                logger.debug(f"Erro ao processar {temp_dir}: {e}")
                continue
        
        mb_freed = bytes_freed / (1024 * 1024)
        logger.info(f"Ficheiros temporários removidos: {files_deleted} ({mb_freed:.2f} MB libertados)")
        
        return files_deleted
    
    async def cleanup_scraper_cache(self, days: int = 7) -> int:
        """
        Limpar cache de scraping expirado.
        
        Remove entradas de cache com mais de X dias.
        
        Returns:
            Número de entradas eliminadas
        """
        logger.info(f"A limpar cache de scraping com mais de {days} dias...")
        
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        result = await self.db.scraper_cache.delete_many({
            "created_at": {"$lt": cutoff_date}
        })
        
        logger.info(f"Cache de scraping limpo: {result.deleted_count} entradas")
        return result.deleted_count
    
    async def send_weekly_ai_report(self) -> bool:
        """
        Envia relatório de extracções de IA aos administradores.
        Respeita a configuração de periodicidade definida pelo admin.
        
        Returns:
            True se o email foi enviado, False caso contrário
        """
        today = datetime.now(timezone.utc)
        current_weekday = today.weekday()
        current_day_of_month = today.day
        
        # Obter configuração do relatório
        config_doc = await self.db.system_config.find_one(
            {"type": "ai_report_config"},
            {"_id": 0}
        )
        
        config = config_doc.get("config", {}) if config_doc else {}
        
        # Valores padrão
        enabled = config.get("enabled", True)
        frequency = config.get("frequency", "weekly")
        send_day = config.get("send_day", 0)  # Segunda-feira
        recipients_type = config.get("recipients_type", "admins")
        custom_recipients = config.get("custom_recipients", [])
        include_insights = config.get("include_insights", True)
        include_charts = config.get("include_charts", True)
        
        # Verificar se está habilitado
        if not enabled or frequency == "disabled":
            logger.info("Relatório de IA desactivado nas configurações")
            return False
        
        # Verificar se é o momento certo para enviar
        should_send = False
        period_days = 7  # Período padrão para relatório semanal
        
        if frequency == "daily":
            # Enviar todos os dias na hora configurada
            should_send = True
            period_days = 1
        elif frequency == "weekly":
            # Enviar apenas no dia da semana configurado
            should_send = current_weekday == send_day
            period_days = 7
        elif frequency == "monthly":
            # Enviar no primeiro dia do mês
            should_send = current_day_of_month == 1
            period_days = 30
        
        if not should_send:
            freq_label = {"daily": "diário", "weekly": "semanal", "monthly": "mensal"}.get(frequency, frequency)
            logger.info(f"Não é o momento do relatório {freq_label} - ignorando")
            return False
        
        logger.info(f"A gerar e enviar relatório de IA ({frequency})...")
        
        # Gerar dados do relatório
        period_start = today - timedelta(days=period_days)
        prev_period_start = today - timedelta(days=period_days * 2)
        
        # Buscar extracções
        processes = await self.db.processes.find(
            {"ai_extraction_history": {"$exists": True, "$ne": []}},
            {"_id": 0, "ai_extraction_history": 1}
        ).to_list(None)
        
        this_period_extractions = []
        prev_period_extractions = []
        
        for proc in processes:
            for extraction in proc.get("ai_extraction_history", []):
                extracted_at = extraction.get("extracted_at", "")
                if extracted_at:
                    try:
                        ext_date = datetime.fromisoformat(extracted_at.replace("Z", "+00:00"))
                        if ext_date >= period_start:
                            this_period_extractions.append(extraction)
                        elif ext_date >= prev_period_start:
                            prev_period_extractions.append(extraction)
                    except Exception:
                        pass
        
        # Calcular métricas
        total_this_period = len(this_period_extractions)
        successful_this_period = sum(1 for e in this_period_extractions if e.get("extracted_data"))
        total_prev_period = len(prev_period_extractions)
        successful_prev_period = sum(1 for e in prev_period_extractions if e.get("extracted_data"))
        
        success_rate = (successful_this_period / total_this_period * 100) if total_this_period > 0 else 0
        prev_success_rate = (successful_prev_period / total_prev_period * 100) if total_prev_period > 0 else 0
        
        doc_variation = ((total_this_period - total_prev_period) / total_prev_period * 100) if total_prev_period > 0 else 0
        success_variation = success_rate - prev_success_rate
        
        # Contagem por tipo de documento
        doc_type_counts = {}
        for extraction in this_period_extractions:
            doc_type = extraction.get("document_type", "outro")
            doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1
        
        # Top campos extraídos
        field_counts = {}
        for extraction in this_period_extractions:
            extracted_data = extraction.get("extracted_data", {})
            if isinstance(extracted_data, dict):
                for field, value in extracted_data.items():
                    if value:
                        field_counts[field] = field_counts.get(field, 0) + 1
        
        top_fields = sorted(field_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Labels de frequência
        freq_labels = {"daily": "Diário", "weekly": "Semanal", "monthly": "Mensal"}
        period_label = freq_labels.get(frequency, "Semanal")
        
        # Mapear nomes
        doc_type_labels = {
            "cc": "Cartão de Cidadão",
            "recibo_vencimento": "Recibo de Vencimento",
            "irs": "Declaração IRS",
            "contrato_trabalho": "Contrato de Trabalho",
            "cpcv": "CPCV",
            "caderneta_predial": "Caderneta Predial",
            "simulacao": "Simulação de Crédito",
            "extrato_bancario": "Extrato Bancário",
            "outro": "Outro Documento",
        }
        
        field_labels = {
            "personal_data.nome": "Nome Completo",
            "personal_data.nif": "NIF",
            "personal_data.cc_number": "Nº CC",
            "financial_data.rendimento_mensal": "Rendimento Mensal",
            "financial_data.entidade_patronal": "Entidade Patronal",
            "real_estate_data.valor_imovel": "Valor do Imóvel",
            "client_name": "Nome do Cliente",
            "client_email": "Email",
        }
        
        # Gerar HTML do email
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #0f766e 0%, #115e59 100%); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .header p {{ margin: 10px 0 0 0; opacity: 0.9; font-size: 14px; }}
                .content {{ padding: 30px; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 25px; }}
                .stat-card {{ background: #f8fafc; border-radius: 8px; padding: 15px; text-align: center; }}
                .stat-value {{ font-size: 32px; font-weight: bold; color: #0f766e; }}
                .stat-label {{ font-size: 12px; color: #64748b; margin-top: 5px; }}
                .stat-change {{ font-size: 11px; margin-top: 3px; }}
                .stat-change.positive {{ color: #16a34a; }}
                .stat-change.negative {{ color: #dc2626; }}
                .section {{ margin-top: 25px; }}
                .section h3 {{ font-size: 14px; color: #334155; margin-bottom: 12px; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
                .progress-bar {{ background: #e2e8f0; border-radius: 4px; height: 8px; margin: 5px 0; overflow: hidden; }}
                .progress-fill {{ height: 100%; background: #0f766e; border-radius: 4px; }}
                .doc-item {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f1f5f9; }}
                .doc-name {{ font-size: 13px; color: #334155; }}
                .doc-count {{ font-size: 13px; font-weight: bold; color: #0f766e; }}
                .insight {{ background: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px 15px; margin: 10px 0; border-radius: 0 8px 8px 0; font-size: 13px; }}
                .insight.warning {{ background: #fffbeb; border-left-color: #f59e0b; }}
                .insight.info {{ background: #eff6ff; border-left-color: #3b82f6; }}
                .footer {{ background: #f8fafc; padding: 20px; text-align: center; font-size: 11px; color: #64748b; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Relatório {period_label} de IA</h1>
                    <p>{period_start.strftime('%d/%m/%Y')} - {today.strftime('%d/%m/%Y')}</p>
                </div>
                
                <div class="content">
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value">{total_this_period}</div>
                            <div class="stat-label">Documentos Analisados</div>
                            <div class="stat-change {'positive' if doc_variation >= 0 else 'negative'}">
                                {'+' if doc_variation >= 0 else ''}{doc_variation:.0f}% vs. período anterior
                            </div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{success_rate:.0f}%</div>
                            <div class="stat-label">Taxa de Sucesso</div>
                            <div class="stat-change {'positive' if success_variation >= 0 else 'negative'}">
                                {'+' if success_variation >= 0 else ''}{success_variation:.1f}pp vs. período anterior
                            </div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{successful_this_period}</div>
                            <div class="stat-label">Extracções com Sucesso</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{total_prev_period}</div>
                            <div class="stat-label">Total Período Anterior</div>
                        </div>
                    </div>
                    
                    {"".join([
                        f'<div class="insight {"warning" if success_rate < 70 else "info" if total_this_period == 0 else ""}">'
                        f'{self._get_weekly_insight(total_this_period, success_rate, doc_variation)}</div>'
                    ]) if include_insights else ''}
                    
                    <div class="section">
                        <h3>Por Tipo de Documento</h3>
                        {"".join([
                            f'''<div class="doc-item">
                                <span class="doc-name">{doc_type_labels.get(doc_type, doc_type)}</span>
                                <span class="doc-count">{count}</span>
                            </div>
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: {count/total_this_period*100 if total_this_period > 0 else 0:.0f}%"></div>
                            </div>'''
                            for doc_type, count in sorted(doc_type_counts.items(), key=lambda x: x[1], reverse=True)
                        ]) if doc_type_counts and include_charts else '<p style="color: #64748b; font-size: 13px;">Nenhum documento analisado</p>'}
                    </div>
                    
                    <div class="section">
                        <h3>Top 5 Campos Extraídos</h3>
                        {"".join([
                            f'<div class="doc-item"><span class="doc-name">{field_labels.get(field, field)}</span><span class="doc-count">{count}</span></div>'
                            for field, count in top_fields
                        ]) if top_fields and include_charts else '<p style="color: #64748b; font-size: 13px;">Nenhum campo extraído</p>'}
                    </div>
                </div>
                
                <div class="footer">
                    <p>Este relatório foi gerado automaticamente pelo PowerCell</p>
                    <p>Power Real Estate & Precision Crédito</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Obter lista de destinatários baseado na configuração
        recipient_emails = []
        
        if recipients_type == "admins":
            # Apenas administradores e CEOs
            from services.role_query import deep_role_in_filter
            users = await self.db.users.find(
                {"$and": [deep_role_in_filter(["admin", "ceo"]), {"is_active": {"$ne": False}}]},
                {"_id": 0, "email": 1, "name": 1}
            ).to_list(50)
            recipient_emails = [u["email"] for u in users if u.get("email")]
            
        elif recipients_type == "all_staff":
            # Toda a equipa activa
            users = await self.db.users.find(
                {"is_active": {"$ne": False}, "email": {"$exists": True, "$ne": None}},
                {"_id": 0, "email": 1}
            ).to_list(100)
            recipient_emails = [u["email"] for u in users if u.get("email")]
            
        elif recipients_type == "custom":
            # Lista personalizada de utilizadores
            if custom_recipients:
                users = await self.db.users.find(
                    {"id": {"$in": custom_recipients}, "is_active": {"$ne": False}},
                    {"_id": 0, "email": 1}
                ).to_list(50)
                recipient_emails = [u["email"] for u in users if u.get("email")]
        
        if not recipient_emails:
            logger.warning("Nenhum destinatário encontrado para o relatório de IA")
            return False
        
        # Enviar email usando o serviço de email existente
        try:
            from services.email_service import send_email
            
            result = await send_email(
                account_name="precision",  # Usar conta principal
                to_emails=recipient_emails,
                subject=f"Relatório {period_label} IA - {period_start.strftime('%d/%m')} a {today.strftime('%d/%m/%Y')}",
                body=f"Relatório {period_label.lower()} de extracções de IA.\n\nDocumentos analisados: {total_this_period}\nTaxa de sucesso: {success_rate:.1f}%",
                body_html=html_content
            )
            
            if result.get("success"):
                logger.info(f"Relatório {period_label.lower()} de IA enviado para {len(recipient_emails)} destinatário(s)")
                return True
            else:
                logger.error(f"Falha ao enviar relatório: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar relatório de IA: {e}")
            return False
    
    async def send_weekly_ceo_report(self) -> bool:
        """
        Envia o relatório semanal de produtividade da equipa ao CEO.

        Corre todas as Segundas-feiras às ~06:00 (quando run_all_tasks
        é invocado pelo worker/scheduler). Gera o relatório via
        analytics_service, formata HTML profissional e envia para o
        e-mail definido na variável de ambiente CEO_EMAIL (ou, em
        fallback, para todos os utilizadores com role=ceo).

        Returns:
            True se o email foi enviado, False caso contrário
        """
        today = datetime.now(timezone.utc)

        # Só enviar à Segunda-feira (weekday 0)
        if today.weekday() != 0:
            logger.info("[CEO Report] Hoje não é Segunda-feira — a ignorar")
            return False

        logger.info("[CEO Report] A gerar relatório semanal de produtividade para o CEO...")

        try:
            # 1. Gerar dados de agregação
            from services.analytics_service import generate_weekly_team_report, format_report_html

            report = await generate_weekly_team_report(self.db)

            # 2. Formatar HTML
            html_content = format_report_html(report)

            # 3. Determinar destinatário(s)
            ceo_email = os.environ.get("CEO_EMAIL", "").strip()
            recipient_emails: List[str] = []

            if ceo_email:
                # Suporta múltiplos e-mails separados por vírgula
                recipient_emails = [e.strip() for e in ceo_email.split(",") if e.strip()]

            if not recipient_emails:
                # Fallback: buscar utilizadores com role ceo na base de dados
                from services.role_query import deep_role_in_filter
                ceo_users = await self.db.users.find(
                    {"$and": [deep_role_in_filter(["ceo"]), {"is_active": {"$ne": False}}]},
                    {"_id": 0, "email": 1, "name": 1}
                ).to_list(10)
                recipient_emails = [u["email"] for u in ceo_users if u.get("email")]

            if not recipient_emails:
                logger.warning("[CEO Report] Nenhum destinatário encontrado — CEO_EMAIL não configurado e sem utilizadores CEO")
                return False

            # 4. Resumo em texto simples (fallback)
            summary = report.get("summary", {})
            period_start = datetime.fromisoformat(report["period_start"])
            period_end = datetime.fromisoformat(report["period_end"])

            plain_body = (
                f"Relatório Semanal de Produtividade\n"
                f"Período: {period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}\n\n"
                f"Processos Movidos: {summary.get('total_processes_moved', 0)}\n"
                f"Tarefas Concluídas: {summary.get('total_tasks_completed', 0)}\n"
                f"Tarefas Atrasadas: {summary.get('total_tasks_overdue', 0)}\n"
                f"Tarefas Pendentes: {summary.get('total_tasks_pending', 0)}\n"
                f"Utilizadores: {summary.get('total_users', 0)}\n"
            )

            # 5. Enviar e-mail
            from services.email_service import send_email

            result = await send_email(
                account_name="precision",
                to_emails=recipient_emails,
                subject=f"Relatório Semanal de Produtividade - {period_start.strftime('%d/%m')} a {period_end.strftime('%d/%m/%Y')}",
                body=plain_body,
                body_html=html_content,
                force_system=True,
                system_purpose="CEO_REPORT",
            )

            if result.get("success"):
                logger.info(
                    f"[CEO Report] Relatório enviado para {len(recipient_emails)} destinatário(s)"
                )
                return True
            else:
                logger.error(f"[CEO Report] Falha ao enviar: {result.get('error')}")
                return False

        except Exception as e:
            logger.error(f"[CEO Report] Erro ao gerar/enviar relatório: {e}")
            return False

    def _get_weekly_insight(self, total: int, success_rate: float, doc_variation: float) -> str:
        """Gera insight para o email."""
        if total == 0:
            return "ℹ️ Nenhum documento foi analisado neste período. Considere testar a funcionalidade de análise de documentos."
        
        if success_rate >= 90:
            return f"✅ Excelente desempenho! Taxa de sucesso de {success_rate:.0f}% nas extracções de IA."
        elif success_rate >= 70:
            return f"📊 Bom desempenho com taxa de {success_rate:.0f}%. Há espaço para melhorias na qualidade dos documentos."
        else:
            return f"⚠️ Taxa de sucesso baixa ({success_rate:.0f}%). Verifique a qualidade das imagens e PDFs enviados."
    
    async def check_stale_processes(self, stale_days: int = 14, urgent_days: int = 7) -> int:
        """
        Verificar processos sem atualização há mais de X dias.
        
        Cria notificações para os consultores/mediadores atribuídos quando um processo
        não é atualizado há mais de `stale_days` dias.
        
        Níveis:
        - > 14 dias sem atualização: Processo atrasado (notifica consultor + mediador + diretor)
        - > 7 dias sem atualização: Processo urgente (notifica consultor + mediador)
        
        Args:
            stale_days: Dias sem atualização para considerar atrasado (default 14)
            urgent_days: Dias sem atualização para considerar urgente (default 7)
        
        Returns:
            Número de notificações criadas
        """
        logger.info(f"A verificar processos sem atualização há mais de {urgent_days} dias...")
        
        today = datetime.now(timezone.utc)
        stale_cutoff = (today - timedelta(days=stale_days)).isoformat()
        urgent_cutoff = (today - timedelta(days=urgent_days)).isoformat()
        
        # Excluir processos em estados finais (concluídos, cancelados, etc.)
        final_statuses = ["concluido", "cancelado", "recusado", "desistiu", "escritura_feita"]
        
        # Buscar processos com updated_at antigo (ou sem updated_at, usar created_at)
        stale_processes = await self.db.processes.find({
            "status": {"$nin": final_statuses},
            "$or": [
                {"updated_at": {"$lte": stale_cutoff}},
                {"updated_at": {"$exists": False}, "created_at": {"$lte": stale_cutoff}}
            ]
        }, {"_id": 0, "id": 1, "client_name": 1, "status": 1, "consultor_id": 1, 
            "mediador_id": 1, "assigned_consultor_id": 1, "assigned_mediador_id": 1,
            "updated_at": 1, "created_at": 1}).to_list(500)
        
        urgent_processes = await self.db.processes.find({
            "status": {"$nin": final_statuses},
            "$or": [
                {"updated_at": {"$lte": urgent_cutoff, "$gt": stale_cutoff}},
                {"updated_at": {"$exists": False}, "created_at": {"$lte": urgent_cutoff, "$gt": stale_cutoff}}
            ]
        }, {"_id": 0, "id": 1, "client_name": 1, "status": 1, "consultor_id": 1, 
            "mediador_id": 1, "assigned_consultor_id": 1, "assigned_mediador_id": 1,
            "updated_at": 1, "created_at": 1}).to_list(500)
        
        notifications_created = 0
        
        # Processar processos atrasados (> stale_days)
        for process in stale_processes:
            last_update = process.get("updated_at") or process.get("created_at", "")
            try:
                last_date = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                days_since = (today - last_date).days
            except (ValueError, TypeError, AttributeError):
                days_since = stale_days
            
            users_to_notify = set()
            if process.get("consultor_id"):
                users_to_notify.add(process["consultor_id"])
            if process.get("assigned_consultor_id"):
                users_to_notify.add(process["assigned_consultor_id"])
            if process.get("mediador_id"):
                users_to_notify.add(process["mediador_id"])
            if process.get("assigned_mediador_id"):
                users_to_notify.add(process["assigned_mediador_id"])
            
            # Também notificar diretores para processos muito atrasados
            if days_since > 21:
                from services.role_query import deep_role_in_filter
                directors = await self.db.users.find(
                    {"$and": [deep_role_in_filter(["diretor", "ceo"]), {"is_active": {"$ne": False}}]},
                    {"_id": 0, "id": 1}
                ).to_list(10)
                for d in directors:
                    users_to_notify.add(d["id"])
            
            client_name = process.get("client_name", "Cliente")
            
            for user_id in users_to_notify:
                existing = await self.db.notifications.find_one({
                    "user_id": user_id,
                    "process_id": process.get("id"),
                    "type": "process_stale",
                    "created_at": {"$gte": (today - timedelta(days=1)).isoformat()}
                })
                
                if not existing:
                    await self.create_notification(
                        user_id=user_id,
                        message=f"Processo de {client_name} sem atualização há {days_since} dias. Requer atenção!",
                        notification_type="process_stale",
                        process_id=process.get("id"),
                        client_name=client_name,
                        link=f"/process/{process.get('id')}"
                    )
                    notifications_created += 1
        
        # Processar processos urgentes (> urgent_days mas < stale_days)
        for process in urgent_processes:
            last_update = process.get("updated_at") or process.get("created_at", "")
            try:
                last_date = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                days_since = (today - last_date).days
            except (ValueError, TypeError, AttributeError):
                days_since = urgent_days
            
            users_to_notify = set()
            if process.get("consultor_id"):
                users_to_notify.add(process["consultor_id"])
            if process.get("assigned_consultor_id"):
                users_to_notify.add(process["assigned_consultor_id"])
            if process.get("mediador_id"):
                users_to_notify.add(process["mediador_id"])
            if process.get("assigned_mediador_id"):
                users_to_notify.add(process["assigned_mediador_id"])
            
            client_name = process.get("client_name", "Cliente")
            
            for user_id in users_to_notify:
                existing = await self.db.notifications.find_one({
                    "user_id": user_id,
                    "process_id": process.get("id"),
                    "type": "process_urgent",
                    "created_at": {"$gte": (today - timedelta(days=1)).isoformat()}
                })
                
                if not existing:
                    await self.create_notification(
                        user_id=user_id,
                        message=f"Processo de {client_name} sem atualização há {days_since} dias.",
                        notification_type="process_urgent",
                        process_id=process.get("id"),
                        client_name=client_name,
                        link=f"/process/{process.get('id')}"
                    )
                    notifications_created += 1
        
        logger.info(f"Processos atrasados: {len(stale_processes)} atrasados, {len(urgent_processes)} urgentes, {notifications_created} notificações criadas")
        return notifications_created
    
    async def run_all_tasks(self):
        """Executar todas as tarefas agendadas."""
        logger.info("=" * 50)
        logger.info("INICIANDO TAREFAS AGENDADAS")
        logger.info(f"Data/Hora: {datetime.now(timezone.utc).isoformat()}")
        logger.info("=" * 50)
        
        try:
            await self.connect()
            
            # Executar tarefas
            docs_count = await self.check_expiring_documents()
            deadlines_count = await self.check_upcoming_deadlines()
            tasks_count = await self.check_tasks_due_soon()
            countdown_count = await self.check_pre_approval_countdown()
            waiting_count = await self.check_clients_waiting_too_long()
            watchdog_count = await self.check_document_expirations_watchdog()  # NOVA TAREFA
            monthly_count = await self.send_monthly_document_reminder()
            stale_count = await self.check_stale_processes()  # Processos atrasados
            cleanup_count = await self.cleanup_old_notifications()
            temp_files_count = await self.cleanup_temp_files()
            cache_count = await self.cleanup_scraper_cache()
            weekly_report_sent = await self.send_weekly_ai_report()
            ceo_report_sent = await self.send_weekly_ceo_report()

            logger.info("=" * 50)
            logger.info("RESUMO DAS TAREFAS")
            logger.info(f"- Alertas de documentos: {docs_count}")
            logger.info(f"- Alertas de prazos: {deadlines_count}")
            logger.info(f"- Alertas de tarefas: {tasks_count}")
            logger.info(f"- Alertas de countdown: {countdown_count}")
            logger.info(f"- Alertas clientes em espera: {waiting_count}")
            logger.info(f"- Watchdog expiração docs: {watchdog_count}")  # NOVA LINHA
            logger.info(f"- Lembretes mensais: {monthly_count}")
            logger.info(f"- Processos atrasados/urgentes: {stale_count}")
            logger.info(f"- Notificações limpas: {cleanup_count}")
            logger.info(f"- Ficheiros temp. limpos: {temp_files_count}")
            logger.info(f"- Cache scraper limpo: {cache_count}")
            logger.info(f"- Relatório AI semanal: {'Enviado' if weekly_report_sent else 'Não enviado (não é segunda-feira)'}")
            logger.info(f"- Relatório CEO semanal: {'Enviado' if ceo_report_sent else 'Não enviado (não é segunda-feira ou sem destinatário)'}")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"Erro nas tarefas agendadas: {e}")
            raise
        finally:
            await self.disconnect()

    async def auto_sync_emails(self) -> Dict[str, Any]:
        """
        Sincronização automática de emails para todas as caixas ativas.
        
        Executa sync_webmail_emails (caixa geral) e sync_user_emails
        (caixas pessoais configuradas). Os novos emails detetados
        geram automaticamente eventos WebSocket NEW_EMAIL para os
        utilizadores conectados.
        
        Returns:
            Dict com resumo da sincronização
        """
        # 🛑 KILL SWITCH: Só sincroniza se ENVIRONMENT=production ou EMAIL_SYNC_ENABLED=true.
        import os
        env = os.environ.get('ENVIRONMENT', '')
        sync_enabled = os.environ.get('EMAIL_SYNC_ENABLED', '').lower() == 'true'
        if env != 'production' and not sync_enabled:
            logger.info("[auto_sync_emails] BLOCKED — ENVIRONMENT != production e EMAIL_SYNC_ENABLED != true")
            return {"success": False, "error": "Email sync desactivado (ENVIRONMENT != production). Defina EMAIL_SYNC_ENABLED=true.", "total_synced": 0}

        logger.info("[Auto-Sync Email] Iniciando sincronização automática de emails...")
        
        total_synced = 0
        total_errors = 0
        results = {}
        
        def _is_policy_violation(error_str: str) -> bool:
            """Detectar erros de policy violation / rate limiting do servidor IMAP."""
            lower = error_str.lower()
            return any(kw in lower for kw in [
                "policy violation",
                "temporarily refused",
                "too many",
                "rate limit",
                "connection limit",
                "abuse",
                "blocked",
            ])
        
        try:
            # 1. Sincronizar caixa geral (global)
            try:
                from services.email_service import sync_webmail_emails
                global_result = await sync_webmail_emails(days=3, max_emails=50)
                total_synced += global_result.get("total_synced", 0)
                total_errors += global_result.get("total_errors", 0)
                results["global"] = {
                    "synced": global_result.get("total_synced", 0),
                    "duplicates": global_result.get("total_duplicates", 0),
                }
            except Exception as e:
                error_str = str(e)
                if _is_policy_violation(error_str):
                    logger.warning(f"[Auto-Sync Email] Caixa geral bloqueada por rate limit — a saltar este ciclo: {error_str[:200]}")
                else:
                    logger.error(f"[Auto-Sync Email] Erro na caixa geral: {e}")
                total_errors += 1
                results["global"] = {"error": str(e)}
            
            # Pausa entre sync global e sync pessoal (evitar rajadas de ligações IMAP)
            await asyncio.sleep(3)
            
            # 2. Sincronizar caixas pessoais dos utilizadores com email_config ativa
            try:
                users_with_email = await self.db.users.find(
                    {
                        "email_config.is_configured": True,
                        "is_active": {"$ne": False},
                    },
                    {"_id": 0, "id": 1, "email": 1, "email_config": 1}
                ).to_list(50)
                
                from services.email_service import sync_user_emails
                
                for u in users_with_email:
                    try:
                        user_result = await sync_user_emails(
                            user_id=u["id"],
                            days=3,
                            max_emails=50
                        )
                        total_synced += user_result.get("total_synced", 0)
                        total_errors += user_result.get("total_errors", 0)
                        
                        # Verificar se houve policy violation — parar de iterar contas
                        if user_result.get("error") and _is_policy_violation(user_result["error"]):
                            logger.warning(
                                f"[Auto-Sync Email] Policy violation detectada para {u.get('email', '?')} "
                                f"— a cancelar sync das restantes contas neste ciclo"
                            )
                            total_errors += 1
                            break
                    except Exception as e:
                        error_str = str(e)
                        if _is_policy_violation(error_str):
                            logger.warning(f"[Auto-Sync Email] Conta {u.get('email', '?')} bloqueada por rate limit — a parar iteração: {error_str[:200]}")
                            break
                        logger.debug(f"[Auto-Sync Email] Erro caixa pessoal {u.get('id', '?')}: {e}")
                        total_errors += 1
                    
                    # Delay entre contas para evitar ligações IMAP simultâneas (3s)
                    await asyncio.sleep(3)
                
                results["personal_accounts"] = len(users_with_email)
            except Exception as e:
                logger.error(f"[Auto-Sync Email] Erro ao buscar utilizadores com email: {e}")
                results["personal_accounts"] = {"error": str(e)}
            
            # Pausa antes de sync partilhado
            await asyncio.sleep(3)
            
            # 3. Sincronizar caixas partilhadas (indexação, etc.)
            try:
                from services.email_service import sync_shared_role_emails
                shared_result = await sync_shared_role_emails("indexacao", days=3, max_emails=50)
                total_synced += shared_result.get("total_synced", 0)
                results["shared_indexacao"] = {
                    "synced": shared_result.get("total_synced", 0),
                }
            except Exception as e:
                error_str = str(e)
                if _is_policy_violation(error_str):
                    logger.warning(f"[Auto-Sync Email] Caixa partilhada bloqueada por rate limit: {error_str[:200]}")
                else:
                    logger.debug(f"[Auto-Sync Email] Erro caixa partilhada indexação: {e}")
            
        except Exception as e:
            logger.error(f"[Auto-Sync Email] Erro geral: {e}")
            total_errors += 1
        
        logger.info(
            f"[Auto-Sync Email] Concluído: {total_synced} novos emails, "
            f"{total_errors} erros"
        )
        
        return {
            "total_synced": total_synced,
            "total_errors": total_errors,
            "results": results,
        }


async def run_email_auto_sync(interval_seconds: int = 180):
    import os
    env = os.environ.get('ENVIRONMENT', '')
    sync_enabled = os.environ.get('EMAIL_SYNC_ENABLED', '').lower() == 'true'
    if env != 'production' and not sync_enabled:
        logger.info("[run_email_auto_sync] BLOCKED — ENVIRONMENT != production e EMAIL_SYNC_ENABLED != true")
        return  # Aborta em DEV a menos que EMAIL_SYNC_ENABLED=true

    # Aguardar 30s antes da primeira execução para dar tempo ao server arrancar
    await asyncio.sleep(30)
    
    service = ScheduledTasksService()
    
    while True:
        try:
            await service.connect()
            await service.auto_sync_emails()
        except asyncio.CancelledError:
            logger.info("[Email Auto-Sync] Cancelado, a sair do loop")
            break
        except Exception as e:
            logger.error(f"[Email Auto-Sync] Erro no ciclo: {e}")
        finally:
            await service.disconnect()
        
        # Jitter: adicionar variação aleatória de 0-60s para evitar que
        # múltiplas instâncias sincronizem ao mesmo tempo
        jitter = random.randint(0, 60)
        await asyncio.sleep(interval_seconds + jitter)


async def run_daemon(interval_hours: int = 24):
    """
    Executar tarefas em loop (modo daemon).
    Por defeito, executa a cada 24 horas.
    """
    # KILL SWITCH — Só permite daemon em ENVIRONMENT=production ou EMAIL_SYNC_ENABLED=true
    import os
    env = os.environ.get('ENVIRONMENT', 'dev')
    sync_enabled = os.environ.get('EMAIL_SYNC_ENABLED', '').lower() == 'true'
    if env != 'production' and not sync_enabled:
        logger.warning("[BLOCK] run_daemon BLOCKED — ENVIRONMENT != production e EMAIL_SYNC_ENABLED != true — daemon will NOT start")
        return

    service = ScheduledTasksService()
    
    while True:
        try:
            await service.run_all_tasks()
        except asyncio.CancelledError:
            logger.info("[Daemon] Cancelado, a sair do loop")
            break
        except Exception as e:
            logger.error(f"Erro no daemon: {e}")
        
        # Aguardar próxima execução
        next_run = datetime.now() + timedelta(hours=interval_hours)
        logger.info(f"Próxima execução: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        await asyncio.sleep(interval_hours * 3600)


async def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description='PowerCell - Tarefas Agendadas')
    parser.add_argument('--daemon', action='store_true', help='Executar em modo daemon (loop contínuo)')
    parser.add_argument('--interval', type=int, default=24, help='Intervalo em horas (para daemon)')
    
    args = parser.parse_args()
    
    if args.daemon:
        logger.info("Iniciando em modo daemon...")
        await run_daemon(args.interval)
    else:
        service = ScheduledTasksService()
        await service.run_all_tasks()


if __name__ == "__main__":
    asyncio.run(main())
