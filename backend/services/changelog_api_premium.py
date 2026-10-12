"""Marcar uma novidade como Premium (upsell) — só o Master.

As atualizações do sistema são GLOBAIS: todas as redes e empresas do CRM veem
as mesmas. «Premium» é um rótulo de venda sobre a novidade (o ecrã destaca-a
com «Módulo Premium» para quem ainda não tem a funcionalidade a pedir); não
altera quem a vê. Marcar é decisão comercial da plataforma, não de uma empresa.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from models.auth import UserRole
from models.changelog import ChangelogPremiumRequest
from services.changelog_service import set_changelog_premium

logger = logging.getLogger(__name__)

#: Quem ESCREVE conteúdo global (gerar por IA, diagnosticar, marcar Premium) —
#: D-34. Uma lista só com o Master é como o `require_roles` diz «isto não é da
#: empresa de ninguém»: o Admin e o CEO, perfis locais, não passam. É UMA
#: constante para as três rotas não divergirem sem dar erro.
PAPEIS_QUE_ESCREVEM_O_CHANGELOG = [UserRole.MASTER]


async def run_set_changelog_premium(changelog_id: str, payload: ChangelogPremiumRequest, user: dict) -> dict:
    resultado = await set_changelog_premium(changelog_id, payload.is_premium)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Atualização não encontrada")
    logger.info(
        "[CHANGELOG] %s marcou a atualização %s como is_premium=%s",
        (user or {}).get("email") or (user or {}).get("id"), changelog_id, payload.is_premium,
    )
    return resultado
