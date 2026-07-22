"""Annotations list/read handlers.

Extraído de `routes/annotations.py`.
Do **not** overwrite services/annotation_service.py.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from services import annotation_service

logger = logging.getLogger(__name__)


async def run_get_document_annotations(document_path: str, process_id: str):
    try:
        return await annotation_service.get_document_annotations(
            document_path=document_path,
            process_id=process_id,
        )
    except Exception as e:
        logger.error(f"Erro ao obter anotações do documento: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter anotações do documento")


async def run_get_process_annotations(process_id: str, include_resolved: bool):
    try:
        return await annotation_service.get_process_annotations(
            process_id=process_id,
            include_resolved=include_resolved,
        )
    except Exception as e:
        logger.error(f"Erro ao obter anotações do processo {process_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter anotações do processo")


async def run_get_annotation_stats(process_id: str):
    try:
        return await annotation_service.get_annotation_stats(process_id=process_id)
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas do processo {process_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter estatísticas de anotações")
