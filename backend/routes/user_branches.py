"""
====================================================================
ROTAS DE BALCÕES PERSONALIZADOS — thin FastAPI stubs
====================================================================
Logic in services/user_branches_api_*.py.
====================================================================
"""
from fastapi import APIRouter, Depends

from services.auth import get_current_user
from models.system_config import UserCustomBranchCreate, UserCustomBranchResponse
from services.user_branches_api_crud import (
    run_create_user_branch,
    run_list_user_branches,
    run_delete_user_branch,
)

router = APIRouter(prefix="/user-branches", tags=["User Custom Branches"])


@router.post("", response_model=UserCustomBranchResponse, status_code=201)
async def create_user_branch(
    body: UserCustomBranchCreate,
    current_user: dict = Depends(get_current_user),
):
    """Criar um novo balcão personalizado associado ao utilizador autenticado."""
    return await run_create_user_branch(body, current_user)


@router.get("", response_model=list[UserCustomBranchResponse])
async def list_user_branches(
    current_user: dict = Depends(get_current_user),
):
    """Listar todos os balcões personalizados do utilizador autenticado."""
    return await run_list_user_branches(current_user)


@router.delete("/{branch_id}", status_code=204)
async def delete_user_branch(
    branch_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Apagar um balcão personalizado."""
    return await run_delete_user_branch(branch_id, current_user)
