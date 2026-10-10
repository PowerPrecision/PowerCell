"""
PORTAL DO PARCEIRO — rotas do PLANO DO PARCEIRO (`/api/partner/*`)
==================================================================
Stubs finos: a lógica vive em `services/partner_*.py`.

REGRAS DESTE FICHEIRO (guardadas por `test_parceiro_inventarios.py`)
  * Toda a rota depende de `get_current_partner`, EXCEPTO as três que
    entram sem sessão (`ROTAS_SEM_SESSAO`): login, activação do convite e
    a leitura do convite. Uma rota nova sem a dependência falha o teste.
  * Nenhuma rota daqui usa `get_current_user`/`require_roles`: o parceiro
    e o staff são planos de identidade diferentes e uma rota só serve um.
  * Todo o endpoint limitado declara `request: Request` e
    `response: Response` (o limiter com cabeçalhos devolve 500 num
    SUCESSO sem eles).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from middleware.rate_limit import limiter
from services.partner_accounts import (
    PartnerAcceptInvite,
    PartnerChangePassword,
    PartnerLogin,
    publico,
    run_accept_invite,
    run_change_password,
    run_get_invite,
    run_partner_login,
)
from services.partner_leads import PartnerLeadIn, run_submit_lead
from services.partner_portal_read import (
    run_get_case,
    run_get_dashboard,
    run_list_cases,
)
from services.partner_security import get_current_partner
from services.partner_upload_ops import (
    PartnerConfirmUploadIn,
    PartnerUploadUrlIn,
    run_partner_confirm_upload,
    run_partner_download_url,
    run_partner_upload_url,
)

router = APIRouter(prefix="/partner", tags=["Portal do Parceiro"])

#: As únicas rotas deste router que não exigem sessão. Uma lista ESCRITA:
#: o inventário por AST compara-a com as rotas reais.
ROTAS_SEM_SESSAO = frozenset({"partner_login", "partner_get_invite", "partner_accept_invite"})


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


# ── Entrada (sem sessão) ────────────────────────────────────────────
@router.post("/auth/login")
@limiter.limit("10/minute")
async def partner_login(request: Request, response: Response, data: PartnerLogin):
    return await run_partner_login(data)


@router.get("/auth/invite/{token}")
@limiter.limit("30/minute")
async def partner_get_invite(request: Request, response: Response, token: str):
    return await run_get_invite(token)


@router.post("/auth/accept-invite")
@limiter.limit("10/minute")
async def partner_accept_invite(request: Request, response: Response, data: PartnerAcceptInvite):
    return await run_accept_invite(data, ip=_ip(request))


# ── Com sessão ──────────────────────────────────────────────────────
@router.get("/me")
async def partner_me(partner: dict = Depends(get_current_partner)):
    return publico(partner)


@router.post("/auth/change-password")
@limiter.limit("10/minute")
async def partner_change_password(
    request: Request,
    response: Response,
    data: PartnerChangePassword,
    partner: dict = Depends(get_current_partner),
):
    return await run_change_password(partner, data)


# ── Leitura: painel, lista, detalhe ─────────────────────────────────
@router.get("/dashboard")
async def partner_dashboard(partner: dict = Depends(get_current_partner)):
    return await run_get_dashboard(partner)


@router.get("/cases")
async def partner_list_cases(
    etapa: Optional[str] = Query(None, max_length=20),
    q: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1, le=1000),
    size: int = Query(20, ge=1, le=50),
    partner: dict = Depends(get_current_partner),
):
    return await run_list_cases(partner, etapa=etapa, pesquisa=q, page=page, size=size)


@router.get("/cases/{case_id}")
async def partner_get_case(case_id: str, partner: dict = Depends(get_current_partner)):
    return await run_get_case(partner, case_id)


# ── Escrita: leads e ficheiros ──────────────────────────────────────
@router.post("/leads")
@limiter.limit("30/hour")
async def partner_submit_lead(
    request: Request,
    response: Response,
    data: PartnerLeadIn,
    partner: dict = Depends(get_current_partner),
):
    return await run_submit_lead(partner, data)


@router.post("/cases/{case_id}/upload-url")
@limiter.limit("60/minute")
async def partner_upload_url(
    request: Request,
    response: Response,
    case_id: str,
    data: PartnerUploadUrlIn,
    partner: dict = Depends(get_current_partner),
):
    return await run_partner_upload_url(partner, case_id, data)


@router.post("/cases/{case_id}/confirm-upload")
@limiter.limit("60/minute")
async def partner_confirm_upload(
    request: Request,
    response: Response,
    case_id: str,
    data: PartnerConfirmUploadIn,
    partner: dict = Depends(get_current_partner),
):
    return await run_partner_confirm_upload(partner, case_id, data)


@router.get("/cases/{case_id}/files/{file_id}/download-url")
@limiter.limit("60/minute")
async def partner_download_url(
    request: Request,
    response: Response,
    case_id: str,
    file_id: str,
    partner: dict = Depends(get_current_partner),
):
    return await run_partner_download_url(partner, case_id, file_id)
