"""
====================================================================
ROTAS DE CLIENTES DO UTILIZADOR - CREDITOIMO
====================================================================
Thin FastAPI stubs for "Os Meus Clientes".

Logic in services/my_clients_api_*.py.
Do **not** overwrite services/process_my_clients.py
(used by GET /processes/my-clients).
====================================================================
"""
from fastapi import APIRouter, Depends, Request

from models.auth import UserRole
from services.auth import require_roles
from services.my_clients_api_helpers import MY_CLIENTS_ROLES
from services.my_clients_api_list import run_get_my_clients
from services.my_clients_api_stats import run_get_my_clients_stats

router = APIRouter(prefix="/my-clients", tags=["My Clients"])


@router.get("")
async def get_my_clients(
    request: Request,
    user: dict = Depends(require_roles(MY_CLIENTS_ROLES)),
):
    """
    Obter lista de clientes atribuídos ao utilizador actual.

    Retorna nome, fase do processo e acções pendentes.
    Consultores/Intermediários: sincronizado com my-processes + leads.
    """
    return await run_get_my_clients(request, user)


@router.get("/stats")
async def get_my_clients_stats(
    user: dict = Depends(require_roles([
        UserRole.CONSULTOR, UserRole.INTERMEDIARIO,
        UserRole.ADMIN, UserRole.CEO, UserRole.INDEXACAO,
        UserRole.DIRETOR, UserRole.ADMINISTRATIVO,
    ])),
):
    """Obter estatísticas dos clientes do utilizador."""
    return await run_get_my_clients_stats(user)
