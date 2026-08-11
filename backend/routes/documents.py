"""
====================================================================
ROTAS DE GESTÃO DE DOCUMENTOS - CREDITOIMO (S3 + VALIDADES)
====================================================================
Inclui:
- Upload com normalização automática de nomes
- Conversão automática de imagens para PDF
- Gestão de validades de documentos
- Categorização automática com IA
====================================================================
"""
import uuid
import logging
import re
import unicodedata
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
from io import BytesIO

# Adicionados UploadFile, File, Form para o S3
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, Response, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator

from database import db
from models.auth import UserRole
from models.document import DocumentExpiryCreate, DocumentExpiryResponse
from services.auth import get_current_user, require_roles
from middleware.rate_limit import limiter

# Importar verificação de permissões de processo
from services.process_service import can_edit_process_data

# Importar o novo serviço S3
from services.s3_storage import s3_service, sanitize_folder_name

# Importar serviço de processamento de documentos (conversão imagem → PDF)
from services.document_processor import convert_image_to_pdf, IMG2PDF_AVAILABLE

# Importar serviço de validação de ficheiros (MIME type validation)
from services.file_validation import validate_file_content, validate_and_extract_file
from services.history import log_history
from utils.input_sanitization import (sanitize_string, sanitize_name, sanitize_email, sanitize_phone, sanitize_url, sanitize_html, log_sanitization_rejection)

router = APIRouter(prefix="/documents", tags=["Document Management"])
logger = logging.getLogger(__name__)

from services.document_constants import (
    ERROR_CLIENT_NOT_FOUND,
    ERROR_PROCESS_NOT_FOUND,
    ERROR_S3_NOT_CONFIGURED,
    ERROR_FILE_ACCESS_DENIED,
    ERROR_S3_UPLOAD_FAILED,
    ERROR_DOWNLOAD_URL,
    ERROR_PRESIGNED_URL,
    ERROR_DELETE_FILE,
    ERROR_RECORD_NOT_FOUND,
    ERROR_S3_FILE_NOT_FOUND,
    ERROR_S3_ACCESS,
    ERROR_CATEGORIZE_DOC,
    ERROR_NO_VALID_FILES,
    ERROR_NO_SUGGESTIONS,
    ERROR_NO_ORGANIZATION,
    ERROR_S3_PATH_REQUIRED,
    ERROR_DOC_NOT_CATEGORIZED,
    ERROR_NEW_NAME_REQUIRED,
    ERROR_RENAME_FAILED,
    ERROR_CLIENT_WITHOUT_PROCESS,
    DEFAULT_CLIENT_NAME,
    DEFAULT_CONSULTOR_NAME,
    DEFAULT_FILE_PREFIX,
    MIME_TYPE_PDF,
    HTTP_400_RESPONSE,
    HTTP_403_RESPONSE,
    HTTP_404_RESPONSE,
    HTTP_500_RESPONSE,
    DOCUMENT_CATEGORY_MAP,
)
from services.document_filenames import (
    sanitize_for_log,
    normalize_filename,
    is_image_file,
    generate_smart_filename,
)
from services.document_process_resolve import (
    resolve_process_from_flexible_id,
    extract_second_client_name,
    assert_s3_file_belongs_to_process,
    build_s3_valid_prefixes,
)
from services.document_expiring_dashboard import run_get_expiring_documents_dashboard
from services.document_portal_request import (
    run_create_portal_document_request,
    run_get_portal_document_requests,
    run_update_portal_document_request,
    run_delete_portal_document_request,
)
from services.document_upload_conflict import run_check_upload_conflict
from services.document_auto_categorize import (
    auto_categorize_document_background,
)
from services.document_direct_upload import (
    run_generate_upload_url,
    run_confirm_upload,
)
from services.document_move import (
    run_check_move_conflict,
    run_move_file_to_category,
)
from services.document_ocr_data import (
    run_get_document_ocr_status,
    run_get_data_suggestions,
    run_resolve_data_conflict,
    run_confirm_process_data,
)
from services.document_upload import run_upload_file_s3
from services.document_ai_analyze import (
    run_ai_analyze_documents,
    run_organize_documents_after_analysis,
    run_apply_ai_suggestions,
    run_organize_files_in_folders,
)
from services.document_queries import (
    run_get_process_documents,
    run_get_document_metadata,
    run_search_documents,
    run_get_all_categories,
)
from services.document_expiry_crud import (
    EXPIRY_WARNING_DAYS,
    DOCUMENT_TYPES,
    run_create_document_expiry,
    run_get_document_expiries,
    run_get_upcoming_expiries,
    run_get_expiry_calendar_events,
    run_delete_document_expiry,
)
from services.document_misc import (
    run_check_file_upload,
    run_initialize_folders,
    run_get_download_url,
    run_get_download_url_by_path,
    run_check_employer_nif,
)
from models.document import DocumentSearchRequest

