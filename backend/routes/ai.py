"""
AI Document Analysis Routes
Endpoints for analyzing documents with AI (CC, salary receipts, IRS)
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from models.auth import UserRole
from services.auth import get_current_user, require_roles
from services.ai_document import (
    analyze_document_from_url, 
    analyze_document_from_base64,
    map_cc_to_personal_data,
    map_recibo_to_financial_data,
    map_irs_to_financial_data
)
from services.onedrive import onedrive_service
from config import ONEDRIVE_BASE_PATH


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI Document Analysis"])


class AnalyzeDocumentRequest(BaseModel):
    """Request to analyze a document."""
    document_url: Optional[str] = None
    document_base64: Optional[str] = None
    mime_type: Optional[str] = "image/jpeg"
    document_type: str  # 'cc', 'recibo_vencimento', 'irs', 'outro'


class AnalyzeOneDriveDocumentRequest(BaseModel):
    """Request to analyze a document from OneDrive."""
    client_folder: str
    file_name: str
    document_type: str  # 'cc', 'recibo_vencimento', 'irs', 'outro'


@router.post("/analyze-document")
async def analyze_document(
    request: AnalyzeDocumentRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.MEDIADOR]))
):
    """
    Analyze a document using AI and extract structured data.
    
    Supports:
    - Direct URL to document
    - Base64 encoded document content
    
    Document types:
    - cc: Cartão de Cidadão (ID card)
    - recibo_vencimento: Salary receipt
    - irs: Tax declaration
    - outro: Other document
    """
    if not request.document_url and not request.document_base64:
        raise HTTPException(status_code=400, detail="Forneça document_url ou document_base64")
    
    if request.document_type not in ['cc', 'recibo_vencimento', 'irs', 'cpcv', 'simulacao_credito', 'caderneta_predial', 'outro']:
        raise HTTPException(status_code=400, detail="document_type inválido")
    
    if request.document_base64:
        result = await analyze_document_from_base64(
            request.document_base64,
            request.mime_type,
            request.document_type
        )
    else:
        result = await analyze_document_from_url(
            request.document_url,
            request.document_type
        )
    
    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao analisar documento"))
    
    # Map extracted data to form fields
    extracted_data = result.get("extracted_data", {})
    mapped_data = {}
    
    if request.document_type == "cc":
        mapped_data["personal_data"] = map_cc_to_personal_data(extracted_data)
        mapped_data["name"] = extracted_data.get("nome_completo")
    elif request.document_type == "recibo_vencimento":
        mapped_data["financial_data"] = map_recibo_to_financial_data(extracted_data)
    elif request.document_type == "irs":
        mapped_data["financial_data"] = map_irs_to_financial_data(extracted_data)
    elif request.document_type == "cpcv":
        # CPCV tem múltiplos dados
        mapped_data["compradores"] = extracted_data.get("compradores", [])
        mapped_data["vendedor"] = extracted_data.get("vendedor", {})
        mapped_data["imovel"] = extracted_data.get("imovel", {})
        mapped_data["valores"] = extracted_data.get("valores", {})
        mapped_data["datas"] = extracted_data.get("datas", {})
        mapped_data["condicoes"] = extracted_data.get("condicoes", {})
        mapped_data["mediador"] = extracted_data.get("mediador", {})
    elif request.document_type == "caderneta_predial":
        mapped_data["real_estate_data"] = extracted_data
    
    return {
        "success": True,
        "document_type": request.document_type,
        "extracted_data": extracted_data,
        "mapped_data": mapped_data
    }


@router.post("/analyze-onedrive-document")
async def analyze_onedrive_document(
    request: AnalyzeOneDriveDocumentRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.MEDIADOR]))
):
    """
    Analyze a document from OneDrive using AI.
    
    The document will be fetched from the client's OneDrive folder and analyzed.
    """
    try:
        # Build the path to the document
        folder_path = f"{ONEDRIVE_BASE_PATH}/{request.client_folder}"
        
        # List files to find the document
        files = await onedrive_service.list_files(folder_path)
        
        target_file = None
        for f in files:
            if f.name.lower() == request.file_name.lower():
                target_file = f
                break
        
        if not target_file:
            raise HTTPException(status_code=404, detail="Ficheiro não encontrado no OneDrive")
        
        # Get download URL
        download_url = target_file.download_url or await onedrive_service.get_download_url(target_file.id)
        
        # Analyze the document
        result = await analyze_document_from_url(download_url, request.document_type)
        
        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Erro ao analisar documento"))
        
        # Map extracted data
        extracted_data = result.get("extracted_data", {})
        mapped_data = {}
        
        if request.document_type == "cc":
            mapped_data["personal_data"] = map_cc_to_personal_data(extracted_data)
            mapped_data["name"] = extracted_data.get("nome_completo")
        elif request.document_type == "recibo_vencimento":
            mapped_data["financial_data"] = map_recibo_to_financial_data(extracted_data)
        elif request.document_type == "irs":
            mapped_data["financial_data"] = map_irs_to_financial_data(extracted_data)
        
        return {
            "success": True,
            "document_type": request.document_type,
            "file_name": request.file_name,
            "extracted_data": extracted_data,
            "mapped_data": mapped_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing OneDrive document: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao analisar documento: {str(e)}")


@router.get("/supported-documents")
async def get_supported_documents(user: dict = Depends(get_current_user)):
    """Get list of supported document types for AI analysis."""
    return {
        "document_types": [
            {
                "type": "cc",
                "name": "Cartão de Cidadão",
                "description": "Extrai nome, NIF, data nascimento, naturalidade, etc.",
                "extracts": ["nome_completo", "nif", "numero_documento", "data_nascimento", "naturalidade", "nacionalidade"]
            },
            {
                "type": "recibo_vencimento",
                "name": "Recibo de Vencimento",
                "description": "Extrai salário líquido, empresa, tipo de contrato, etc.",
                "extracts": ["salario_liquido", "salario_bruto", "empresa", "tipo_contrato", "categoria_profissional"]
            },
            {
                "type": "irs",
                "name": "Declaração de IRS",
                "description": "Extrai rendimentos anuais, estado civil fiscal, etc.",
                "extracts": ["rendimento_bruto_anual", "rendimento_liquido_anual", "estado_civil_fiscal", "numero_dependentes"]
            },
            {
                "type": "outro",
                "name": "Outro Documento",
                "description": "Extrai dados gerais do documento",
                "extracts": ["dados_gerais"]
            }
        ]
    }


class ResetClientDataRequest(BaseModel):
    """Request to reset client extracted data."""
    process_id: str
    reset_personal: bool = True
    reset_financial: bool = True
    reset_real_estate: bool = True


@router.post("/reset-client-data")
async def reset_client_data(
    request: ResetClientDataRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Reset/clear extracted AI data for a specific client.
    Only admins can perform this action.
    
    Useful for:
    - Clearing incorrect data from failed AI extractions
    - Starting fresh with a client's data
    - Testing purposes
    """
    from database import db
    
    update_fields = {}
    
    if request.reset_personal:
        update_fields["personal_data"] = {}
    if request.reset_financial:
        update_fields["financial_data"] = {}
    if request.reset_real_estate:
        update_fields["real_estate_data"] = {}
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo selecionado para limpar")
    
    # Verificar se processo existe
    process = await db.processes.find_one({"id": request.process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    result = await db.processes.update_one(
        {"id": request.process_id},
        {"$set": update_fields}
    )
    
    if result.modified_count > 0:
        logger.info(f"Dados do cliente {request.process_id} limpos por {user.get('email')}")
        return {
            "success": True,
            "message": f"Dados limpos com sucesso para o processo {request.process_id}",
            "fields_reset": list(update_fields.keys())
        }
    else:
        return {
            "success": True,
            "message": "Nenhuma alteração necessária (dados já estavam vazios)",
            "fields_reset": []
        }
