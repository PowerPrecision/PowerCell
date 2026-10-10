"""
GESTÃO DE PARCEIROS — rotas do PLANO DO STAFF (`/api/admin/partners/*`)
=======================================================================
Quem convida e gere parceiros é o Master, o Admin e o CEO — estes dois
**só dentro da sua rede** (a parede está em
`partner_accounts.carregar_parceiro_gerivel`: 404 para um parceiro de outra
rede, igual ao de «não existe»). `require_roles` autoriza o VERBO; o
OBJECTO é verificado no serviço.
"""
from fastapi import APIRouter, Depends, Request, Response

from middleware.rate_limit import limiter
from models.auth import UserRole
from services.auth import require_roles
from services.partner_accounts import (
    PartnerInvite,
    PartnerUpdate,
    run_get_partner,
    run_invite_partner,
    run_list_partners,
    run_resend_invite,
    run_update_partner,
)

router = APIRouter(prefix="/admin/partners", tags=["Parceiros (gestão)"])

_GESTAO = [UserRole.MASTER, UserRole.ADMIN, UserRole.CEO]


@router.get("")
async def list_partners(user: dict = Depends(require_roles(_GESTAO))):
    return await run_list_partners(user)


@router.post("/invite")
@limiter.limit("30/hour")
async def invite_partner(
    request: Request,
    response: Response,
    data: PartnerInvite,
    user: dict = Depends(require_roles(_GESTAO)),
):
    return await run_invite_partner(data, user)


@router.get("/{partner_id}")
async def get_partner(partner_id: str, user: dict = Depends(require_roles(_GESTAO))):
    return await run_get_partner(partner_id, user)


@router.patch("/{partner_id}")
async def update_partner(
    partner_id: str,
    data: PartnerUpdate,
    user: dict = Depends(require_roles(_GESTAO)),
):
    return await run_update_partner(partner_id, data, user)


@router.post("/{partner_id}/resend-invite")
@limiter.limit("30/hour")
async def resend_partner_invite(
    request: Request,
    response: Response,
    partner_id: str,
    user: dict = Depends(require_roles(_GESTAO)),
):
    return await run_resend_invite(partner_id, user)
