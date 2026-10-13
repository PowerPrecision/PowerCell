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
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from services.auth import require_staff
from services.document_vision_extract import run_extract_document_data
from services.process_closed_guard import exigir_processo_editavel

router = APIRouter(tags=["Document Extraction"], dependencies=[Depends(exigir_processo_editavel)])


class DocumentExtractRequest(BaseModel):
    """Pedido de extracção: o caminho S3 do ficheiro a ler."""

    s3_path: str = Field(..., description="Caminho S3 completo do ficheiro")


@router.post("/processes/{process_id}/documents/extract")
async def extract_document_data(
    request: Request,
    process_id: str,
    payload: DocumentExtractRequest,
    user: dict = Depends(require_staff()),
):
    """Lê um documento arquivado no S3 e devolve os dados para revisão.

    Gestão OU atribuído ao processo, como as restantes ferramentas de IA sobre
    documentos (`/documents/ai-analyze`, `/rename-all-smart`) — a decisão vive em
    `services/document_ai_access`.
    """
    return await run_extract_document_data(
        process_id, payload.s3_path, user=user, request=request
    )
