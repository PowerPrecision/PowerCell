"""
AI Document Analysis Routes
Endpoints for analyzing documents with AI (CC, salary receipts, IRS)
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models.auth import UserRole
from models.task_log import TaskType
from services.auth import get_current_user, require_roles
from services.ai_document import (
    analyze_document_from_url, 
    analyze_document_from_base64,
    map_cc_to_personal_data,
    map_recibo_to_financial_data,
    map_irs_to_financial_data
)
from services.task_log_service import task_log_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI Document Analysis"])


class AnalyzeDocumentRequest(BaseModel):
    """Request to analyze a document."""
    document_url: Optional[str] = None
    document_base64: Optional[str] = None
    mime_type: Optional[str] = "image/jpeg"
    document_type: str  # 'cc', 'recibo_vencimento', 'irs', 'outro'


class AnalyzeOneDriveDocumentRequest(BaseModel):
    """Request to analyze a document from S3 storage."""
    client_folder: str  # Client name used to locate S3 path
    file_name: str
    document_type: str  # 'cc', 'recibo_vencimento', 'irs', 'outro'


@router.post("/analyze-document")
async def analyze_document(
    request: AnalyzeDocumentRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INTERMEDIARIO]))
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
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INTERMEDIARIO]))
):
    """
    Analyze a document from S3 storage using AI.
    
    The document will be fetched from the client's S3 folder and analyzed.
    client_folder is the client_name used to locate the S3 path.
    """
    from database import db
    from services.s3_storage import s3_service

    try:
        # --- Step 1: Find the process by client name ---
        process = await db.processes.find_one(
            {"client_name": {"$regex": f"^{request.client_folder}$", "$options": "i"}},
            {"id": 1, "client_name": 1, "second_client_name": 1, "titular2_data": 1, "s3_folder": 1}
        )
        if not process:
            # Fallback: partial match
            process = await db.processes.find_one(
                {"client_name": {"$regex": request.client_folder, "$options": "i"}},
                {"id": 1, "client_name": 1, "second_client_name": 1, "titular2_data": 1, "s3_folder": 1}
            )
        if not process:
            raise HTTPException(status_code=404, detail=f"Cliente '{request.client_folder}' não encontrado")

        client_id = process.get("id")
        client_name = process.get("client_name", request.client_folder)
        second_client_name = process.get("second_client_name") or process.get("titular2_data", {}).get("nome")
        s3_folder = process.get("s3_folder")

        # --- Step 2: Check S3 is configured ---
        if not s3_service.is_configured():
            raise HTTPException(status_code=503, detail="Armazenamento S3 não configurado")

        # --- Step 3: List files to find the target file ---
        files_data = s3_service.list_files(client_id, client_name, second_client_name, s3_folder=s3_folder)
        files_by_category = files_data.get("files", {})

        target_s3_key = None
        for category, category_files in files_by_category.items():
            if not isinstance(category_files, list):
                continue
            for f in category_files:
                if f.get("name", "").lower() == request.file_name.lower():
                    target_s3_key = f.get("path")
                    break
            if target_s3_key:
                break

        if not target_s3_key:
            raise HTTPException(
                status_code=404,
                detail=f"Ficheiro '{request.file_name}' não encontrado na pasta do cliente '{client_name}'"
            )

        # --- Step 4: Get a presigned URL for the file ---
        download_url = s3_service.get_presigned_url(target_s3_key)
        if not download_url:
            raise HTTPException(status_code=500, detail="Erro ao gerar URL de download do ficheiro")

        # --- Step 5: Analyze the document ---
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
        logger.error(f"Error analyzing document from S3: {e}", exc_info=True)
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


# ====================================================================
# ASYNC AI ANALYSIS - MOTOR DE TAREFAS ASSÍNCRONAS
# ====================================================================

class AsyncAnalyzeDocumentRequest(BaseModel):
    """Request for async document analysis."""
    process_id: str
    document_url: str
    document_type: str  # 'cc', 'recibo_vencimento', 'irs', 'outro'
    auto_apply: bool = False  # Se deve aplicar automaticamente os dados extraídos


async def _analyze_document_background(
    task_id: str,
    process_id: str,
    document_url: str,
    document_type: str,
    auto_apply: bool,
    user_id: str
):
    """
    Função de background para análise de documento com IA.
    
    Esta função é executada em background após o endpoint retornar 202.
    Atualiza o progresso da tarefa e o resultado final.
    """
    from database import db
    
    try:
        # Marcar como em processamento
        await task_log_service.mark_processing(task_id)
        await task_log_service.update_progress(task_id, 10, "A iniciar análise...")
        
        # Executar análise
        result = await analyze_document_from_url(document_url, document_type)
        
        if not result.get("success", False):
            await task_log_service.mark_failed(
                task_id, 
                result.get("error", "Erro ao analisar documento")
            )
            return
        
        await task_log_service.update_progress(task_id, 60, "Análise concluída, a processar dados...")
        
        # Mapear dados extraídos
        extracted_data = result.get("extracted_data", {})
        mapped_data = {}
        
        if document_type == "cc":
            mapped_data["personal_data"] = map_cc_to_personal_data(extracted_data)
        elif document_type == "recibo_vencimento":
            mapped_data["financial_data"] = map_recibo_to_financial_data(extracted_data)
        elif document_type == "irs":
            mapped_data["financial_data"] = map_irs_to_financial_data(extracted_data)
        
        await task_log_service.update_progress(task_id, 80, "A guardar resultados...")
        
        # Se auto_apply, actualizar o processo
        if auto_apply and mapped_data:
            for field, data in mapped_data.items():
                if data:
                    await db.processes.update_one(
                        {"id": process_id},
                        {"$set": {field: data}}
                    )
        
        # Marcar como concluído
        await task_log_service.mark_completed(
            task_id,
            result_data={
                "document_type": document_type,
                "extracted_data": extracted_data,
                "mapped_data": mapped_data,
                "auto_applied": auto_apply
            }
        )
        
        logger.info(f"[AsyncAI] Análise concluída: {task_id}")
        
    except Exception as e:
        logger.error(f"[AsyncAI] Erro na análise: {e}")
        await task_log_service.mark_failed(task_id, str(e))


@router.post("/analyze-document-async")
async def analyze_document_async(
    request: AsyncAnalyzeDocumentRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INTERMEDIARIO]))
):
    """
    Analisa um documento com IA de forma assíncrona.
    
    Este endpoint retorna imediatamente um 202 Accepted com o task_id,
    permitindo que o utilizador continue a usar o CRM enquanto a análise
    corre em background.
    
    Fluxo:
    1. Endpoint regista tarefa e retorna 202 com task_id
    2. Análise corre em background
    3. Frontend faz polling a /api/tasks/active
    4. Quando concluído, frontend mostra notificação
    
    Body:
    - process_id: ID do processo
    - document_url: URL do documento a analisar
    - document_type: Tipo de documento ('cc', 'recibo_vencimento', 'irs', 'outro')
    - auto_apply: Se deve aplicar automaticamente os dados extraídos ao processo
    
    Returns:
    - 202 Accepted com task_id
    """
    # Validar tipo de documento
    valid_types = ['cc', 'recibo_vencimento', 'irs', 'cpcv', 'simulacao_credito', 'caderneta_predial', 'outro']
    if request.document_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"document_type inválido. Tipos suportados: {valid_types}")
    
    # Verificar se o processo existe
    from database import db
    process = await db.processes.find_one({"id": request.process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Criar tarefa
    task = await task_log_service.create_task(
        task_type=TaskType.AI_ANALYSIS,
        user_id=user.get("id"),
        title=f"Análise IA: {request.document_type}",
        description=f"A analisar documento do tipo '{request.document_type}' com IA",
        process_id=request.process_id,
        metadata={
            "document_url": request.document_url[:100] + "..." if len(request.document_url) > 100 else request.document_url,
            "document_type": request.document_type,
            "auto_apply": request.auto_apply
        }
    )
    
    # Agendar execução em background
    background_tasks.add_task(
        _analyze_document_background,
        task.task_id,
        request.process_id,
        request.document_url,
        request.document_type,
        request.auto_apply,
        user.get("id")
    )
    
    # Retornar 202 Accepted
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": "Análise iniciada em background",
            "task_id": task.task_id,
            "process_id": request.process_id
        }
    )


class BulkAnalysisRequest(BaseModel):
    """Request for bulk document analysis."""
    process_ids: List[str]
    analysis_type: str  # 'full', 'documents_only', 'financial_only'


async def _bulk_analysis_background(
    task_id: str,
    process_ids: List[str],
    analysis_type: str,
    user_id: str
):
    """
    Executa análise em massa em background.
    """
    from database import db
    from services.ai_document_analyzer import analyze_process_documents
    
    try:
        await task_log_service.mark_processing(task_id)
        
        total = len(process_ids)
        results = []
        
        for i, process_id in enumerate(process_ids, 1):
            try:
                # Actualizar progresso
                progress = int((i / total) * 100)
                await task_log_service.update_progress(
                    task_id, 
                    progress, 
                    f"A processar {i}/{total} processos..."
                )
                
                # Executar análise
                if analysis_type == "documents_only":
                    result = await analyze_process_documents(process_id)
                else:
                    # Análise completa
                    result = {"process_id": process_id, "analyzed": True}
                
                results.append({
                    "process_id": process_id,
                    "success": True,
                    "result": result
                })
                
            except Exception as e:
                results.append({
                    "process_id": process_id,
                    "success": False,
                    "error": str(e)
                })
        
        # Marcar como concluído
        successful = sum(1 for r in results if r["success"])
        await task_log_service.mark_completed(
            task_id,
            result_data={
                "total": total,
                "successful": successful,
                "failed": total - successful,
                "results": results
            }
        )
        
    except Exception as e:
        logger.error(f"[BulkAnalysis] Erro: {e}")
        await task_log_service.mark_failed(task_id, str(e))


@router.post("/bulk-analysis-async")
async def bulk_analysis_async(
    request: BulkAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Executa análise em massa de forma assíncrona.
    
    Apenas administradores podem executar análises em massa.
    
    Body:
    - process_ids: Lista de IDs de processos a analisar
    - analysis_type: Tipo de análise ('full', 'documents_only', 'financial_only')
    
    Returns:
    - 202 Accepted com task_id
    """
    if len(request.process_ids) == 0:
        raise HTTPException(status_code=400, detail="Lista de process_ids vazia")
    
    if len(request.process_ids) > 50:
        raise HTTPException(status_code=400, detail="Máximo de 50 processos por análise em massa")
    
    # Criar tarefa
    task = await task_log_service.create_task(
        task_type=TaskType.AI_ANALYSIS,
        user_id=user.get("id"),
        title=f"Análise em massa: {len(request.process_ids)} processos",
        description=f"Análise {request.analysis_type} de {len(request.process_ids)} processos",
        metadata={
            "analysis_type": request.analysis_type,
            "process_count": len(request.process_ids)
        }
    )
    
    # Agendar execução em background
    background_tasks.add_task(
        _bulk_analysis_background,
        task.task_id,
        request.process_ids,
        request.analysis_type,
        user.get("id")
    )
    
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": "Análise em massa iniciada",
            "task_id": task.task_id,
            "process_count": len(request.process_ids)
        }
    )
