"""
====================================================================
ROTAS DE ANOTAÇÕES DE DOCUMENTOS - CREDITOIMO
====================================================================
Endpoints para o sistema de anotações contextuais em documentos.

Funcionalidades:
- Criar anotações em documentos
- Listar anotações por documento ou processo
- Atualizar e eliminar anotações
- Resolver/reabrir anotações
- Estatísticas de anotações por processo
====================================================================
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.annotation import (
    AnnotationCreate,
    AnnotationUpdate,
    AnnotationResponse,
    ANNOTATION_TYPES,
    VALID_ANNOTATION_TYPES,
)
from services.auth import get_current_user
from services import annotation_service

router = APIRouter(prefix="/annotations", tags=["annotations"])
logger = logging.getLogger(__name__)


# ====================================================================
# POST / - Criar anotação
# ====================================================================

@router.post("/", response_model=AnnotationResponse)
async def create_annotation(
    data: AnnotationCreate,
    user: dict = Depends(get_current_user),
):
    """
    Cria uma nova anotação num documento.

    Requer autenticação. A anotação fica associada ao utilizador atual.
    """
    try:
        annotation = await annotation_service.create_annotation(
            data=data.model_dump(),
            author_id=user["id"],
            author_name=user.get("name", user.get("email", "Utilizador")),
        )
        return annotation

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar anotação: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao criar anotação")


# ====================================================================
# GET /document - Anotações de um documento
# ====================================================================

@router.get("/document")
async def get_document_annotations(
    document_path: str = Query(..., description="Caminho do documento no storage"),
    process_id: str = Query(..., description="ID do processo"),
    user: dict = Depends(get_current_user),
):
    """
    Retorna todas as anotações de um documento específico.

    Ordenadas por página e depois por data de criação.
    """
    try:
        annotations = await annotation_service.get_document_annotations(
            document_path=document_path,
            process_id=process_id,
        )
        return annotations

    except Exception as e:
        logger.error(f"Erro ao obter anotações do documento: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter anotações do documento")


# ====================================================================
# GET /process/{process_id} - Anotações de um processo
# ====================================================================

@router.get("/process/{process_id}")
async def get_process_annotations(
    process_id: str,
    include_resolved: bool = Query(True, description="Incluir anotações resolvidas"),
    user: dict = Depends(get_current_user),
):
    """
    Retorna todas as anotações de um processo.

    Pode filtrar anotações resolvidas com include_resolved=false.
    """
    try:
        annotations = await annotation_service.get_process_annotations(
            process_id=process_id,
            include_resolved=include_resolved,
        )
        return annotations

    except Exception as e:
        logger.error(f"Erro ao obter anotações do processo {process_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter anotações do processo")


# ====================================================================
# PUT /{annotation_id} - Atualizar anotação
# ====================================================================

@router.put("/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: str,
    data: AnnotationUpdate,
    user: dict = Depends(get_current_user),
):
    """
    Atualiza uma anotação existente.

    Campos atualizáveis: comment, annotation_type, color, resolved.
    """
    try:
        updated = await annotation_service.update_annotation(
            annotation_id=annotation_id,
            data=data.model_dump(exclude_none=True),
            user_id=user["id"],
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Anotação não encontrada")

        return updated

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar anotação {annotation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar anotação")


# ====================================================================
# DELETE /{annotation_id} - Eliminar anotação
# ====================================================================

@router.delete("/{annotation_id}")
async def delete_annotation(
    annotation_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Elimina uma anotação.

    Apenas o autor da anotação ou um administrador pode eliminar.
    """
    try:
        success = await annotation_service.delete_annotation(
            annotation_id=annotation_id,
            user_id=user["id"],
        )

        if not success:
            raise HTTPException(status_code=404, detail="Anotação não encontrada ou sem permissão para eliminar")

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao eliminar anotação {annotation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao eliminar anotação")


# ====================================================================
# PUT /{annotation_id}/resolve - Alternar resolução
# ====================================================================

@router.put("/{annotation_id}/resolve", response_model=AnnotationResponse)
async def resolve_annotation(
    annotation_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """
    Alterna o estado de resolução de uma anotação.

    Corpo do pedido: {"resolved": true/false}
    """
    try:
        resolved = body.get("resolved")
        if resolved is None or not isinstance(resolved, bool):
            raise HTTPException(
                status_code=400,
                detail="Campo 'resolved' é obrigatório e deve ser booleano (true/false)"
            )

        updated = await annotation_service.resolve_annotation(
            annotation_id=annotation_id,
            user_id=user["id"],
            user_name=user.get("name", user.get("email", "Utilizador")),
            resolved=resolved,
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Anotação não encontrada")

        return updated

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao resolver anotação {annotation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar estado da anotação")


# ====================================================================
# GET /process/{process_id}/stats - Estatísticas de anotações
# ====================================================================

@router.get("/process/{process_id}/stats")
async def get_annotation_stats(
    process_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Retorna estatísticas de anotações para um processo.

    Inclui contagens totais, por estado (resolvida/pendente) e por tipo.
    """
    try:
        stats = await annotation_service.get_annotation_stats(process_id=process_id)
        return stats

    except Exception as e:
        logger.error(f"Erro ao obter estatísticas do processo {process_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao obter estatísticas de anotações")
