"""
====================================================================
ROTAS DE ANOTAÇÕES — thin FastAPI stubs
====================================================================
Logic in services/annotations_api_*.py.
Do **not** overwrite services/annotation_service.py.
Keep /document and /process/{id}* before /{annotation_id}.
====================================================================
"""
from fastapi import APIRouter, Depends, Query

from models.annotation import AnnotationCreate, AnnotationUpdate, AnnotationResponse
from services.auth import get_current_user
from services.annotations_api_list import (
    run_get_document_annotations,
    run_get_process_annotations,
    run_get_annotation_stats,
)
from services.annotations_api_crud import (
    run_create_annotation,
    run_update_annotation,
    run_delete_annotation,
    run_resolve_annotation,
)

router = APIRouter(prefix="/annotations", tags=["annotations"])


@router.post("/", response_model=AnnotationResponse)
async def create_annotation(
    data: AnnotationCreate,
    user: dict = Depends(get_current_user),
):
    """Cria uma nova anotação num documento."""
    return await run_create_annotation(data, user)


@router.get("/document")
async def get_document_annotations(
    document_path: str = Query(..., description="Caminho do documento no storage"),
    process_id: str = Query(..., description="ID do processo"),
    user: dict = Depends(get_current_user),
):
    """Retorna todas as anotações de um documento específico."""
    return await run_get_document_annotations(document_path, process_id)


@router.get("/process/{process_id}/stats")
async def get_annotation_stats(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """Retorna estatísticas de anotações para um processo."""
    return await run_get_annotation_stats(process_id)


@router.get("/process/{process_id}")
async def get_process_annotations(
    process_id: str,
    include_resolved: bool = Query(True, description="Incluir anotações resolvidas"),
    user: dict = Depends(get_current_user),
):
    """Retorna todas as anotações de um processo."""
    return await run_get_process_annotations(process_id, include_resolved)


@router.put("/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: str,
    data: AnnotationUpdate,
    user: dict = Depends(get_current_user),
):
    """Atualiza uma anotação existente."""
    return await run_update_annotation(annotation_id, data, user)


@router.delete("/{annotation_id}")
async def delete_annotation(
    annotation_id: str,
    user: dict = Depends(get_current_user),
):
    """Elimina uma anotação."""
    return await run_delete_annotation(annotation_id, user)


@router.put("/{annotation_id}/resolve", response_model=AnnotationResponse)
async def resolve_annotation(
    annotation_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """Alterna o estado de resolução de uma anotação."""
    return await run_resolve_annotation(annotation_id, body, user)
