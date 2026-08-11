"""Annotations CRUD/mutate handlers.

Extraído de `routes/annotations.py`.
Do **not** overwrite services/annotation_service.py.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from models.annotation import AnnotationCreate, AnnotationUpdate
from services import annotation_service
from utils.input_sanitization import sanitize_string

logger = logging.getLogger(__name__)


async def run_create_annotation(data: AnnotationCreate, user: dict):
    try:
        dump = data.model_dump()
        if dump.get("comment"):
            dump["comment"] = sanitize_string(dump["comment"], max_length=5000)
        if dump.get("document_name"):
            dump["document_name"] = sanitize_string(dump["document_name"], max_length=1000)

        return await annotation_service.create_annotation(
            data=dump,
            author_id=user["id"],
            author_name=user.get("name", user.get("email", "Utilizador")),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar anotação: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao criar anotação")


async def run_update_annotation(annotation_id: str, data: AnnotationUpdate, user: dict):
    try:
        update_data = data.model_dump(exclude_none=True)
        if update_data.get("comment"):
            update_data["comment"] = sanitize_string(update_data["comment"], max_length=5000)

        updated = await annotation_service.update_annotation(
            annotation_id=annotation_id,
            data=update_data,
            user_id=user["id"],
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Anotação não encontrada")

        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar anotação {annotation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar anotação")


async def run_delete_annotation(annotation_id: str, user: dict):
    try:
        success = await annotation_service.delete_annotation(
            annotation_id=annotation_id,
            user_id=user["id"],
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Anotação não encontrada ou sem permissão para eliminar",
            )

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao eliminar anotação {annotation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao eliminar anotação")


async def run_resolve_annotation(annotation_id: str, body: dict, user: dict):
    try:
        resolved = body.get("resolved")
        if resolved is None or not isinstance(resolved, bool):
            raise HTTPException(
                status_code=400,
                detail="Campo 'resolved' é obrigatório e deve ser booleano (true/false)",
            )

        updated = await annotation_service.resolve_annotation(
            annotation_id=annotation_id,
            user_id=user["id"],
            user_name=user.get("name", user.get("email", "Utilizador")),
            resolved=resolved,
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Anotação não encontrada")

        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao resolver anotação {annotation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar estado da anotação")
