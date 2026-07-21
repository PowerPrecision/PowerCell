"""
Criação de pedidos de documentos via portal (staff → cliente).

Extraído de `routes/documents.py` (`create_portal_document_request`).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.document_constants import DOCUMENT_CATEGORY_MAP

logger = logging.getLogger(__name__)

_ACTIVE_PORTAL_STATUSES = [
    "REQUESTED",
    "PENDING",
    "UPLOADED",
    "SUBMITTED",
    "RECEIVED",
    "requested",
    "pending",
    "uploaded",
    "submitted",
    "received",
]

_OUTROS_ALIASES = ("Outros", "outro", "other", "outros")


def normalize_portal_category(category: Any) -> str:
    """Garante category string válida no DOCUMENT_CATEGORY_MAP (fallback Outros)."""
    if isinstance(category, dict):
        category = category.get("value", category.get("label", "Outros"))
    if not isinstance(category, str):
        category = str(category) if category is not None else "Outros"
    if category not in DOCUMENT_CATEGORY_MAP:
        return "Outros"
    return category


def coerce_optional_str(value: Any) -> Optional[str]:
    """Converte notes/custom_label object → string (ou None)."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("label", value.get("value", str(value)))
    return str(value)


def build_portal_duplicate_query(process_id: str, category: str) -> dict:
    """Query Mongo para detectar pedido portal activo da mesma categoria."""
    return {
        "process_id": process_id,
        "$and": [
            {
                "$or": [
                    {"category": category},
                    {"category.value": category},
                    {"category.label": category},
                ]
            },
            {
                "$or": [
                    {"source": {"$in": ["admin_request", "client_portal"]}},
                    {"source": {"$exists": False}},
                ]
            },
        ],
        "status": {"$in": _ACTIVE_PORTAL_STATUSES},
    }


def build_portal_document_record(
    *,
    process_id: str,
    category: str,
    notes: Optional[str],
    custom_label: Optional[str],
    user: dict,
) -> dict:
    """Monta o documento a inserir em `documents`."""
    now = datetime.now(timezone.utc).isoformat()
    notes_val = coerce_optional_str(notes)
    if notes_val is None:
        notes_val = ""
    return {
        "id": str(uuid.uuid4()),
        "process_id": process_id,
        "category": category,
        "filename": None,
        "original_filename": None,
        "status": "REQUESTED",
        "notes": notes_val,
        "custom_label": coerce_optional_str(custom_label),
        "requested_by": user.get("id", "") or "",
        "requested_by_name": user.get("name", "") or "",
        "source": "admin_request",
        "file_size": None,
        "content_type": None,
        "uploaded_at": None,
        "created_at": now,
        "updated_at": now,
    }


async def _check_portal_duplicate(
    process_id: str,
    category: str,
    custom_label: Optional[str],
) -> None:
    """Raise 409 se já existir pedido activo equivalente."""
    try:
        existing = await db.documents.find_one(
            build_portal_duplicate_query(process_id, category)
        )
    except Exception as db_err:
        logger.warning(
            "[PORTAL-REQUESTS] Duplicate check query failed, "
            f"proceeding without check: {type(db_err).__name__}: {db_err}"
        )
        return

    if not existing:
        return

    is_outros = category in _OUTROS_ALIASES
    if is_outros and custom_label:
        existing_same_label = await db.documents.find_one(
            {
                "process_id": process_id,
                "category": {"$in": list(_OUTROS_ALIASES)},
                "custom_label": custom_label,
                "status": {"$in": _ACTIVE_PORTAL_STATUSES},
            }
        )
        if not existing_same_label:
            return
        raise HTTPException(
            status_code=409,
            detail=(
                f"Já existe um pedido de '{custom_label}' pendente "
                "para este processo."
            ),
        )

    cat_info = DOCUMENT_CATEGORY_MAP.get(category, {"label": category, "icon": "📎"})
    raise HTTPException(
        status_code=409,
        detail=(
            f"Já existe um pedido de '{cat_info.get('label', category)}' "
            "pendente para este processo."
        ),
    )


async def run_create_portal_document_request(
    process_id: str,
    *,
    category: Any,
    notes: Any = None,
    custom_label: Any = None,
    user: dict,
) -> dict:
    """
    Cria pedido de documento via portal (status REQUESTED).

    Returns:
        Payload `{success, document}` com label/icon da categoria.
    """
    logger.info(
        f"[PORTAL-REQUESTS] Creating request for process_id={process_id}, "
        f"category={category!r}, notes={notes!r}, custom_label={custom_label!r}, "
        f"user={user.get('id', '?')}"
    )

    if not process_id or not str(process_id).strip():
        raise HTTPException(status_code=400, detail="ID do processo inválido")

    try:
        process = await db.processes.find_one({"id": process_id})
    except Exception as db_err:
        logger.error(
            f"[PORTAL-REQUESTS] MongoDB find process failed for {process_id}: "
            f"{type(db_err).__name__}: {db_err}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Erro ao aceder à base de dados: {type(db_err).__name__}",
        )
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    category_norm = normalize_portal_category(category)
    custom_label_val = coerce_optional_str(custom_label)

    await _check_portal_duplicate(process_id, category_norm, custom_label_val)

    doc = build_portal_document_record(
        process_id=process_id,
        category=category_norm,
        notes=notes,
        custom_label=custom_label_val,
        user=user,
    )

    try:
        insert_result = await db.documents.insert_one(doc)
    except Exception as insert_err:
        logger.error(
            f"[PORTAL-REQUESTS] MongoDB insert failed for process {process_id}: "
            f"{type(insert_err).__name__}: {insert_err}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao inserir documento: {type(insert_err).__name__}",
        )
    if not insert_result.inserted_id:
        raise HTTPException(
            status_code=500,
            detail="Erro ao inserir documento na base de dados",
        )

    # Motor mutates `doc` with ObjectId `_id` — strip before JSON response
    doc.pop("_id", None)

    try:
        if user and user.get("role") != "indexacao":
            await db.history.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "process_id": process_id,
                    "user_id": doc["requested_by"],
                    "user_name": doc["requested_by_name"],
                    "action": f"Documento solicitado via portal: {category_norm}",
                    "field": "portal_document_requested",
                    "old_value": None,
                    "new_value": category_norm,
                    "created_at": doc["created_at"],
                }
            )
    except Exception as hist_err:
        logger.warning(f"Failed to write audit log: {hist_err}")

    cat_info = DOCUMENT_CATEGORY_MAP.get(
        category_norm, {"label": category_norm, "icon": "📎"}
    )
    return {
        "success": True,
        "document": {
            **doc,
            "category_label": cat_info.get("label", category_norm),
            "category_icon": cat_info.get("icon", "📎"),
        },
    }
