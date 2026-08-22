"""
Rotas para gestão de Clientes — thin FastAPI stubs.

Logic in services/client_*.py.

Permite gerir clientes de forma independente dos processos.
Um cliente pode ter múltiplos processos de compra/financiamento.

FLUXO:
1. Formulário público cria ficha de cliente na tabela 'clients'
2. Quando o cliente é atribuído a um utilizador, cria-se o processo
3. Um cliente pode ter vários processos

SEGURANÇA:
- Campos sensíveis (NIFs, telefones) são encriptados automaticamente
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from models.client import Client, ClientCreate, ClientUpdate
from services.auth import get_current_user, require_roles
from models.auth import UserRole

from services.client_me import run_get_my_assigned_clients
from services.client_registered import run_list_registered_clients
from services.client_assign import run_assign_client_to_user
from services.client_list_search import run_search_clients, run_list_clients
from services.client_crud import (
    run_get_client,
    run_create_client,
    run_update_client,
)
from services.client_process_ops import (
    run_link_process_to_client,
    run_unlink_process_from_client,
    run_create_process_for_client,
    run_get_client_processes,
)
from services.client_portal_access import run_resend_portal_access
from services.client_find_or_create import run_find_or_create_client
from services.client_delete import run_delete_client

router = APIRouter(prefix="/clients", tags=["Clients"])


# Static paths before /{client_id}
@router.get("/me")
async def get_my_assigned_clients(
    request: Request,
    search: Optional[str] = Query(None, description="Pesquisar por nome ou email"),
    limit: int = Query(100, le=500),
    skip: int = Query(0),
    user: dict = Depends(get_current_user)
):
    return await run_get_my_assigned_clients(
        request, user, search=search, limit=limit, skip=skip,
    )


@router.get("/registered")
async def list_registered_clients(
    search: Optional[str] = Query(None, description="Pesquisar por nome, email ou NIF"),
    has_process: Optional[bool] = Query(None, description="Filtrar por ter processo criado"),
    assigned_to_me: bool = Query(False, description="Mostrar apenas clientes atribuídos ao utilizador atual"),
    include_ghosts: bool = Query(False, description="Incluir clientes fantasma (2º titular apenas). Admin/CEO podem ver todos."),
    triage_mode: bool = Query(False, description="PACOTE BN — Sala de Triagem: inclui leads + processos pre_registo + processos sem indexador atribuído"),
    sort_field: str = Query("nome", description="Campo de ordenação"),
    sort_order: str = Query("asc", description="Ordem: asc ou desc"),
    limit: int = Query(50, le=200),
    skip: int = Query(0),
    cursor: Optional[str] = Query(None, description="Cursor para paginação (valor do campo de ordenação do último item)"),
    cursor_id: Optional[str] = Query(None, description="ID do último item (para desempate na paginação por cursor)"),
    user: dict = Depends(get_current_user)
):
    return await run_list_registered_clients(
        user,
        search=search,
        has_process=has_process,
        assigned_to_me=assigned_to_me,
        include_ghosts=include_ghosts,
        triage_mode=triage_mode,
        sort_field=sort_field,
        sort_order=sort_order,
        limit=limit,
        skip=skip,
        cursor=cursor,
        cursor_id=cursor_id,
    )


@router.get("/search")
async def search_clients(
    q: str = Query(..., min_length=2, description="Pesquisa por nome, email ou NIF"),
    limit: int = Query(10, le=20, description="Número máximo de resultados"),
    user: dict = Depends(get_current_user)
):
    return await run_search_clients(q, user, limit=limit)


@router.get("")
async def list_clients(
    search: Optional[str] = Query(None, description="Pesquisar por nome, email ou NIF"),
    has_active_process: Optional[bool] = Query(None, description="Filtrar por ter processo activo"),
    show_all: Optional[bool] = Query(True, description="Se True, mostra todos os clientes da empresa. Se False, apenas os do utilizador"),
    status_filter: Optional[str] = Query(None, description="Filtrar por fase do processo (legado)"),
    assignment_filter: Optional[str] = Query(None, description="Filtrar por tipo de atribuição: 'both', 'consultor', 'intermediario', 'none'"),
    indexacao_filter: Optional[str] = Query(None, description="Filtrar por indexação: 'assigned' (com indexação), 'unassigned' (sem indexação)"),
    exclude_deleted: Optional[bool] = Query(False, description="Excluir clientes eliminados (status=eliminado)"),
    deleted_only: Optional[bool] = Query(False, description="Mostrar apenas clientes eliminados (status=eliminado)"),
    fonte: Optional[str] = Query(None, description="PACOTE FK — Origem do cliente (campo fonte)"),
    tipo: Optional[str] = Query(None, description="PACOTE FK — Tipo de cliente: particular, dois_titulares, empresa"),
    status: Optional[str] = Query(None, description="PACOTE FK — Estado da ficha: active, inactive, deleted"),
    limit: Optional[int] = Query(100, le=500),
    skip: Optional[int] = Query(0),
    user: dict = Depends(get_current_user)
):
    return await run_list_clients(
        user,
        search=search,
        has_active_process=has_active_process,
        show_all=show_all,
        status_filter=status_filter,
        assignment_filter=assignment_filter,
        indexacao_filter=indexacao_filter,
        exclude_deleted=exclude_deleted,
        deleted_only=deleted_only,
        fonte=fonte,
        tipo=tipo,
        status=status,
        limit=limit,
        skip=skip,
    )


@router.post("/find-or-create")
async def find_or_create_client(
    nome: str,
    email: Optional[str] = None,
    nif: Optional[str] = None,
    telefone: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    return await run_find_or_create_client(
        nome, user, email=email, nif=nif, telefone=telefone,
    )


@router.post("", response_model=Client)
async def create_client(
    client_data: ClientCreate,
    user: dict = Depends(get_current_user)
):
    return await run_create_client(client_data, user)


@router.post("/{client_id}/assign")
async def assign_client_to_user(
    client_id: str,
    assign_to_user_id: Optional[str] = Query(None, description="ID do utilizador a atribuir (vazio = atribuir a si próprio)"),
    create_process: bool = Query(True, description="Criar processo automaticamente"),
    process_type: str = Query("credito_habitacao", description="Tipo de processo a criar"),
    user: dict = Depends(get_current_user)
):
    return await run_assign_client_to_user(
        client_id,
        user,
        assign_to_user_id=assign_to_user_id,
        create_process=create_process,
        process_type=process_type,
    )


@router.get("/{client_id}")
async def get_client(
    client_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_get_client(client_id, user)


@router.put("/{client_id}")
async def update_client(
    client_id: str,
    client_data: ClientUpdate,
    request: Request,
    user: dict = Depends(get_current_user)
):
    return await run_update_client(client_id, client_data, request, user)


@router.post("/{client_id}/link-process")
async def link_process_to_client(
    client_id: str,
    process_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_link_process_to_client(client_id, process_id, user)


@router.delete("/{client_id}/unlink-process/{process_id}")
async def unlink_process_from_client(
    client_id: str,
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO]))
):
    return await run_unlink_process_from_client(client_id, process_id, user)


@router.post("/{client_id}/create-process")
async def create_process_for_client(
    client_id: str,
    process_type: str = Query("credito_habitacao", description="Tipo de processo"),
    description: Optional[str] = Query(None, description="Descrição do processo"),
    user: dict = Depends(get_current_user)
):
    return await run_create_process_for_client(
        client_id, user, process_type=process_type, description=description,
    )


@router.post("/{client_id}/resend-portal-access")
async def resend_portal_access(
    client_id: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    return await run_resend_portal_access(client_id, request, user)


@router.get("/{client_id}/processes")
async def get_client_processes(
    client_id: str,
    include_archived: bool = Query(False),
    user: dict = Depends(get_current_user)
):
    return await run_get_client_processes(
        client_id, user, include_archived=include_archived,
    )


@router.delete("/{client_id}")
async def delete_client(
    client_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))
):
    return await run_delete_client(client_id, user)
