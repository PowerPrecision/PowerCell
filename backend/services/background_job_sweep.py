"""
====================================================================
VARRIMENTO DE JOBS BLOQUEADOS — o ciclo do `background_job_monitor`
====================================================================
Lote 2, ponto 1 — extraído de `server.py`.

PORQUE É QUE SAIU DO `server.py`
  O trabalho do monitor estava DENTRO do `while` do
  `background_job_monitor`, logo não era chamável. O botão «Forçar
  Execução» do painel precisa de uma função, e a alternativa era escrever
  o varrimento uma segunda vez no endpoint — uma segunda definição de
  "correr o job", a divergir da primeira sem dar erro. É a forma do
  defeito que este projecto já viu em quatro eixos.

  Agora há UM ciclo: o laço de 30 minutos e o botão chamam o mesmo
  `varrer_jobs_bloqueados`, e o que o painel prova é o que o horário faz.

DETALHE QUE NÃO SE PODE PERDER
  A higiene do ZSET de presença continua a andar de boleia neste ciclo
  (Ponto 2 do Lote 4) em vez de ter temporizador próprio, e continua a
  não poder derrubar o varrimento: o `except` à volta dela é mudo de
  propósito — quem já saiu, já saiu, e a limpeza é só para o conjunto não
  crescer para sempre.

`server.py` reexporta as duas funções que vieram para cá, para não
quebrar nada que as importe de lá.
====================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from database import db

logger = logging.getLogger(__name__)

# Jobs sem actualização há mais do que isto são considerados bloqueados.
HORAS_ATE_CONSIDERAR_BLOQUEADO = 2


async def varrer_jobs_bloqueados(
    horas: int = HORAS_ATE_CONSIDERAR_BLOQUEADO,
) -> int:
    """Um ciclo completo do monitor. Devolve quantos jobs foram marcados.

    É este o corpo que o laço de 30 minutos corre e que o botão de
    execução forçada invoca — a mesma função, nunca duas.
    """
    limite = datetime.now(timezone.utc) - timedelta(hours=horas)
    bloqueados = await db.background_jobs.find({
        "status": {"$in": ["running", "pending"]},
        "updated_at": {"$lt": limite.isoformat()},
    }).to_list(100)

    await _tratar_jobs_bloqueados(bloqueados, horas)

    # Higiene do ZSET de presença: boleia neste ciclo, e nunca o derruba.
    try:
        from services.presenca import limpar_expirados

        saidos = await limpar_expirados()
        if saidos:
            logger.debug("[PRESENCA] %s entrada(s) expirada(s) removida(s)", saidos)
    except Exception:
        pass

    return len(bloqueados)


async def send_stuck_job_email(stuck_jobs: list):
    """Enviar email quando jobs ficam stuck."""
    try:
        # Buscar configuração de email do sistema
        config = await db.system_config.find_one({"type": "email_notifications"})
        if not config or not config.get("enabled"):
            logger.info("Notificações por email desactivadas")
            return
        
        admin_emails = config.get("admin_emails", [])
        if not admin_emails:
            # Buscar emails de admins
            from services.role_query import deep_role_filter
            admins = await db.users.find(deep_role_filter("admin"), {"email": 1}).to_list(10)
            admin_emails = [a["email"] for a in admins if a.get("email")]
        
        if not admin_emails:
            logger.warning("Nenhum email de admin configurado para notificações")
            return
        
        # Construir mensagem
        job_details = "\n".join([
            f"- {job.get('name', job.get('id', 'N/A'))} ({job.get('job_type', 'desconhecido')})"
            for job in stuck_jobs[:10]
        ])
        
        subject = f"⚠️ {len(stuck_jobs)} Jobs Bloqueados Detectados - CRM"
        body = f"""
Olá,

O sistema detectou {len(stuck_jobs)} job(s) bloqueado(s) que foram automaticamente marcados como falhados.

Jobs afectados:
{job_details}

Por favor verifique a página de Background Jobs para mais detalhes.

---
Esta é uma notificação automática do CRM.
        """.strip()
        
        # Tentar enviar email usando o serviço existente
        from services.email_service import send_email
        for email in admin_emails[:3]:  # Máximo 3 destinatários
            try:
                await send_email(
                    to_email=email,
                    subject=subject,
                    body=body
                )
                logger.info(f"Email de jobs stuck enviado para {email}")
            except (IOError, OSError, ValueError, ConnectionError) as email_err:
                logger.warning(f"Falha ao enviar email para {email}: {email_err}")
                
    except (IOError, OSError, ValueError, ConnectionError, KeyError) as email_global_err:
        logger.error(f"Erro ao enviar emails de jobs stuck: {email_global_err}")


async def _tratar_jobs_bloqueados(stuck_jobs: list, STUCK_THRESHOLD_HOURS: int):
    """Marca como falhados os jobs parados e avisa quem de direito.

    Extraído do corpo do ciclo para o envelope do batimento não precisar
    de indentar 50 linhas — e para o ciclo passar a ler-se de uma vez.
    """
    if stuck_jobs:
        logger.warning(f"⚠️ Encontrados {len(stuck_jobs)} jobs bloqueados há mais de {STUCK_THRESHOLD_HOURS}h")
        
        job_ids = [job.get("id") for job in stuck_jobs]
        
        # Marcar como failed
        await db.background_jobs.update_many(
            {"id": {"$in": job_ids}},
            {"$set": {
                "status": "failed",
                "error": f"Job marcado automaticamente como stuck após {STUCK_THRESHOLD_HOURS}h sem actividade",
                "auto_cleaned_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Criar notificação de sistema
        for job in stuck_jobs:
            try:
                await db.system_notifications.insert_one({
                    "type": "job_stuck",
                    "severity": "warning",
                    "title": "Job bloqueado detectado",
                    "message": f"Job '{job.get('name', job.get('id'))}' foi automaticamente marcado como falhado após {STUCK_THRESHOLD_HOURS}h sem actividade.",
                    "job_id": job.get("id"),
                    "job_type": job.get("job_type"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "read": False
                })
            except (IOError, OSError, ValueError) as notif_err:
                logger.error(f"Erro ao criar notificação para job stuck: {notif_err}")
        
        # Enviar email para admins
        await send_stuck_job_email(stuck_jobs)
        
        logger.info(f"✅ {len(stuck_jobs)} jobs stuck foram marcados como 'failed'")
