"""Opções de parceiro para os FILTROS do CRM (`GET /api/partners/options`, P4).

Aberto a todo o staff (um consultor filtra por parceiro) e só devolve id + nome dos parceiros no
âmbito de quem pergunta. A gestão (convidar, suspender…) é de `routes/partners_admin.py`.
"""
from fastapi import APIRouter, Depends

from services.auth import require_staff
from services.partner_accounts import run_list_partner_options

router = APIRouter(prefix="/partners", tags=["Parceiros (filtros)"])


@router.get("/options")
async def partner_options(user: dict = Depends(require_staff())):
    return await run_list_partner_options(user)