from services.document_delete import (
    run_delete_file_s3,
    run_bulk_delete_files,
)
from services.document_proxy import run_proxy_s3_file
from services.document_bulk_download import run_bulk_download_documents
from services.document_categorize import (
    run_categorize_document,
    run_categorize_all_documents,
)
from services.document_rename_smart import (
    run_rename_document_smart,
    run_rename_all_documents_smart,
)


# ====================================================================
# FUNÇÃO DE CATEGORIZAÇÃO AUTOMÁTICA EM BACKGROUND
# ====================================================================

# Re-export: testes/integration importam de routes.documents
# (auto_categorize_document_background → services.document_auto_categorize)


# ====================================================================
# PARTE 1: GESTÃO DE FICHEIROS (S3 STORAGE) - NOVO
# ====================================================================

@router.get("/client/{client_id}/files", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def list_client_files(
    client_id: str, 
    user: dict = Depends(get_current_user)
):
    """Lista todos os ficheiros do cliente no S3 organizados por pastas.
    
    Suporta múltiplos tipos de ID:
    - ID de processo (procura em processes por "id")
    - ID de cliente (procura em clients por "id", depois em processes por "client_id")
    """
    process, effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[FILES]",
        allow_client_without_process=True,
        raise_on_client_without_process=False,
    )
    if process is None and effective_id is None:
        # Cliente sem processo OU não encontrado — distinguir
        client = await db.clients.find_one({"id": client_id})
        if client:
            return {"files": {}, "categories": []}
        raise HTTPException(status_code=404, detail=ERROR_CLIENT_NOT_FOUND)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = extract_second_client_name(process)
    s3_folder = process.get("s3_folder")
    
    # Executar operação síncrona do S3 em thread separada para não bloquear o event loop
    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(
        None,
        lambda: s3_service.list_files(effective_id, client_name, second_client_name, s3_folder)
    )

    # Enriquecer com flags de análise/categorização IA (para badge na UI)
    try:
        meta_docs = await db.document_metadata.find(
            {"process_id": effective_id},
            {
                "_id": 0,
                "s3_path": 1,
                "ai_analyzed": 1,
                "ai_analyzed_at": 1,
                "is_categorized": 1,
                "ai_category": 1,
            },
        ).to_list(2000)
        meta_by_path = {
            m["s3_path"]: m for m in meta_docs if m.get("s3_path")
        }
        files_by_cat = files.get("files") if isinstance(files, dict) else None
        if isinstance(files_by_cat, dict):
            for _cat, file_list in files_by_cat.items():
                if not isinstance(file_list, list):
                    continue
                for f in file_list:
                    meta = meta_by_path.get(f.get("path") or "", {})
                    f["ai_analyzed"] = bool(meta.get("ai_analyzed"))
                    f["ai_analyzed_at"] = meta.get("ai_analyzed_at")
                    f["is_categorized"] = bool(meta.get("is_categorized"))
                    if meta.get("ai_category") and not f.get("ai_category"):
                        f["ai_category"] = meta.get("ai_category")
    except Exception as enrich_err:
        logger.warning(f"[FILES] Falha ao enriquecer metadados IA: {enrich_err}")

    return files

