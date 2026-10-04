"""Shared helpers for CRM visits (calendar / scraper / portal sync).

Extraído de `routes/visits.py`. Prefer `visit_*` (not `visits_*`) and do
**not** collide with existing `portal_client_visits.py`.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)


async def carimbo_da_visita(
    process: dict | None, user: dict | None = None
) -> dict:
    """O carimbo de tenant a gravar numa visita nova (Lote 9, D-21).

    PONTO ÚNICO PARA OS DOIS ESCRITORES
    ===================================
    Havia dois, com origens DIFERENTES para o mesmo campo: a criação pela
    equipa gravava `user.get("company_id")` — que o documento de
    utilizador **não tem** (tem `company`, o NOME; o `company_id` vive no
    UCR) — e o Portal gravava o `company_id` do processo. Uma das duas
    estava sempre vazia, e `network_id` não existia em sítio nenhum.

    **O PROCESSO é a autoridade, não quem grava.** Uma visita é sempre
    sobre um processo, e o processo já leva o carimbo certo desde o Lote
    4. Derivar do utilizador deixava a visita na empresa DELE, que pode
    ser outra empresa da mesma rede — e no Portal não há utilizador de
    equipa nenhum de quem derivar.

    Recurso: sem processo carimbado, usa-se o `resolve_tenant_stamp` do
    utilizador (caminho da equipa). Sem nenhum dos dois devolve `{}` —
    **meio carimbo é pior do que nenhum**, porque carimbar a rede errada
    é permanente, e sem carimbo a visita cai na pilha por carimbar, que a
    migração resolve depois.
    """
    from services.tenant_network import CAMPO_REDE, resolve_tenant_stamp

    rede = str((process or {}).get(CAMPO_REDE) or "").strip()
    if rede:
        carimbo = {
            "company_id": (process or {}).get("company_id"),
            "company_name": (process or {}).get("company_name"),
            CAMPO_REDE: rede,
        }
        return {k: v for k, v in carimbo.items() if v}

    if user:
        try:
            return await resolve_tenant_stamp(user) or {}
        except Exception as exc:  # observa, não intercepta
            logger.warning("[VISITS] Falha a resolver o carimbo: %s", exc)
    return {}


#: A projecção mínima de um processo para carimbar e enriquecer a visita.
#: Escrita aqui para os dois escritores não divergirem: um projecção sem
#: `network_id` fazia o carimbo cair sempre no recurso do utilizador, em
#: silêncio.
PROJECCAO_DO_PROCESSO = {
    "_id": 0,
    "id": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "status": 1,
    "assigned_consultor_id": 1,
    "process_number": 1,
    "company_id": 1,
    "company_name": 1,
    "network_id": 1,
}


async def _create_calendar_event_for_visit(visit: dict):
    """
    Cria um registo na coleção de deadlines (calendário do CRM)
    quando uma visita transita para 'agendada'.

    Título: 'Visita Imóvel: [Nome do Imóvel]'
    Associado ao consultor e ao processo.
    """
    try:
        deadline_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        property_name = visit.get("property_title") or "Imóvel"
        scheduled_date = visit.get("scheduled_date")
        client_name_suffix = ""
        client_name_val = visit.get("client_name", "")
        if client_name_val:
            client_name_suffix = f" — {client_name_val}"

        consultor_id = visit.get("consultor_id")
        process_id = visit.get("process_id") or visit.get("client_id")  # process_id explícito ou fallback para client_id

        assigned_users = [uid for uid in [consultor_id] if uid]

        deadline_doc = {
            "id": deadline_id,
            "process_id": process_id,
            "visit_id": visit.get("id"),  # Referência cruzada
            "title": f"Visita Imóvel: {property_name}",
            "description": (
                f"Visita agendada a '{property_name}'{client_name_suffix}"
                f"\nNotas: {visit.get('notes', '—')}"
            ),
            "due_date": scheduled_date or now,
            "priority": "alta",
            "completed": False,
            "created_by": consultor_id or "system",
            "created_at": now,
            "assigned_user_ids": assigned_users,
            "source": "visit_schedule",
            "assigned_consultor_id": consultor_id,
            "assigned_mediador_id": None,
        }

        await db.deadlines.insert_one(deadline_doc)
        logger.info(f"[VISITS] Evento de calendário criado: {deadline_id} para visita {visit.get('id')}")
        return deadline_id

    except Exception as e:
        logger.warning(f"[VISITS] Erro ao criar evento de calendário: {e}")
        return None


async def _remove_calendar_event_for_visit(visit_id: str):
    """
    Remove o evento de calendário associado a uma visita
    quando é cancelada ou recusada.
    """
    try:
        result = await db.deadlines.delete_many({"visit_id": visit_id})
        if result.deleted_count > 0:
            logger.info(f"[VISITS] {result.deleted_count} evento(s) de calendário removido(s) para visita {visit_id}")
    except Exception as e:
        logger.warning(f"[VISITS] Erro ao remover evento de calendário: {e}")


async def _update_portal_visit_status(visit: dict, new_status: str, scheduled_date: str = None):
    """
    Atualiza o estado da visita no Portal do Cliente.

    Quando a visita é agendada, define a data oficial.
    Quando é recusada/cancelada, atualiza o estado no portal.
    """
    try:
        process_id = visit.get("process_id") or visit.get("client_id")  # process_id explícito ou fallback
        visit_id = visit.get("id")

        update_fields = {
            "portal_status": new_status,
            "portal_updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if new_status == "agendada" and scheduled_date:
            update_fields["portal_scheduled_date"] = scheduled_date

        if new_status in ("cancelada", "recusada"):
            update_fields["portal_cancelled_at"] = datetime.now(timezone.utc).isoformat()
            update_fields.pop("portal_scheduled_date", None)

        await db.visits.update_one(
            {"id": visit_id},
            {"$set": update_fields}
        )

        # Notificar via WebSocket para a sala do processo
        try:
            from services.websocket_manager import WSEventType
            from services.realtime_delivery import entregar_na_sala, sala_do_processo
            ws_data = {
                "visit_id": visit_id,
                "status": new_status,
                "property_title": visit.get("property_title", "Imóvel"),
            }
            if scheduled_date:
                ws_data["scheduled_date"] = scheduled_date

            await entregar_na_sala(
                sala_do_processo(process_id),
                WSEventType.PORTAL_MESSAGE,
                {"type": "visit_status_update", **ws_data},
            )
        except Exception as ws_err:
            logger.debug(f"[VISITS] Erro ao notificar portal via WS: {ws_err}")

        logger.info(f"[VISITS] Portal atualizado: visita {visit_id} → {new_status}")

    except Exception as e:
        logger.warning(f"[VISITS] Erro ao atualizar portal: {e}")


async def _run_scraper_for_visit(visit_id: str, url: str):
    """Extrai os dados do imóvel e grava-os na visita (caminho do CRM).

    LOTE 9 (D-23) — ESTE MAPEADOR ERA ESCRITO À MÃO, E JÁ DIVERGIA
    Havia dois — este e o `_background_visit_scraper_and_notify` do
    Portal — a traduzir o MESMO resultado para os MESMOS campos. E já
    divergiam: o do Portal guardava `raw_data`, este não, pelo que uma
    visita criada no CRM perdia também `quartos`, `casas_banho`,
    `certificado_energetico`, `ano_construcao`, `descricao` e
    `referencia`. Os dois passaram a derivar de `ficha_do_imovel`.
    """
    from services.visit_property_extract import (
        VEREDICTO_ERRO,
        VEREDICTO_SEM_DADOS,
        ficha_do_imovel,
    )

    try:
        from services.property_scraper import extract_property_data
        scraped_result = await extract_property_data(url)
    except Exception as exc:
        logger.warning("[VISITS] Scraper rebentou para a visita %s: %s",
                       visit_id, exc)
        scraped_result = None

    agora = datetime.now(timezone.utc).isoformat()
    ficha = ficha_do_imovel(scraped_result, url=url, agora=agora)

    try:
        await db.visits.update_one({"id": visit_id}, {"$set": ficha.campos})
    except Exception as exc:
        logger.warning("[VISITS] Erro ao gravar a extracção da visita %s: %s",
                       visit_id, exc)
        return

    if ficha.veredicto == VEREDICTO_ERRO:
        logger.warning("[VISITS] Extracção falhou para a visita %s: %s",
                       visit_id, ficha.motivo)
    elif ficha.veredicto == VEREDICTO_SEM_DADOS:
        # O terceiro veredicto, que não existia: um anúncio que responde
        # 200 com tudo vazio contava como sucesso, e a visita ficava sem
        # um único dado — indistinguível de um imóvel sem informação.
        logger.warning("[VISITS] Visita %s: %s (%s)",
                       visit_id, ficha.motivo, url)
    else:
        logger.info("[VISITS] Extracção concluída para a visita %s", visit_id)
