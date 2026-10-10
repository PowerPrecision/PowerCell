"""Rotas do Dashboard Executivo e do Relatório Semanal (Bloco 4, pontos 13 e 16).

Só `admin` e `ceo` (a rota exige-o). O âmbito é a REDE de quem pede.
Traduz os erros do motor: período inválido → 422; base de dados que cortou
por tempo → 503 com a instrução do que fazer (nunca um relatório vazio).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import Response

from services import executive_report as er
from services import executive_weekly as ew
from services.executive_report_pdf import construir_pdf, nome_do_ficheiro

logger = logging.getLogger(__name__)


def _filtros(start_date, end_date, user_ids, papeis, com_movimentos=False) -> er.Filtros:
    try:
        periodo = er.construir_periodo(start_date, end_date)
    except er.PeriodoInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro))
    return er.Filtros(
        periodo=periodo,
        user_ids=er.normalizar_lista(user_ids),
        papeis=er.normalizar_lista(papeis),
        com_movimentos=com_movimentos,
    )


async def _correr(coro):
    try:
        return await coro
    except er.PeriodoInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro))
    except er.RelatorioIndisponivel as erro:
        raise HTTPException(status_code=503, detail=str(erro))


async def run_team_performance(
    user: dict,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_ids: Optional[str] = None,
    papeis: Optional[str] = None,
) -> dict:
    filtros = _filtros(start_date, end_date, user_ids, papeis)
    ambito = await er.resolver_ambito(user)
    return await _correr(er.gerar_relatorio(ambito, filtros))


async def _branding(user: dict) -> dict:
    from services.financial_proposal_pdf import resolve_proposal_branding

    company_id = user.get("active_company_id") or user.get("company_id")
    try:
        return await resolve_proposal_branding(company_id)
    except Exception as erro:  # sem branding o PDF sai igual
        logger.warning("[EXEC-PDF] Branding indisponível: %s", erro)
        return {"empresa": {}, "logo_bytes": None, "accent": "#334155"}


async def _pdf(relatorio: dict, user: dict, **opcoes) -> bytes:
    branding = await _branding(user)
    # `reportlab` é síncrono: fora do event loop.
    return await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: construir_pdf(
            relatorio,
            empresa=branding.get("empresa"),
            logo_bytes=branding.get("logo_bytes"),
            accent=branding.get("accent") or "#334155",
            gerado_por=user.get("name") or "",
            **opcoes,
        ),
    )


def _resposta_pdf(conteudo: bytes, nome: str) -> Response:
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"},
    )


async def run_team_performance_pdf(
    user: dict,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_ids: Optional[str] = None,
    papeis: Optional[str] = None,
) -> Response:
    filtros = _filtros(start_date, end_date, user_ids, papeis, com_movimentos=False)
    ambito = await er.resolver_ambito(user)
    relatorio = await _correr(er.gerar_relatorio(ambito, filtros))
    return _resposta_pdf(await _pdf(relatorio, user), nome_do_ficheiro(relatorio))


async def run_weekly(user: dict, week: Optional[str] = None, regenerate: bool = False) -> dict:
    relatorio = await _correr(ew.obter_semana(user, week, forcar=regenerate))
    relatorio["semanas"] = await ew.listar_semanas(user)
    return relatorio


async def run_weekly_pdf(user: dict, week: Optional[str] = None) -> Response:
    relatorio = await _correr(ew.obter_semana(user, week))
    pdf = await _pdf(
        relatorio, user,
        titulo="Relatório Semanal Executivo",
        subtitulo="semana de segunda a domingo",
    )
    return _resposta_pdf(pdf, nome_do_ficheiro(relatorio, "relatorio-semanal"))