@router.post("/client/{client_id}/upload", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
@limiter.limit("60/minute")
async def upload_file_s3(
    client_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form(...), # Ex: "Financeiros", "Imovel"
    empresa_nif: Optional[str] = Form(None),  # NIF da empresa - obrigatório para indexacao
    custom_filename: Optional[str] = Form(None),  # Nome personalizado para evitar conflitos
    user: dict = Depends(get_current_user)
):
    """
    Faz upload de um ficheiro para o S3 com pipeline automático completo.

    Este endpoint é o ponto de entrada principal para upload de documentos
    e executa automaticamente as seguintes etapas:
    1. Validação de MIME type por magic bytes (segurança contra executáveis).
    2. Extração de conteúdo de wrappers (Java serialization, base64).
    3. Conversão automática de imagens (JPG, PNG) para PDF.
    4. Normalização do nome do ficheiro para armazenamento seguro.
    5. Upload para o S3 e categorização IA em background.
    6. Registo no histórico de atividades do processo.

    Porquê o pipeline completo: sem automação, os consultores precisavam
    de converter ficheiros manualmente e categorizar cada documento,
    causando atrasos significativos no processo de crédito.

    Args:
        client_id: ID do processo/cliente.
        file: Ficheiro a carregar (UploadFile do FastAPI).
        category: Categoria do documento (ex: "Financeiros", "Imóvel").
        empresa_nif: NIF da empresa empregadora (para indexação).
        custom_filename: Nome personalizado para evitar conflitos.
        user: Utilizador autenticado (injetado pelo Depends).

    Returns:
        JSONResponse: Dados do upload incluindo path, normalized_filename,
            converted_to_pdf, e auto_categorization status.
    """
    try:
        file_content = await file.read()
        original_filename = file.filename or (
            f"documento_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        )
        content_type = file.content_type or "application/octet-stream"
        response_data = await run_upload_file_s3(
            client_id,
            file_content=file_content,
            original_filename=original_filename,
            content_type=content_type,
            category=category,
            empresa_nif=empresa_nif,
            custom_filename=custom_filename,
            user=user,
            background_tasks=background_tasks,
            client_original_filename=file.filename,
        )
        return JSONResponse(status_code=200, content=response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[UPLOAD] Erro inesperado: {type(e).__name__}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Erro interno ao processar upload. Por favor tente novamente "
                "ou contacte o suporte se o problema persistir."
            ),
        )


@router.post("/check-upload-conflict", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE})
async def check_upload_conflict(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Verifica se existe conflito de nomes ANTES do upload.
    
    Body:
    - process_id: ID do processo
    - filenames: Lista de nomes de ficheiros a verificar
    - category: Categoria destino (opcional, default: "Outros")
    
    Returns:
    - conflicts: Lista de ficheiros com conflito
    - for each conflict:
        - filename: Nome do ficheiro
        - existing_path: Caminho do ficheiro existente
        - suggested_names: Lista de nomes alternativos
    """
    return await run_check_upload_conflict(data)


# ====================================================================
# DIRECT S3 UPLOAD - PRE-SIGNED URLs
# ====================================================================

@router.post("/generate-upload-url", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def generate_upload_url(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Gera uma pre-signed URL para upload direto do frontend para o S3.
    
    Este endpoint permite que o frontend faça upload diretamente para o S3,
    evitando que o ficheiro passe pelo backend (reduz consumo de RAM e previne timeouts).
    
    Fluxo:
    1. Frontend chama este endpoint com nome e tipo do ficheiro
    2. Backend gera URL assinada e devolve
    3. Frontend faz PUT diretamente para o S3
    4. Frontend chama /confirm-upload para registar na base de dados
    
    Body:
    - process_id: ID do processo (obrigatório)
    - filename: Nome original do ficheiro (obrigatório)
    - content_type: MIME type do ficheiro (obrigatório, ex: "application/pdf")
    - category: Categoria destino (default: "Outros")
    - custom_filename: Nome personalizado para evitar conflitos (opcional)
    
    Returns:
    - upload_url: URL assinada para PUT request
    - file_key: Caminho S3 onde o ficheiro será armazenado
    - expires_at: Timestamp de expiração da URL
    - expires_in_seconds: Segundos até a URL expirar
    """
    return await run_generate_upload_url(data, user=user)


@router.post("/confirm-upload", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def confirm_upload(
    data: dict,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """
    Confirma um upload direto para o S3 e regista metadados na base de dados.
    
    Este endpoint deve ser chamado pelo frontend APÓS o upload direto para o S3
    ter sido concluído com sucesso (HTTP 200 do S3).
    
    Body:
    - process_id: ID do processo (obrigatório)
    - file_key: Caminho S3 do ficheiro (obrigatório, devolvido pelo /generate-upload-url)
    - original_filename: Nome original do ficheiro (obrigatório)
    - category: Categoria do documento (obrigatório)
    - file_size: Tamanho do ficheiro em bytes (opcional)
    - content_type: MIME type do ficheiro (opcional)
    
    Returns:
    - success: True se registado com sucesso
    - s3_path: Caminho S3 do ficheiro
    - temporary_url: URL temporário para acesso imediato
    """
    return await run_confirm_upload(
        data, background_tasks=background_tasks, user=user
    )


@router.post("/check-file", responses={400: HTTP_400_RESPONSE, 500: HTTP_500_RESPONSE})
async def check_file_upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """
    Verifica se um ficheiro pode ser enviado e/ou convertido.
    
    Este endpoint permite verificar o ficheiro antes de tentar o upload,
    dando feedback ao utilizador sobre:
    - Se o formato é suportado
    - Se pode ser convertido automaticamente
    - Que tipo de conversão será aplicada
    
    Útil para dar feedback proativo ao utilizador.
    """
    return await run_check_file_upload(file)



@router.post("/client/{client_id}/init-folders", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def initialize_folders(client_id: str, user: dict = Depends(get_current_user)):
    """Cria a estrutura de pastas inicial no S3 (se não existir)."""
    return await run_initialize_folders(client_id)



@router.get("/client/{client_id}/download", responses={403: HTTP_403_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def get_download_url(
    client_id: str,
    file_path: str,
    user: dict = Depends(get_current_user)
):
    """Gera um URL temporário para download de um ficheiro."""
    return await run_get_download_url(client_id, file_path)



@router.get("/download-url/{file_path:path}", responses={500: HTTP_500_RESPONSE})
async def get_download_url_by_path(
    file_path: str,
    user: dict = Depends(get_current_user)
):
    """
    Gera URL temporário (pre-signed) para download ou preview de um
    ficheiro por caminho S3 direto.
    """
    return await run_get_download_url_by_path(file_path)



@router.get("/proxy/{file_path:path}", responses={500: HTTP_500_RESPONSE})
async def proxy_s3_file(
    file_path: str,
    user: dict = Depends(get_current_user)
):
    """
    Proxy para download de ficheiros S3.
    Resolve problemas de CORS ao fazer streaming do ficheiro através do backend.
    
    Args:
        file_path: Path completo do ficheiro no S3 (URL encoded)
        
    Returns:
        StreamingResponse com o conteúdo do ficheiro
    """
    return await run_proxy_s3_file(file_path)



@router.delete("/client/{client_id}/file", responses={403: HTTP_403_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
@limiter.limit("20/minute")
async def delete_file_s3(
    client_id: str,
    file_path: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Elimina um ficheiro do S3 com protecção contra eliminação cruzada.
    
    PROTECÇÃO DE ELIMINAÇÃO SEGURA (Regra de Scope Cruzado):
    - Se o documento tem scope 'global' (pertence ao client_id), verifica
      se está referenciado nos arrays de document_ids / checklist de OUTROS
      processos ativos do mesmo cliente.
    - Se estiver, retorna 409 Conflict com mensagem explícita indicando
      qual o processo que referencia o documento.
    - Documentos com scope 'process' ou sem scope são eliminados normalmente.
    
    Args:
        client_id: ID do processo/cliente.
        file_path: Caminho do ficheiro no S3.
        request: Request object (para rate limiting).
        user: Utilizador autenticado (injetado pelo Depends).
    
    Returns:
        JSONResponse: Sucesso ou erro 409 com detalhes do conflito.
    """
    return await run_delete_file_s3(client_id, file_path, user=user)



@router.post("/client/{client_id}/bulk-delete", responses={400: HTTP_400_RESPONSE, 403: HTTP_403_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
@limiter.limit("30/minute")
async def bulk_delete_files(
    client_id: str,
    request: Request,
    data: dict = Body(...),
    user: dict = Depends(get_current_user)
):
    """Elimina múltiplos ficheiros do S3 de uma só vez."""
    return await run_bulk_delete_files(client_id, data, user=user)



@router.post("/check-move-conflict", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE})
async def check_move_conflict(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Verifica se existe conflito ao mover/renomear um ficheiro.
    
    Body:
    - process_id: ID do processo
    - source_path: Caminho atual do ficheiro no S3
    - target_category: Categoria destino (opcional, para mover)
    - target_filename: Novo nome do ficheiro (opcional, para renomear)
    
    Returns:
    - has_conflict: True se existe ficheiro com mesmo nome
    - conflict_path: Caminho do ficheiro existente (se houver conflito)
    - suggested_names: Lista de nomes alternativos (se houver conflito)
    """
    return await run_check_move_conflict(data)


@router.post("/move-file/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def move_file_to_category(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Move um ficheiro para uma categoria/pasta específica.
    
    Body:
    - source_path: Caminho atual do ficheiro no S3
    - target_category: Nome da categoria destino (ex: "Documentos Pessoais", "Financeiros")
    - target_filename: Novo nome do ficheiro (opcional, para renomear ao mover)
    - overwrite: Se True, substitui ficheiro existente (padrão: False)
    - auto_rename: Se True e existir conflito, renomeia automaticamente (padrão: False)
    
    Returns:
    - success: True/False
    - new_path: Novo caminho no S3
    - was_renamed: Se o nome foi alterado automaticamente devido a conflito
    """
    return await run_move_file_to_category(process_id, data, user=user)


# ====================================================================
# PARTE 2: GESTÃO DE VALIDADES (EXISTENTE)
# ====================================================================
@router.post("/expiry", response_model=DocumentExpiryResponse, responses={404: HTTP_404_RESPONSE})
async def create_document_expiry(
    data: DocumentExpiryCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO]))
):
    """Registar validade de um documento."""
    return await run_create_document_expiry(data, user=user)



@router.get("/expiry", response_model=List[DocumentExpiryResponse], responses={500: HTTP_500_RESPONSE})
async def get_document_expiries(
    process_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Obter registos de validade."""
    return await run_get_document_expiries(process_id, user=user)



@router.get("/expiry/upcoming", responses={500: HTTP_500_RESPONSE})
async def get_upcoming_expiries(
    days: int = EXPIRY_WARNING_DAYS,
    user: dict = Depends(get_current_user)
):
    """Alertas de documentos a expirar."""
    return await run_get_upcoming_expiries(days=days, user=user)



@router.get("/expiry/calendar", responses={500: HTTP_500_RESPONSE})
async def get_expiry_calendar_events(user: dict = Depends(get_current_user)):
    """Eventos para calendário."""
    return await run_get_expiry_calendar_events(user=user)



@router.delete("/expiry/{doc_id}", responses={404: HTTP_404_RESPONSE})
async def delete_document_expiry(doc_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INDEXACAO]))):
    """Remove uma regra de validade de documento."""
    return await run_delete_document_expiry(doc_id)



DOCUMENT_TYPES = [
    {"type": "cc", "name": "Cartão de Cidadão", "validity_years": 5},
    {"type": "irs", "name": "Declaração de IRS", "validity_years": 1},
    {"type": "recibo", "name": "Recibo Vencimento", "validity_months": 3},
    {"type": "outro", "name": "Outro", "validity_years": None},
]

@router.get("/types", responses={500: HTTP_500_RESPONSE})
async def get_document_types(user: dict = Depends(get_current_user)):
    """Retorna a lista de tipos de documentos suportados com prazos de validade."""
    return DOCUMENT_TYPES



# ====================================================================
# PARTE 3: CATEGORIZAÇÃO E PESQUISA COM IA (NOVO)
# ====================================================================

from services.document_categorization import (
    extract_text_from_pdf,
    categorize_document_with_ai,
    search_documents_by_content
)


@router.post("/categorize/{process_id}", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def categorize_document(
    process_id: str,
    s3_path: str = Form(...),
    filename: str = Form(...),
    user: dict = Depends(get_current_user)
):
    """
    Categorizar um documento específico usando IA.
    
    A IA analisa o conteúdo do documento e atribui:
    - Categoria principal
    - Subcategoria (tipo específico)
    - Tags relevantes
    - Resumo do conteúdo
    """
    return await run_categorize_document(
        process_id, s3_path=s3_path, filename=filename
    )



@router.post("/categorize-all/{process_id}", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def categorize_all_documents(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Categorizar TODOS os documentos de um cliente/processo.
    Processa documentos que ainda não foram categorizados.
    """
    return await run_categorize_all_documents(process_id)



@router.get("/process/{process_id}", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def get_process_documents(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter lista simples de documentos de um processo.
    Usado pelo modal de envio de documentação para balcões.
    """
    return await run_get_process_documents(process_id)



@router.get("/metadata/{process_id}", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def get_document_metadata(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter metadados de todos os documentos de um processo.
    Inclui categorização IA se disponível.
    """
    return await run_get_document_metadata(process_id)



@router.post("/search", responses={500: HTTP_500_RESPONSE})
async def search_documents(
    request: DocumentSearchRequest,
    user: dict = Depends(get_current_user)
):
    """Pesquisar documentos por conteúdo."""
    return await run_search_documents(request)



@router.get("/categories", responses={500: HTTP_500_RESPONSE})
async def get_all_categories(
    process_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Obter todas as categorias de documentos."""
    return await run_get_all_categories(process_id)



# ====================================================================
# DASHBOARD DE VALIDADES DE DOCUMENTOS
# ====================================================================

@router.get("/expiring-dashboard", responses={500: HTTP_500_RESPONSE})
async def get_expiring_documents_dashboard(
    days_ahead: int = 60,
    urgency: Optional[str] = None,  # "critical", "high", "medium"
    consultor_id: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Dashboard de documentos a expirar (ACL por role + filtros)."""
    return await run_get_expiring_documents_dashboard(
        days_ahead=days_ahead,
        urgency=urgency,
        consultor_id=consultor_id,
        search=search,
        user=user,
    )


# ====================================================================
# ANÁLISE DE DOCUMENTOS COM IA
# ====================================================================

@router.post("/ai-analyze/{process_id}", responses={400: HTTP_400_RESPONSE, 403: {"description": "Forbidden"}, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def ai_analyze_documents(
    request: Request,
    process_id: str,
    files: List[UploadFile] = File(...),
    file_paths: Optional[str] = Form(None),
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR])),
):
    """
    Analisa documentos com IA para extração de dados.

    Restrito a cargos de gestão (admin, CEO, diretor / "gestor").
    Documentos já marcados com ai_analyzed são saltados.
    
    Funcionalidades:
    - OCR e extração de dados estruturados
    - Comparação com dados do cliente existentes
    - Identificação de campos diferentes e em falta
    - Sugestões de organização em pastas
    - Sugestões de preenchimento automático
    - Criação de log de importação para consulta posterior
    
    Args:
        process_id: ID do processo/cliente
        files: Lista de ficheiros para analisar
        file_paths: JSON opcional com paths S3 alinhados à ordem de `files`
        
    Returns:
        Resultado da análise com comparações e sugestões
    """
    parsed_paths: Optional[List[str]] = None
    if file_paths:
        try:
            import json as _json
            raw = _json.loads(file_paths)
            if isinstance(raw, list):
                parsed_paths = [str(p) if p is not None else "" for p in raw]
        except (TypeError, ValueError) as e:
            logger.warning(f"file_paths inválido no ai-analyze: {e}")
    return await run_ai_analyze_documents(
        process_id, files, user=user, file_paths=parsed_paths
    )


@router.post("/ai-apply-suggestions/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def apply_ai_suggestions(
    process_id: str,
    suggestions: Dict = Body(default=None),
    user: dict = Depends(get_current_user)
):
    """Aplica sugestões da análise IA aos dados do cliente."""
    return await run_apply_ai_suggestions(process_id, suggestions, user=user)



@router.post("/organize-files/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def organize_files_in_folders(
    process_id: str,
    organization: List[Dict] = None,
    user: dict = Depends(get_current_user)
):
    """Organiza ficheiros em pastas no S3 baseado na análise IA."""
    return await run_organize_files_in_folders(process_id, organization)



@router.post("/organize/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def organize_documents_after_analysis(
    request: Request,
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Organiza documentos em pastas após análise IA.
    Cria pastas baseadas no tipo de documento detectado.
    
    Args:
        process_id: ID do processo
        documents: Lista de documentos analisados com tipo detectado
        create_folders: Se deve criar pastas automaticamente
    """
    body = await request.json()
    return await run_organize_documents_after_analysis(
        process_id,
        documents=body.get("documents", []),
        create_folders=body.get("create_folders", True),
    )


# ====================================================================
# RENOMEAÇÃO INTELIGENTE DE DOCUMENTOS COM IA
# (generate_smart_filename → services.document_filenames)
# ====================================================================

@router.post("/rename-smart/{process_id}", responses={400: HTTP_400_RESPONSE, 403: {"description": "Forbidden"}, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def rename_document_smart(
    process_id: str,
    data: dict,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR])),
):
    """
    Renomeia um documento de forma inteligente baseado na análise IA.

    Restrito a cargos de gestão (admin, CEO, diretor / "gestor").
    
    Body:
    - s3_path: Caminho actual do ficheiro no S3
    - apply_ai_name: Se True, usa o nome gerado pela IA; se False, usa o novo_nome fornecido
    - novo_nome: Nome manual (usado se apply_ai_name=False)
    
    Returns:
    - success: True/False
    - old_name: Nome antigo
    - new_name: Novo nome
    - new_path: Novo caminho no S3
    """
    return await run_rename_document_smart(process_id, data)



@router.post("/rename-all-smart/{process_id}", responses={403: {"description": "Forbidden"}, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def rename_all_documents_smart(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR])),
):
    """
    Renomeia TODOS os documentos de um processo usando nomes inteligentes IA.
    Apenas documentos já categorizados são renomeados.
    Restrito a cargos de gestão (admin, CEO, diretor / "gestor").
    
    Returns:
    - total: Total de documentos
    - renamed: Número renomeados com sucesso
    - skipped: Número ignorados (não categorizados)
    - errors: Número de erros
    - details: Lista de operações
    """
    return await run_rename_all_documents_smart(process_id)



# ====================================================================
# VERIFICAÇÃO DE NIF DE EMPRESA
# ====================================================================

@router.get("/check-employer-nif/{nif}")
async def check_employer_nif(
    nif: str,
    user: dict = Depends(get_current_user)
):
    """Verifica se um NIF de empresa já existe na base de dados."""
    return await run_check_employer_nif(nif)



# ====================================================================
# DOWNLOAD EM MASSA (ZIP)
# ====================================================================

@router.post("/bulk-download", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def bulk_download_documents(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Faz download de múltiplos documentos empacotados num ficheiro ZIP.
    
    Body:
    - document_ids: Lista de IDs de documentos (s3_paths) ou paths diretos
    - process_id: ID do processo (opcional, para verificação de permissões)
    
    Returns:
    - StreamingResponse com o ficheiro ZIP
    """
    return await run_bulk_download_documents(data, user=user)



# ====================================================================
# PORTAL DOCUMENT REQUESTS — Admin manages what the client sees
# ====================================================================

@router.get("/portal-requests/{process_id}")
async def get_portal_document_requests(
    process_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))
):
    """
    Lista todos os pedidos de documentos do portal para um processo.
    Inclui docs com status REQUESTED, PENDING, UPLOADED, RECEIVED.
    """
    return await run_get_portal_document_requests(process_id)


class DocumentRequestCreate(BaseModel):
    category: str  # Will be coerced from object if needed in the handler
    notes: Optional[str] = None
    custom_label: Optional[str] = None  # For "Outros" category

    @model_validator(mode='before')
    @classmethod
    def coerce_category_to_str(cls, values):
        """Coerce category from object {value, label} to string if needed."""
        if isinstance(values, dict):
            cat = values.get('category')
            if isinstance(cat, dict):
                values['category'] = cat.get('value', cat.get('label', str(cat)))
            elif cat is not None and not isinstance(cat, str):
                values['category'] = str(cat)
            # Also coerce notes and custom_label if they come as objects
            for field in ['notes', 'custom_label']:
                val = values.get(field)
                if isinstance(val, dict):
                    values[field] = val.get('value', val.get('label', str(val)))
                elif val is not None and not isinstance(val, str):
                    values[field] = str(val)
        return values


@router.post("/portal-requests/{process_id}")
async def create_portal_document_request(
    process_id: str,
    data: DocumentRequestCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))
):
    """
    Solicita um documento ao cliente via portal.
    Cria um registo com status REQUESTED que aparece no portal do cliente.
    """
    try:
        return await run_create_portal_document_request(
            process_id,
            category=data.category,
            notes=data.notes,
            custom_label=data.custom_label,
            user=user,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[PORTAL-REQUESTS] Unhandled error creating portal request for process "
            f"{process_id}: {type(e).__name__}: {e} | "
            f"input_data: category={data.category!r}, notes={data.notes!r}, "
            f"custom_label={data.custom_label!r}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno do servidor [{type(e).__name__}]"
        )


class DocumentStatusUpdate(BaseModel):
    status: str  # RECEIVED or REQUESTED (to toggle back)


@router.put("/portal-requests/{process_id}/{document_id}")
async def update_portal_document_request(
    process_id: str,
    document_id: str,
    data: DocumentStatusUpdate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))
):
    """
    Atualiza o status de um documento do portal.
    - RECEIVED: marca como recebido (não aparece como pendente no portal)
    - REQUESTED: volta a pedir (aparece como pendente no portal)
    - UPLOADED: cliente submeteu o ficheiro
    """
    try:
        return await run_update_portal_document_request(
            process_id, document_id, status=data.status, user=user
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Error updating portal request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar pedido: {str(e)}")


@router.delete("/portal-requests/{process_id}/{document_id}")
async def delete_portal_document_request(
    process_id: str,
    document_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]))
):
    """
    Remove um pedido de documento do portal.
    """
    return await run_delete_portal_document_request(
        process_id, document_id, user=user
    )


# ====================================================================
# ENDPOINTS DE DADOS OCR / CONFLITOS DE DADOS
# ====================================================================

@router.get("/process/{process_id}/ocr-status", responses={404: HTTP_404_RESPONSE})
async def get_document_ocr_status(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Retorna o estado do OCR para todos os documentos de um processo.
    
    Permite ao frontend fazer polling após o upload para verificar
    se o OCR já extraiu dados dos documentos.
    
    Args:
        process_id: ID do processo.
    
    Returns:
        Lista de documentos com extracted_data (se disponível).
    """
    return await run_get_document_ocr_status(process_id)


@router.get("/process/{process_id}/data-suggestions", responses={404: HTTP_404_RESPONSE})
async def get_data_suggestions(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Retorna sugestões de conflito de dados pendentes para um processo.
    
    O DataConflictResolver no frontend consome este endpoint para
    mostrar ao utilizador as diferenças entre dados atuais e dados OCR.
    
    Args:
        process_id: ID do processo.
    
    Returns:
        Lista de sugestões pendentes com campo, valor atual e valor sugerido.
    """
    return await run_get_data_suggestions(process_id)


@router.post("/process/{process_id}/resolve-conflict", responses={404: HTTP_404_RESPONSE})
async def resolve_data_conflict(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Resolve um conflito de dados individual.
    
    Body:
        - suggestion_id: ID da sugestão (opcional, alternativa ao field)
        - field: Nome do campo em conflito (alternativa ao suggestion_id)
        - choice: 'current' (manter actual) ou 'ai' (aceitar valor da IA)
    
    Returns:
        Resultado da resolução.
    """
    return await run_resolve_data_conflict(process_id, data, user=user)


@router.post("/process/{process_id}/confirm-data", responses={404: HTTP_404_RESPONSE})
async def confirm_process_data(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Confirma ou desconfirma os dados do processo.
    
    Quando confirmados, o sistema deixa de criar sugestões de conflito
    automaticamente (o utilizador pode desbloquear depois).
    
    Body:
        - confirmed: true para confirmar, false para desbloquear
    """
    return await run_confirm_process_data(process_id, data, user=user)
