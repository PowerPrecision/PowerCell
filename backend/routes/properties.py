"""
Rotas para gestão de Imóveis Angariados — thin FastAPI stubs.

Logic in services/property_*.py.
Do not confuse with services/property_scraper.py (portal URL scraping).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File

from models.property import (
    Property, PropertyCreate, PropertyUpdate, PropertyListItem,
    PropertyStatus, PropertyType,
)
from services.auth import get_current_user, require_roles
from models.auth import UserRole

from services.property_list import (
    run_list_properties,
    run_get_property_stats,
    run_get_properties_by_process,
)
from services.property_crud import (
    run_create_property,
    run_get_property,
    run_update_property,
    run_update_property_status,
    run_delete_property,
)
from services.property_engagement import (
    run_add_interested_client,
    run_get_interested_clients,
    run_register_visit,
    run_upload_property_photo,
    run_remove_property_photo,
)
from services.property_excel_import import (
    run_import_properties_from_excel,
    run_get_import_job_status,
    run_get_user_import_jobs,
    run_get_import_template,
)
from services.property_documents import (
    run_upload_property_document,
    run_get_property_documents,
    run_delete_property_document,
)

router = APIRouter(prefix="/properties", tags=["Properties"])


# Static paths before /{property_id}
@router.get("", response_model=List[PropertyListItem])
async def list_properties(
    status: Optional[PropertyStatus] = None,
    property_type: Optional[PropertyType] = None,
    district: Optional[str] = None,
    municipality: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_bedrooms: Optional[int] = None,
    agent_id: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    return await run_list_properties(
        user,
        status=status,
        property_type=property_type,
        district=district,
        municipality=municipality,
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        agent_id=agent_id,
        search=search,
    )


@router.get("/stats")
async def get_property_stats(user: dict = Depends(get_current_user)):
    return await run_get_property_stats(user)


@router.get("/by-process/{process_id}", response_model=List[PropertyListItem])
async def get_properties_by_process(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_get_properties_by_process(process_id, user)


@router.post("", response_model=Property)
async def create_property(
    data: PropertyCreate,
    user: dict = Depends(get_current_user)
):
    return await run_create_property(data, user)


@router.get("/{property_id}", response_model=Property)
async def get_property(
    property_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_get_property(property_id, user)


@router.patch("/{property_id}", response_model=Property)
async def update_property(
    property_id: str,
    data: PropertyUpdate,
    user: dict = Depends(get_current_user)
):
    return await run_update_property(property_id, data, user)


@router.patch("/{property_id}/status")
async def update_property_status(
    property_id: str,
    status: PropertyStatus,
    user: dict = Depends(get_current_user)
):
    return await run_update_property_status(property_id, status, user)


@router.delete("/{property_id}")
async def delete_property(
    property_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    return await run_delete_property(property_id, user)


@router.post("/{property_id}/interested-client")
async def add_interested_client(
    property_id: str,
    client_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_add_interested_client(property_id, client_id, user)


@router.get("/{property_id}/interested-clients")
async def get_interested_clients(
    property_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_get_interested_clients(property_id, user)


@router.post("/{property_id}/register-visit")
async def register_visit(
    property_id: str,
    client_id: Optional[str] = None,
    notes: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    return await run_register_visit(
        property_id, user, client_id=client_id, notes=notes,
    )


@router.post("/{property_id}/upload-photo")
async def upload_property_photo(
    property_id: str,
    photo_url: str,
    user: dict = Depends(get_current_user)
):
    return await run_upload_property_photo(property_id, photo_url, user)


@router.delete("/{property_id}/photo")
async def remove_property_photo(
    property_id: str,
    photo_url: str,
    user: dict = Depends(get_current_user)
):
    return await run_remove_property_photo(property_id, photo_url, user)


@router.post("/bulk/import-excel")
async def import_properties_from_excel(
    file: UploadFile,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    return await run_import_properties_from_excel(file, user)


@router.get("/bulk/job/{job_id}")
async def get_import_job_status(
    job_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_get_import_job_status(job_id, user)


@router.get("/bulk/jobs")
async def get_user_import_jobs(
    limit: int = Query(default=20, le=100),
    user: dict = Depends(get_current_user)
):
    return await run_get_user_import_jobs(user, limit=limit)


@router.get("/bulk/import-template")
async def get_import_template(user: dict = Depends(get_current_user)):
    return await run_get_import_template(user)


# ============== DOCUMENTOS DE IMÓVEIS (Item 1 - Outros erros/melhorias) ==============

@router.post("/{property_id}/documents")
async def upload_property_document(
    property_id: str,
    file: UploadFile = File(...),
    document_type: str = "outro",
    description: str = None,
    user: dict = Depends(get_current_user)
):
    return await run_upload_property_document(
        property_id, file, user,
        document_type=document_type,
        description=description,
    )


@router.get("/{property_id}/documents")
async def get_property_documents(
    property_id: str,
    document_type: str = None,
    user: dict = Depends(get_current_user)
):
    return await run_get_property_documents(
        property_id, user, document_type=document_type,
    )


@router.delete("/{property_id}/documents/{document_id}")
async def delete_property_document(
    property_id: str,
    document_id: str,
    user: dict = Depends(get_current_user)
):
    return await run_delete_property_document(property_id, document_id, user)
