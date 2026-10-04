"""Pedidos de visita a imóveis via Portal.

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, BackgroundTasks

from database import db
from services.portal_assigned_users import get_all_assigned_user_ids as _get_all_assigned_user_ids
from services.notification_service import send_notification_with_preference_check
from services.websocket_manager import WSEventType
from services.realtime_delivery import entregar_na_sala, sala_do_processo
from services.visit_helpers import PROJECCAO_DO_PROCESSO, carimbo_da_visita

logger = logging.getLogger(__name__)


async def _background_visit_scraper_and_notify(visit_id: str, url: str, process_id: str, client_name: str, notify_process: dict):
    """
    Background task que:
    1. Invoca o scraper para extrair dados do imóvel (Idealista/Imovirtual)
    2. Atualiza o registo de visita com os dados extraídos
    3. Notifica a equipa atribuída ao processo
    
    Executa de forma assíncrona após o endpoint devolver 200 ao cliente.
    """
    # ── Extracção (D-23: ponto único, partilhado com o caminho do CRM) ──
    from services.visit_property_extract import (
        VEREDICTO_COMPLETA,
        ficha_do_imovel,
    )

    try:
        from services.property_scraper import extract_property_data
        scraped_result = await extract_property_data(url)
    except Exception as exc:
        logger.warning(f"[PORTAL-BG] Erro no scraper para URL {url}: {exc}")
        scraped_result = None

    agora = datetime.now(timezone.utc).isoformat()
    ficha = ficha_do_imovel(scraped_result, url=url, agora=agora)
    update_fields = ficha.campos

    try:
        await db.visits.update_one({"id": visit_id}, {"$set": update_fields})
        logger.info(f"[PORTAL-BG] Visita {visit_id} atualizada com dados do scraper")
    except Exception as e:
        logger.warning(f"[PORTAL-BG] Erro ao atualizar visita {visit_id}: {e}")

    if ficha.veredicto != VEREDICTO_COMPLETA:
        logger.warning(
            f"[PORTAL-BG] Visita {visit_id} sem dados utilizáveis: {ficha.motivo}"
        )

    # ── Notificar equipa atribuída ──
    assigned_ids = _get_all_assigned_user_ids(notify_process)
    process_number = notify_process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process_id[:8]
    
    # Usar o título final (após scraper) ou fallback
    final_title = update_fields.get("property_title", f"Imóvel de {url.split('//')[-1][:50]}...")
    
    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if user:
                await send_notification_with_preference_check(
                    user.get("email"),
                    "Pedido de Visita do Cliente",
                    f"O cliente {client_name} pediu uma visita a um imóvel no processo {process_ref}.",
                    notification_type="visit_request"
                )
                # In-app notification
                try:
                    from services.realtime_notifications import send_realtime_notification
                    await send_realtime_notification(
                        user_id=uid,
                        title="Pedido de Visita do Cliente",
                        message=f"O cliente {client_name} pediu uma visita a '{final_title}' no processo {process_ref}.",
                        notification_type="visit_request",
                        link="/visitas",
                        process_id=process_id,
                    )
                except Exception as notif_err:
                    logger.debug(f"Erro ao enviar notificação in-app para {uid}: {notif_err}")
        except Exception as e:
            logger.warning(f"[PORTAL-BG] Erro ao notificar utilizador {uid} sobre pedido de visita: {e}")
    
    # ── Broadcast WebSocket ──
    try:
        await entregar_na_sala(sala_do_processo(process_id), WSEventType.PORTAL_MESSAGE, {
            "id": visit_id,
            "process_id": process_id,
            "type": "visit_request",
            "client_name": client_name,
            "property_title": final_title,
            "url": url,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as ws_err:
        logger.debug(f"[PORTAL-BG] Erro ao broadcast pedido de visita via WS: {ws_err}")


async def run_request_portal_visit(data: dict, background_tasks: BackgroundTasks, client_data: dict):
    """
    Cliente pede uma visita a um imóvel através do Portal.
    
    Fluxo (v2 — non-blocking com BackgroundTasks):
    1. Recebe URL do anúncio do imóvel
    2. Procura o processo ativo do cliente e guarda o _id como process_id
    3. Cria o registo de visita na BD IMEDIATAMENTE com status 'solicitada'
    4. Coloca a execução do scraper (Idealista) em BackgroundTask
       (que atualizará a visita na BD depois de extrair foto/preço)
    5. Devolve status 200 IMEDIATAMENTE para libertar o frontend
    6. Notifica a equipa atribuída em background
    
    Body:
    - url: Link do imóvel (obrigatório)
    - process_id: ID do processo (opcional, usa o do token se não fornecido)
    - notes: Notas adicionais (opcional)
    """
    process = client_data["process"]
    token_process_id = client_data["process_id"]
    url = data.get("url", "").strip()
    notes = data.get("notes", "").strip()
    
    if not url:
        raise HTTPException(status_code=400, detail="O link do imóvel é obrigatório.")
    
    # ── 1. Procurar o processo ativo do cliente ──
    # O token do portal pode ter um process_id, mas vamos confirmar
    # procurando o processo ativo (não concluído/não cancelado).
    # Isto garante que a visita fica sempre associada ao processo correcto.
    active_process = None
    candidate_ids = [token_process_id]
    if data.get("process_id"):
        candidate_ids.insert(0, data.get("process_id"))
    
    for pid in candidate_ids:
        if not pid:
            continue
        found = await db.processes.find_one(
            {"id": pid, "status": {"$nin": ["concluido", "cancelado", "arquivado"]}},
            PROJECCAO_DO_PROCESSO
        )
        if found:
            active_process = found
            break
    
    # Fallback: procurar por NIF do cliente se não encontramos por ID
    if not active_process:
        client_nif = process.get("client_nif") or (process.get("personal_data") or {}).get("nif")
        if client_nif:
            active_process = await db.processes.find_one(
                {
                    "$or": [
                        {"client_nif": client_nif},
                        {"personal_data.nif": client_nif},
                    ],
                    "status": {"$nin": ["concluido", "cancelado", "arquivado"]},
                },
                PROJECCAO_DO_PROCESSO
            )
    
    if active_process:
        process_id = active_process["id"]
        client_name = active_process.get("client_name", process.get("client_name", "Cliente"))
        logger.info(f"[PORTAL] Processo ativo encontrado: {process_id} (status={active_process.get('status')})")
    else:
        process_id = token_process_id
        client_name = process.get("client_name", "Cliente")
        logger.warning(f"[PORTAL] Nenhum processo ativo encontrado para client_id={token_process_id}, a usar token process_id")
    
    # ── 2. Criar registo de visita IMEDIATAMENTE com status 'solicitada' ──
    # Não esperamos pelo scraper — a visita nasce com dados mínimos
    # e será enriquecida em background pela BackgroundTask.
    now = datetime.now(timezone.utc).isoformat()
    visit_id = str(uuid.uuid4())
    
    # Título provisório (será atualizado pelo scraper)
    property_title = f"Imóvel de {url.split('//')[-1][:50]}..."
    
    visit_doc = {
        "id": visit_id,
        "property_id": None,
        "property_title": property_title,
        "property_photo": None,
        "property_address": {},
        "client_id": process_id,
        "process_id": process_id,  # Explícito — processo ativo confirmado
        "client_name": client_name,
        "client_email": (active_process or process).get("client_email", ""),
        "client_phone": (active_process or process).get("client_phone", ""),
        "consultor_id": None,
        "consultor_name": None,
        "scheduled_date": None,
        "status": "solicitada",
        "notes": notes,
        "source": "portal_client",
        "scraped_url": url,
        "scraper_status": "pending",  # Será atualizado pela BackgroundTask
        "created_at": now,
        "updated_at": now,
        "created_by": "portal_client",
        # LOTE 9 (D-21) — o `company_id` do processo sozinho não bastava:
        # faltava a REDE, que é a fronteira de segurança. Vem do mesmo
        # ponto único que o escritor da equipa usa.
        **(await carimbo_da_visita(active_process or process)),
    }
    
    await db.visits.insert_one(visit_doc)
    
    # ── 3. Registar no histórico do processo ──
    try:
        from services.history import log_history
        await log_history(
            process_id,
            user={"id": None, "name": f"{client_name} (Portal)", "role": "client_portal"},
            action="VISIT_REQUESTED_BY_CLIENT",
            field="visita",
            old_value=None,
            new_value=f"Pedido de visita a imóvel ({url})"
        )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao registar histórico de visita: {e}")
    
    # ── 4. Colocar o scraper e as notificações em BackgroundTask ──
    # O scraper é lento (5-15s) — não deve bloquear a resposta ao cliente.
    notify_process = active_process if active_process else process
    background_tasks.add_task(
        _background_visit_scraper_and_notify,
        visit_id=visit_id,
        url=url,
        process_id=process_id,
        client_name=client_name,
        notify_process=notify_process,
    )
    
    logger.info(
        f"[PORTAL] Pedido de visita criado: {visit_id} — "
        f"Cliente {client_name}, URL {url}, Scraper em background"
    )
    
    # ── 5. Devolver 200 IMEDIATAMENTE ──
    visit_doc.pop("_id", None)
    return visit_doc


async def run_get_portal_visits(client_data: dict):
    """
    Lista todas as visitas ligadas a este processo/cliente.
    Inclui visitas pedidas pelo cliente e visitas agendadas pelo consultor.
    
    Endpoint consumido pelo Portal do Cliente.
    """
    process = client_data["process"]
    process_id = client_data["process_id"]
    
    try:
        visits = await db.visits.find(
            {"client_id": process_id},
            {"_id": 0, "scraped_data.raw_data": 0}  # Não enviar raw_data pesado
        ).sort("created_at", -1).limit(50).to_list(50)
        
        # Mapear status para labels client-friendly e enriquecer com data formatada
        status_labels = {
            "solicitada": "A aguardar agendamento",
            "agendada": "Agendada",
            "concluida": "Concluída",
            "cancelada": "Cancelada",
            "recusada": "Recusada",
        }
        
        for visit in visits:
            visit["status_label"] = status_labels.get(visit.get("status", ""), visit.get("status", ""))
            
            # Incluir data da visita confirmada (para o portal mostrar ao cliente)
            scheduled = visit.get("scheduled_date") or visit.get("portal_scheduled_date")
            if scheduled and visit.get("status") == "agendada":
                try:
                    dt = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
                    visit["formatted_date"] = dt.strftime("%d/%m/%Y às %H:%M")
                except Exception:
                    visit["formatted_date"] = scheduled
            
            # URL clicável do imóvel
            scraped_url = visit.get("scraped_url")
            if scraped_url:
                visit["property_url"] = scraped_url
        
        return {
            "visits": visits,
            "total": len(visits),
        }
    except Exception as e:
        logger.error(f"[PORTAL] Erro ao listar visitas: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar visitas. Tente novamente."
        )


