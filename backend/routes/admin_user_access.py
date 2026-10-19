"""
«REENVIAR CONVITE» DE UTILIZADORES DO CRM — `/api/admin/users/{id}/resend-invite`
================================================================================
Rota própria porque `routes/admin.py` está no tecto de linhas dos stubs finos. O OBJECTO é
verificado no serviço (`carregar_utilizador_gerivel`): `require_roles` autoriza o verbo.
"""
from fastapi import APIRouter, Depends, Request, Response

from middleware.rate_limit import limiter
from models.auth import UserRole
from services.admin_users import run_resend_user_access
from services.auth import require_roles

router = APIRouter(prefix="/admin/users", tags=["Admin"])


@router.post("/{user_id}/resend-invite")
@limiter.limit("10/minute")
async def resend_user_invite(
    request: Request,
    response: Response,
    user_id: str,
    user: dict = Depends(require_roles([UserRole.MASTER, UserRole.ADMIN, UserRole.CEO])),
):
    return await run_resend_user_access(user_id, user, request=request)
