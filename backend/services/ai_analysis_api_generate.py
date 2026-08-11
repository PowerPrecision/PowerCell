"""POST generate AI executive summary handler.

Extraído de `routes/ai_analysis.py`. Prefer `ai_analysis_api_*` —
do **not** overwrite `ai_document_analyzer.py` (uses `get_openai_client` only).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from database import db
from services.ai_document_analyzer import get_openai_client
from services.ai_analysis_api_helpers import (
    SYSTEM_PROMPT,
    _AI_MODEL,
    _AI_TEMPERATURE,
    acquire_lock,
    release_lock,
    build_context,
    sanitize_ai_response,
)

logger = logging.getLogger(__name__)


async def run_generate_analysis(
    process_id: str,
    force: bool,
    user: dict,
) -> Dict[str, Any]:
    """Generate (or regenerate) an AI executive summary for a credit process."""
    client = get_openai_client()
    if client is None:
        logger.error("OpenAI client not configured — cannot run executive summary")
        raise HTTPException(
            status_code=503,
            detail="Serviço de IA não configurado. Configure OPENAI_API_KEY nas variáveis de ambiente.",
        )

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    if not force and process.get("ai_executive_summary"):
        return {
            "process_id": process_id,
            "ai_executive_summary": process["ai_executive_summary"],
            "ai_analysis_date": process.get("ai_analysis_date"),
            "cached": True,
        }

    if not acquire_lock(process_id):
        raise HTTPException(
            status_code=409,
            detail="Já existe uma análise em curso para este processo. Aguarde a conclusão ou use force=true.",
        )

    user_email = user.get("email", "unknown")

    try:
        doc_metadata_cursor = db.document_metadata.find(
            {"process_id": process_id},
            {
                "_id": 0,
                "filename": 1,
                "ai_category": 1,
                "ai_subcategory": 1,
                "extracted_text": 1,
                "ai_summary": 1,
            },
        )
        doc_metadata: List[Dict[str, Any]] = await doc_metadata_cursor.to_list(length=200)

        analyzed_documents: Optional[List[Dict[str, Any]]] = process.get("analyzed_documents")

        context = build_context(process, doc_metadata, analyzed_documents)

        logger.info(
            "AI analysis started for process %s (user=%s, docs=%d, context=%d chars)",
            process_id,
            user_email,
            len(doc_metadata),
            len(context),
        )

        response = await client.chat.completions.create(
            model=_AI_MODEL,
            temperature=_AI_TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            max_tokens=4_096,
        )

        raw_summary = response.choices[0].message.content or ""
        summary = sanitize_ai_response(raw_summary)

        analysis_date = datetime.now(timezone.utc).isoformat()

        await db.processes.update_one(
            {"id": process_id},
            {
                "$set": {
                    "ai_executive_summary": summary,
                    "ai_analysis_date": analysis_date,
                }
            },
        )

        logger.info(
            "AI analysis completed for process %s (user=%s, summary_len=%d chars)",
            process_id,
            user_email,
            len(summary),
        )

        return {
            "process_id": process_id,
            "ai_executive_summary": summary,
            "ai_analysis_date": analysis_date,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "AI analysis failed for process %s (user=%s): %s",
            process_id,
            user_email,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar análise: {str(exc)}",
        )
    finally:
        release_lock(process_id)
