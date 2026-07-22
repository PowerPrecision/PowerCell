"""
====================================================================
MINUTAS ROUTES - CREDITOIMO — thin FastAPI stubs
====================================================================
Logic in services/minutas_api_*.py.
Do **not** overwrite services/rgpd_minutas.py.
Keep static /import before /{minuta_id}.
====================================================================
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile

from services.auth import get_current_user
from services.minutas_api_models import MinutaCreate, MinutaUpdate
from services.minutas_api_crud import (
    run_list_minutas,
    run_create_minuta,
    run_get_minuta,
    run_update_minuta,
    run_delete_minuta,
)
from services.minutas_api_import import run_import_minuta

router = APIRouter(prefix="/minutas", tags=["Minutas"])


@router.get("")
async def list_minutas(
    categoria: Optional[str] = Query(None, description="Filtrar por categoria"),
    search: Optional[str] = Query(None, description="Pesquisar por titulo ou tags"),
    limit: int = Query(100, le=500),
    skip: int = Query(0),
    user: dict = Depends(get_current_user),
):
    """Listar todas as minutas."""
    return await run_list_minutas(categoria, search, limit, skip, user)


@router.post("")
async def create_minuta(
    data: MinutaCreate,
    user: dict = Depends(get_current_user),
):
    """Criar uma nova minuta."""
    return await run_create_minuta(data, user)


@router.post("/import")
async def import_minuta(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Importar uma minuta a partir de um ficheiro (.docx, .doc, .pdf, .txt)."""
    return await run_import_minuta(file, user)


@router.get("/{minuta_id}")
async def get_minuta(
    minuta_id: str,
    user: dict = Depends(get_current_user),
):
    """Obter uma minuta especifica."""
    return await run_get_minuta(minuta_id, user)


@router.put("/{minuta_id}")
async def update_minuta(
    minuta_id: str,
    data: MinutaUpdate,
    user: dict = Depends(get_current_user),
):
    """Actualizar uma minuta."""
    return await run_update_minuta(minuta_id, data, user)


@router.delete("/{minuta_id}")
async def delete_minuta(
    minuta_id: str,
    user: dict = Depends(get_current_user),
):
    """Eliminar uma minuta."""
    return await run_delete_minuta(minuta_id, user)
