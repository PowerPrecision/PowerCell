"""GET /portal/status — status do processo para o cliente.

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from database import db
from services.portal_doc_categories import (
    DOCUMENT_CATEGORY_MAP,
    PORTAL_HIDDEN_CATEGORIES,
    DEFAULT_PENDING_CATEGORIES,
)
from services.portal_status_helpers import (
    _get_user_contact_info,
    _get_rgpd_status,
    _get_team_info,
)
from services.process_status import INACTIVE_STATUSES

logger = logging.getLogger(__name__)


async def run_get_portal_status(client_data: dict):
    """
    Retorna o status completo do processo para o Portal do Cliente.

    Dados incluídos:
    - Informações do processo (sem dados sensíveis)
    - Stepper dinâmico baseado no workflow (vindo da BD)
    - Documentos solicitados (status REQUESTED/PENDING)
    - Documentos já submetidos (status RECEIVED via upload ou scraper)
    - Contactos do consultor

    Documentos pendentes:
    - Primário: Docs com status REQUESTED/PENDING na BD (o admin solicitou)
    - Fallback: Se não existem docs solicitados, mostra categorias padrão
      que ainda não têm qualquer documento submetido
    """
    process = client_data.get("process")
    
    # Para access_code_session sem processo, mostrar checklist do cliente
    if not process:
        client_id = client_data.get("client_id")
        client = client_data.get("client") or {}
        client_name = client.get("nome") or ""

        requested_docs = []
        uploaded_docs = []
        if client_id:
            docs = await db.documents.find(
                {
                    "client_id": client_id,
                    "$or": [
                        {"process_id": None},
                        {"process_id": ""},
                        {"process_id": {"$exists": False}},
                    ],
                },
                {"_id": 0},
            ).to_list(200)
            for d in docs:
                status = (d.get("status") or "").upper()
                entry = {
                    "id": d.get("id"),
                    "category": d.get("category"),
                    "custom_label": d.get("custom_label") or d.get("notes"),
                    "filename": d.get("filename") or d.get("original_filename"),
                    "status": d.get("status"),
                    "source": d.get("source"),
                }
                if status in ("REQUESTED", "PENDING"):
                    requested_docs.append(entry)
                elif status in ("RECEIVED", "UPLOADED", "SUBMITTED", "VALIDATED"):
                    uploaded_docs.append(entry)

        return {
            "process": {
                "id": None,
                "client_name": client_name,
                "status": "pending_documents",
                "status_label": "Aguardando documentação",
                "status_color": "#94a3b8",
                "process_type": client.get("pending_process_type"),
            },
            "progress": {"percent": 0, "current_step": 0, "total_steps": 0},
            "stepper": [],
            "documents": {
                "requested": requested_docs,
                "uploaded": uploaded_docs,
                "received": uploaded_docs,
                "has_pending": len(requested_docs) > 0,
            },
            "rgpd": {"status": "none", "has_rgpd": False},
            "team": {"consultores": [], "mediadores": []},
            "consultor": None,
            "welcome_message": (
                "Complete o seu perfil e envie a documentação solicitada. "
                "O processo será criado automaticamente após os documentos obrigatórios."
            ),
            "has_process": False,
            "client_id": client_id,
        }
    
    process_id = process["id"]

    # ── Workflow statuses para o stepper ──
    # Buscar todos os statuses (incluindo hidden, para calcular progresso)
    all_statuses = await db.workflow_statuses.find(
        {}, {"_id": 0}
    ).sort("order", 1).to_list(100)

    current_status = process.get("status", "clientes_espera")
    current_status_label = current_status
    current_status_color = "#94a3b8"

    # Determinar label e cor do status atual
    # Usar portal_label se disponível (client-facing)
    for s in all_statuses:
        if s.get("name") == current_status:
            current_status_label = s.get("portal_label") or s.get("label", current_status)
            current_status_color = s.get("color", "#94a3b8")
            break

    # Excluir statuses terminais E ocultos no portal
    # Fix: Normalize process status filters — reutiliza a constante central
    # (com variações singular/plural) em vez de uma lista local.
    terminal_statuses = INACTIVE_STATUSES
    active_steps = [
        s for s in all_statuses
        if s.get("name") not in terminal_statuses
        and s.get("visible_in_portal", True) is not False
    ]
    total_active_steps = len(active_steps) if active_steps else 1

    # Posição atual e progresso — usar TODOS os active (não apenas visíveis)
    all_active = [s for s in all_statuses if s.get("name") not in terminal_statuses]
    current_order = 0
    for s in all_active:
        if s.get("name") == current_status:
            current_order = s.get("order", 0)
            break

    current_active_index = sum(1 for s in all_active if s.get("order", 0) < current_order)
    if any(s.get("name") == current_status for s in all_active):
        current_active_index = max(current_active_index, 1)

    progress_percent = min(100, int((current_active_index / len(all_active)) * 100)) if all_active else 100

    # ── Stepper data (apenas visíveis no portal) ──
    stepper = []
    for status in active_steps:
        is_current = status.get("name") == current_status
        is_completed = status.get("order", 0) < current_order

        # Usar portal_label se disponível, senão label, senão name
        display_label = status.get("portal_label") or status.get("label", status.get("name"))

        stepper.append({
            "id": status.get("name"),
            "label": display_label,
            "color": status.get("color", "#94a3b8"),
            "description": status.get("portal_description") or status.get("description", ""),
            "is_current": is_current,
            "is_completed": is_completed,
        })

    # ── Documentos solicitados (REQUESTED/PENDING) ──
    requested_docs = []
    requested_cursor = db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": ["REQUESTED", "PENDING", "requested", "pending"]},
            "source": {"$ne": "admin_received"},  # Exclude admin-marked received docs
            "category": {"$nin": list(PORTAL_HIDDEN_CATEGORIES)}  # Hide internal categories
        },
        {"_id": 0, "file_content": 0}
    ).sort("created_at", 1)

    async for doc in requested_cursor:
        cat = doc.get("category", "Outros")
        # Ensure cat is a string (backend may have stored objects)
        if isinstance(cat, dict):
            cat = cat.get("value", cat.get("label", "Outros"))
        cat_info = DOCUMENT_CATEGORY_MAP.get(cat, {"label": cat, "icon": "📎"})
        # Ensure notes is a string (may have been stored as an object)
        raw_notes = doc.get("notes", "")
        if isinstance(raw_notes, dict):
            raw_notes = raw_notes.get("label", raw_notes.get("value", str(raw_notes)))
        notes_str = str(raw_notes) if raw_notes is not None else ""

        # PACOTE AN: Para categoria "Outros", usar custom_label/description/custom_name
        # se existir (permite vários "Outros Documentos" com nomes diferentes).
        # Fallback para o label genérico "Outro Documento".
        display_label = cat_info["label"]
        if cat == "Outros" or cat.lower() in ("outro", "other", "outros"):
            display_label = (
                doc.get("custom_label")
                or doc.get("custom_name")
                or doc.get("description")
                or doc.get("title")
                or cat_info["label"]
            )

        requested_docs.append({
            "id": doc.get("id"),
            "category": cat,
            "label": display_label,
            "icon": cat_info["icon"],
            "notes": notes_str,
            "requested_at": doc.get("created_at", doc.get("uploaded_at", "")),
        })

    # ── Documentos submetidos (UPLOADED/SUBMITTED) ──
    uploaded_docs = []
    uploaded_cursor = db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": ["UPLOADED", "SUBMITTED", "uploaded", "submitted"]},
            "category": {"$nin": list(PORTAL_HIDDEN_CATEGORIES)}  # Hide internal categories
        },
        {"_id": 0, "file_content": 0}
    ).sort("uploaded_at", -1)

    async for doc in uploaded_cursor:
        cat = doc.get("category", "Outros")
        # Ensure cat is a string (backend may have stored objects)
        if isinstance(cat, dict):
            cat = cat.get("value", cat.get("label", "Outros"))
        cat_info = DOCUMENT_CATEGORY_MAP.get(cat, {"label": cat, "icon": "📎"})
        # Show custom_label for "Outros" category, otherwise use category label
        display_label = doc.get("custom_label") if cat == "Outros" and doc.get("custom_label") else cat_info["label"]
        uploaded_docs.append({
            "id": doc.get("id"),
            "filename": doc.get("original_filename", doc.get("filename", "")),
            "category": cat,
            "category_label": display_label,
            "icon": cat_info["icon"],
            "uploaded_at": doc.get("uploaded_at", ""),
            "file_size": doc.get("file_size"),
            "status": doc.get("status", "UPLOADED"),
            "s3_path": doc.get("s3_path") or doc.get("file_key"),
        })

    # ── Documentos recebidos pelo admin (marcados como RECEIVED) ──
    received_docs = []
    received_cursor = db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": ["RECEIVED", "received"]},
            "category": {"$nin": list(PORTAL_HIDDEN_CATEGORIES)}  # Hide internal categories
        },
        {"_id": 0, "file_content": 0}
    ).sort("updated_at", -1)

    async for doc in received_cursor:
        cat = doc.get("category", "Outros")
        # Ensure cat is a string (backend may have stored objects)
        if isinstance(cat, dict):
            cat = cat.get("value", cat.get("label", "Outros"))
        cat_info = DOCUMENT_CATEGORY_MAP.get(cat, {"label": cat, "icon": "📎"})
        received_docs.append({
            "id": doc.get("id"),
            "filename": doc.get("original_filename") or doc.get("filename") or cat_info["label"],
            "category": cat,
            "category_label": cat_info["label"],
            "icon": cat_info["icon"],
            "received_at": doc.get("reviewed_at", doc.get("updated_at", "")),
            "s3_path": doc.get("s3_path") or doc.get("file_key"),
            # PACOTE DE — histórico completo de ficheiros anexados a esta
            # categoria/pedido (cada upload acrescentado via $push no backend).
            # Permite ao frontend listar todos os ficheiros por categoria em
            # vez de mostrar apenas o mais recente (campo `s3_path` top-level).
            "attached_files": doc.get("attached_files") or [],
        })

    # ── Fallback: se não há docs REQUESTED, calcular pendentes por categoria ──
    has_pending = len(requested_docs) > 0
    if not has_pending:
        # Buscar TODOS os docs para saber quais categorias já foram submetidas
        all_docs_cursor = db.documents.find(
            {"process_id": process_id},
            {"_id": 0, "category": 1}
        )
        submitted_categories = set()
        async for doc in all_docs_cursor:
            if doc.get("category"):
                submitted_categories.add(doc["category"])

        # Cross-category mapping: se "Financeiros" foi submetido pelo scraper,
        # considerar "IRS" como satisfeita (o scraper Finanças guarda como "Financeiros")
        if "Financeiros" in submitted_categories:
            submitted_categories.add("IRS")

        for cat_key in DEFAULT_PENDING_CATEGORIES:
            if cat_key not in submitted_categories:
                cat_info = DOCUMENT_CATEGORY_MAP.get(cat_key, {"label": cat_key, "icon": "📎"})
                requested_docs.append({
                    "id": None,
                    "category": cat_key,
                    "label": cat_info["label"],
                    "icon": cat_info["icon"],
                    "notes": "",
                    "requested_at": None,
                })

        has_pending = len(requested_docs) > 0

    # ── Equipa atribuída (consultores + mediadores) ──
    team_info = await _get_team_info(process)

    # ── RGPD Status ──
    rgpd_info = await _get_rgpd_status(process_id)

    # ── Welcome message (from portal_settings, rendered with variables) ──
    welcome_message = None
    try:
        from routes.portal_settings import _get_portal_settings_doc, render_welcome_message
        settings_doc = await _get_portal_settings_doc()
        template = settings_doc.get("welcome_message_template", "")
        if template:
            consultor_name = team_info["consultores"][0]["name"] if team_info["consultores"] else "a sua equipa"
            empresa_name = process.get("company", "Power Precision")
            welcome_message = render_welcome_message(
                template=template,
                client_name=process.get("client_name", "Cliente"),
                consultor_name=consultor_name,
                empresa_name=empresa_name,
            )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao gerar welcome message: {type(e).__name__}")

    return {
        "process": {
            "id": process_id,
            "client_name": process.get("client_name", ""),
            "status": current_status,
            "status_label": current_status_label,
            "status_color": current_status_color,
            "process_type": process.get("process_type", "credito_habitacao"),
            "created_at": process.get("created_at"),
            "updated_at": process.get("updated_at"),
        },
        "progress": {
            "percent": progress_percent,
            "current_step": current_active_index,
            "total_steps": total_active_steps,
        },
        "stepper": stepper,
        "documents": {
            "requested": requested_docs,
            "uploaded": uploaded_docs,
            "received": received_docs,
            "has_pending": has_pending,
        },
        "rgpd": rgpd_info,
        "team": team_info,
        "consultor": team_info["consultores"][0] if team_info["consultores"] else None,
        "welcome_message": welcome_message,
    }


