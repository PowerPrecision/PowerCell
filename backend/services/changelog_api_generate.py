"""Changelog AI generate handler.

Extraído de `routes/changelog.py`.
Do **not** overwrite changelog_service.py — use changelog_api_*.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from models.changelog import ChangelogGenerateRequest
from services.changelog_service import generate_changelog_ai

logger = logging.getLogger(__name__)


async def run_generate_changelog(payload: ChangelogGenerateRequest, user: dict):
    try:
        return await generate_changelog_ai(
            source_type=payload.source_type,
            max_source_lines=payload.max_source_lines,
            custom_prompt_suffix=payload.custom_prompt_suffix
        )
    except ValueError as e:
        error_msg = str(e)
        logger.warning(
            "[CHANGELOG] ValueError ao gerar: %s | source_type=%s | user=%s",
            error_msg, payload.source_type, user.get("email"),
        )
        if "Nenhuma credencial de IA configurada" in error_msg:
            friendly = (
                "Nenhuma credencial de IA configurada. Configure o provider e a API key "
                "no painel de administração (Configurações → IA) ou defina OPENAI_API_KEY / "
                "EMERGENT_LLM_KEY nas variáveis de ambiente do servidor."
            )
        elif "Não foi possível obter dados da fonte" in error_msg:
            friendly = (
                f"Não foi possível obter dados da fonte '{payload.source_type}'. "
                "No Render, o histórico Git pode não estar disponível. "
                "Tente selecionar 'Ficheiro CHANGELOG.md' ou 'worklog.md' como fonte."
            )
        elif "Fonte não suportada" in error_msg:
            friendly = error_msg
        else:
            friendly = error_msg
        raise HTTPException(status_code=400, detail=friendly)
    except RuntimeError as e:
        logger.error("[CHANGELOG] RuntimeError ao gerar: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("[CHANGELOG] Erro inesperado ao gerar changelog: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar notas de atualização: {type(e).__name__}: {e}",
        )
