"""
====================================================================
Extracção de dados de um documento — thin FastAPI stub (Épico 9)
====================================================================
Lógica em `services/document_vision_extract.py`. A rota vive fora do
router `/documents` porque o recurso é o PROCESSO: os dados extraídos só
fazem sentido comparados com a ficha dele.

A IA não escreve nada aqui. Este endpoint LÊ; quem grava continua a ser
`POST /documents/ai-apply-suggestions/{process_id}`, depois de o
consultor confirmar no diálogo de revisão.
====================================================================
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from models.auth import UserRole
from services.auth import require_roles
from services.document_vision_extract import run_extract_document_data

router = APIRouter(tags=["Document Extraction"])


class DocumentExtractRequest(BaseModel):
    """Pedido de extracção: o caminho S3 do ficheiro a ler."""

    s3_path: str = Field(..., description="Caminho S3 completo do ficheiro")


@router.post("/processes/{process_id}/documents/extract")
async def extract_document_data(
    process_id: str,
    payload: DocumentExtractRequest,
    user: dict = Depends(
        require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR])
    ),
):
    """Lê um documento arquivado no S3 e devolve os dados para revisão.

    Restrito a cargos de gestão, como as restantes ferramentas de IA sobre
    documentos (`/documents/ai-analyze`, `/rename-smart`).
    """
    return await run_extract_document_data(
        process_id, payload.s3_path, user=user
    )
