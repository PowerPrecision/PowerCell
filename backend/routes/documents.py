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
    from services.file_converter import can_convert_file, detect_file_type
    
    try:
        # Ler o conteúdo do ficheiro
        file_content = await file.read()
        filename = file.filename
        
        if not file_content or len(file_content) == 0:
            return {
                "can_upload": False,
                "reason": "Ficheiro vazio",
                "filename": filename
            }
        
        # Detectar tipo real
        detected_mime, detected_ext, confidence = detect_file_type(file_content)
        
        # Verificar se pode ser convertido
        conversion_check = can_convert_file(file_content, filename)
        
        # Verificar tamanho
        file_size_mb = len(file_content) / (1024 * 1024)
        
        return {
            "can_upload": conversion_check["can_convert"] != False,
            "filename": filename,
            "file_size_mb": round(file_size_mb, 2),
            "detected_type": detected_mime,
            "detected_extension": detected_ext,
            "confidence": confidence,
            "conversion_info": conversion_check,
            "recommendation": conversion_check.get("suggested_action", "Pode fazer upload diretamente")
        }
        
    except Exception as e:
        logger.error(f"[CHECK-FILE] Erro: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao verificar ficheiro: {str(e)}"
        )


@router.post("/client/{client_id}/init-folders", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def initialize_folders(client_id: str, user: dict = Depends(get_current_user)):
    """Cria a estrutura de pastas inicial no S3 (se não existir)."""
    process, effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[INIT-FOLDERS]",
        client_without_process_detail=(
            "Cliente encontrado mas sem processo associado. "
            "Não é possível inicializar pastas."
        ),
    )

    # Verificar se já existe mapeamento S3 - NÃO criar duplicados
    existing_s3_folder = process.get("s3_folder")
    if existing_s3_folder:
        # Verificar se a pasta ainda existe no S3
        if s3_service._folder_exists(existing_s3_folder):
            logger.info(f"Pasta S3 já existe para cliente {client_id}: {existing_s3_folder}")
            return {"success": True, "s3_folder": existing_s3_folder, "already_exists": True}
        # Se não existe, continuar para criar nova
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = extract_second_client_name(process)
    
    success, s3_folder_path = s3_service.initialize_client_folders(
        effective_id, 
        client_name,
        second_client_name=second_client_name
    )
    
    # Se criou as pastas, guardar mapeamento no processo
    if success and s3_folder_path:
        await db.processes.update_one(
            {"id": effective_id},
            {"$set": {"s3_folder": s3_folder_path}}
        )
    
    return {"success": success, "s3_folder": s3_folder_path}


@router.get("/client/{client_id}/download", responses={403: HTTP_403_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def get_download_url(
    client_id: str,
    file_path: str,
    user: dict = Depends(get_current_user)
):
    """Gera um URL temporário para download de um ficheiro."""
    process, _effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[DOWNLOAD]",
        client_without_process_detail=(
            "Cliente encontrado mas sem processo associado. "
            "Não é possível gerar link de download."
        ),
    )
    assert_s3_file_belongs_to_process(file_path, process)
    
    url = s3_service.get_presigned_url(file_path)
    if not url:
        raise HTTPException(status_code=500, detail=ERROR_DOWNLOAD_URL)
    
    return {"success": True, "url": url}


@router.get("/download-url/{file_path:path}", responses={500: HTTP_500_RESPONSE})
async def get_download_url_by_path(
    file_path: str,
    user: dict = Depends(get_current_user)
):
    """
    Gera URL temporário (pre-signed) para download ou preview de um
    ficheiro por caminho S3 direto.

    Porquê pre-signed URLs em vez de servir o ficheiro pelo backend:
    - Reduz drasticamente o consumo de RAM e largura de banda do servidor.
    - O ficheiro vai diretamente do S3 para o browser do utilizador.
    - A URL expira automaticamente (segurança temporal).
    - Permite preview inline de PDFs no browser sem download completo.

    Args:
        file_path: Caminho completo do ficheiro no S3.
        user: Utilizador autenticado (injetado pelo Depends).

    Returns:
        dict: URL temporário para download/preview.
    """
    import asyncio
    
    # Tentar path original e variações
    variations = [file_path]
    
    # Variação com underscores -> espaços
    if '_' in file_path:
        variations.append(file_path.replace('_', ' '))
    
    # Variação com espaços -> underscores
    if ' ' in file_path:
        variations.append(file_path.replace(' ', '_'))
    
    # Variação com a pasta "Documentação Clientes"
    if 'Documentação Clientes/' in file_path:
        variations.append(file_path.replace('Documentação Clientes/', 'Documentação_Clientes/'))
    if 'Documentação_Clientes/' in file_path:
        variations.append(file_path.replace('Documentação_Clientes/', 'Documentação Clientes/'))
    
    # Verificar qual variação existe no S3
    loop = asyncio.get_event_loop()
    for path in variations:
        exists = await loop.run_in_executor(None, lambda p=path: s3_service.file_exists(p))
        if exists:
            url = s3_service.get_presigned_url(path)
            if url:
                logger.info(f"[DOWNLOAD-URL] URL gerado para: {path}")
                return {"url": url, "path": path}
    
    logger.warning(f"[DOWNLOAD-URL] Ficheiro não encontrado (tentadas {len(variations)} variações): {file_path}")
    raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)


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
    from fastapi.responses import StreamingResponse
    from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
    import asyncio
    
    # Log do pedido para debugging
    logger.info(f"[PROXY] Acesso a ficheiro: {file_path}")
    
    if not s3_service.is_configured():
        logger.error("[PROXY] S3 não configurado")
        raise HTTPException(status_code=500, detail=ERROR_S3_NOT_CONFIGURED)
    
    # Função auxiliar para obter ficheiro do S3
    def get_s3_object(key):
        """Obtém um objeto do S3 pela chave (bucket e key configurados no serviço).

        Args:
            key: Caminho completo do objeto no S3 (ex: "clients/123/Financeiros/doc.pdf").

        Returns:
            dict: Resposta do botocore get_object com Body, ContentType, etc.

        Raises:
            botocore.exceptions.ClientError: Se o objeto não existir ou acesso negado.
        """
        return s3_service.s3_client.get_object(
            Bucket=s3_service.bucket_name,
            Key=key
        )
    
    # Gerar variações do path (underscore <-> espaço)
    path_variations = [file_path]
    
    # Variação com underscores -> espaços
    if '_' in file_path:
        path_variations.append(file_path.replace('_', ' '))
    
    # Variação com espaços -> underscores  
    if ' ' in file_path:
        path_variations.append(file_path.replace(' ', '_'))
    
    # Variação com a pasta "Documentação Clientes" <-> "Documentação_Clientes"
    if 'Documentação Clientes/' in file_path:
        path_variations.append(file_path.replace('Documentação Clientes/', 'Documentação_Clientes/'))
    if 'Documentação_Clientes/' in file_path:
        path_variations.append(file_path.replace('Documentação_Clientes/', 'Documentação Clientes/'))
    
    response = None
    used_path = None
    last_error = None
    
    loop = asyncio.get_event_loop()
    
    for try_path in path_variations:
        try:
            response = await loop.run_in_executor(None, lambda p=try_path: get_s3_object(p))
            used_path = try_path
            logger.info(f"[PROXY] Ficheiro encontrado com path: {try_path}")
            break
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchKey':
                logger.debug(f"[PROXY] Path não encontrado: {try_path}")
                last_error = f"Ficheiro não encontrado: {try_path}"
                continue
            elif error_code == 'AccessDenied':
                logger.error(f"[PROXY] Acesso negado ao ficheiro: {try_path}")
                last_error = f"Acesso negado: {try_path}"
                continue
            else:
                logger.error(f"[PROXY] Erro S3 ({error_code}) no path {try_path}: {e}")
                last_error = f"Erro S3 ({error_code}): {try_path}"
                continue
        except NoCredentialsError:
            logger.error("[PROXY] Credenciais S3 não configuradas")
            raise HTTPException(status_code=500, detail="Credenciais S3 não configuradas")
        except Exception as e:
            logger.error(f"[PROXY] Erro inesperado ao tentar {try_path}: {type(e).__name__}: {e}")
            last_error = f"Erro: {str(e)}"
            continue
    
    if response is None:
        logger.warning(f"[PROXY] Ficheiro não encontrado em nenhuma variação: {file_path}")
        raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)
    
    try:
        # Determinar content-type
        content_type = response.get('ContentType', 'application/octet-stream')
        content_length = response.get('ContentLength', 0)
        
        # Extrair nome do ficheiro
        filename = used_path.split('/')[-1] if '/' in used_path else used_path
        
        logger.info(f"[PROXY] Streaming ficheiro: {filename} ({content_length} bytes)")
        
        # Criar generator para streaming
        def iterfile():
            body = response['Body']
            try:
                while True:
                    chunk = body.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    yield chunk
            finally:
                body.close()
        
        # Codificar filename para HTTP header (suporta Unicode)
        from urllib.parse import quote
        encoded_filename = quote(filename, safe='')
        
        headers = {
            'Content-Disposition': f"inline; filename*=UTF-8''{encoded_filename}",
            'Content-Length': str(content_length),
            'Cache-Control': 'private, max-age=3600',
        }
        
        return StreamingResponse(
            iterfile(),
            media_type=content_type,
            headers=headers
        )
        
    except (BotoCoreError, IOError, OSError) as e:
        logger.error(f"[PROXY] Erro ao fazer proxy do ficheiro S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter ficheiro: {str(e)}")
    except Exception as e:
        logger.error(f"[PROXY] Erro inesperado: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


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
    process, _effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[DELETE]",
        client_without_process_detail=(
            "Cliente encontrado mas sem processo associado. "
            "Não é possível eliminar ficheiros."
        ),
    )

    # Verificar se é um caminho de ficheiro válido (não pode terminar com /)
    if file_path.endswith('/'):
        raise HTTPException(
            status_code=400, 
            detail="Caminho inválido: não pode eliminar pastas. Selecione um ficheiro específico."
        )

    assert_s3_file_belongs_to_process(file_path, process)
    
    # ====================================================================
    # PROTECÇÃO DE ELIMINAÇÃO SEGURA — Scope Global
    # Se o documento é 'global' do cliente (ex: Cartão de Cidadão),
    # verificar se está referenciado por OUTROS processos ativos antes
    # de eliminar. Isto previne a perda de documentos partilhados.
    # ====================================================================
    doc_metadata = await db.document_metadata.find_one({"s3_path": file_path}, {"_id": 0})
    doc_scope = doc_metadata.get("doc_scope") if doc_metadata else None
    doc_client_id = doc_metadata.get("client_id") if doc_metadata else None
    
    # Documentos de scope 'global' requerem verificação de referências cruzadas
    if doc_scope == "global" or (doc_client_id and doc_client_id != client_id):
        # Determinar o client_id do documento (pode ser o mesmo do processo ou diferente)
        effective_client_id = doc_client_id or process.get("client_id") or client_id
        
        # Buscar TODOS os processos ativos deste cliente (excluindo o processo actual)
        other_processes = await db.processes.find(
            {
                "client_id": effective_client_id,
                "id": {"$ne": client_id},
                "is_deleted": {"$ne": True},
                "status": {"$nin": ["eliminados", "desistencias"]},
            },
            {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, "status": 1, "document_ids": 1, "required_documents": 1, "checklist": 1}
        ).to_list(100)
        
        # Verificar se o documento está referenciado em qualquer outro processo
        for other_proc in other_processes:
            # Verificar arrays que podem referenciar documentos
            doc_ids = other_proc.get("document_ids") or []
            required_docs = other_proc.get("required_documents") or []
            checklist = other_proc.get("checklist") or []
            
            # Verificar se o s3_path ou o ID do documento está referenciado
            doc_id = doc_metadata.get("id") if doc_metadata else None
            
            is_referenced = False
            reference_source = ""
            
            # Verificar document_ids
            if file_path in doc_ids or (doc_id and doc_id in doc_ids):
                is_referenced = True
                reference_source = "document_ids"
            # Verificar required_documents
            elif isinstance(required_docs, list):
                for req_doc in required_docs:
                    if isinstance(req_doc, dict):
                        if req_doc.get("s3_path") == file_path or req_doc.get("id") == doc_id:
                            is_referenced = True
                            reference_source = "required_documents"
                            break
                    elif isinstance(req_doc, str) and (req_doc == file_path or req_doc == doc_id):
                        is_referenced = True
                        reference_source = "required_documents"
                        break
            # Verificar checklist
            if not is_referenced and isinstance(checklist, list):
                for check_item in checklist:
                    if isinstance(check_item, dict):
                        if check_item.get("s3_path") == file_path or check_item.get("document_id") == doc_id:
                            is_referenced = True
                            reference_source = "checklist"
                            break
            
            # Verificar também se o S3 path começa com o prefixo da pasta do outro processo
            if not is_referenced:
                other_s3_folder = other_proc.get("s3_folder")
                if other_s3_folder and file_path.startswith(other_s3_folder.rstrip('/') + '/'):
                    is_referenced = True
                    reference_source = "s3_folder"
            
            if is_referenced:
                proc_number = other_proc.get("process_number", "N/A")
                proc_name = other_proc.get("client_name", "Cliente")
                proc_status = other_proc.get("status", "ativo")
                filename = file_path.split('/')[-1] if '/' in file_path else file_path
                
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Não é possível eliminar: Este documento está a ser utilizado "
                        f"no Processo #{proc_number} ({proc_name})."
                    )
                )
    
    # Guardar nome do ficheiro antes de eliminar
    filename = file_path.split('/')[-1] if '/' in file_path else file_path
    
    success = s3_service.delete_file(file_path)
    if not success:
        raise HTTPException(status_code=500, detail=ERROR_DELETE_FILE)
    
    # Eliminar metadados do documento
    if doc_metadata:
        await db.document_metadata.delete_one({"s3_path": file_path})
    
    # Registar no histórico
    await log_history(
        process_id=client_id,
        user=user,
        action="Eliminou documento",
        field="documento",
        old_value=filename
    )
    
    # Retornar JSONResponse explicitamente para compatibilidade com slowapi rate limiter
    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Ficheiro eliminado"}
    )


@router.post("/client/{client_id}/bulk-delete", responses={400: HTTP_400_RESPONSE, 403: HTTP_403_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
@limiter.limit("30/minute")
async def bulk_delete_files(
    client_id: str,
    request: Request,
    data: dict = Body(...),
    user: dict = Depends(get_current_user)
):
    """Elimina múltiplos ficheiros do S3 de uma só vez."""
    file_paths = data.get("file_paths", [])
    
    if not file_paths or not isinstance(file_paths, list) or len(file_paths) == 0:
        raise HTTPException(
            status_code=400, 
            detail="Lista de ficheiros vazia ou inválida"
        )
    
    process, _effective_id = await resolve_process_from_flexible_id(
        client_id,
        log_prefix="[DELETE-BATCH]",
    )
    valid_prefixes = build_s3_valid_prefixes(process)
    
    deleted_count = 0
    failed_files = []
    
    for file_path in file_paths:
        # Ignorar pastas (paths que terminam com /)
        if file_path.endswith('/'):
            continue
        
        # Verificar se o ficheiro pertence ao cliente
        if not any(file_path.startswith(prefix) for prefix in valid_prefixes):
            failed_files.append(file_path)
            continue
        
        try:
            success = s3_service.delete_file(file_path)
            if success:
                deleted_count += 1
            else:
                failed_files.append(file_path)
        except Exception as e:
            logger.warning(f"Erro ao eliminar ficheiro {file_path}: {e}")
            failed_files.append(file_path)
    
    # Registar no histórico
    if deleted_count > 0:
        await log_history(
            process_id=client_id,
            user=user,
            action="Eliminou documentos em massa",
            field="documento",
            old_value=f"{deleted_count} ficheiro(s)"
        )
    
    result = {
        "success": True,
        "deleted_count": deleted_count,
        "total_requested": len(file_paths),
    }
    
    if failed_files:
        result["failed_count"] = len(failed_files)
        result["failed_files"] = failed_files
    
    return JSONResponse(status_code=200, content=result)


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
EXPIRY_WARNING_DAYS = 60 

@router.post("/expiry", response_model=DocumentExpiryResponse, responses={404: HTTP_404_RESPONSE})
async def create_document_expiry(
    data: DocumentExpiryCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.INDEXACAO]))
):
    """Registar validade de um documento."""
    process = await db.processes.find_one({"id": data.process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Sanitizar inputs do utilizador antes de guardar
    sanitized_document_name = sanitize_string(data.document_name, max_length=300) if data.document_name else data.document_name
    sanitized_notes = sanitize_string(data.notes, max_length=1000) if data.notes else data.notes
    
    doc = {
        "id": doc_id,
        "process_id": data.process_id,
        "document_type": data.document_type,
        "document_name": sanitized_document_name,
        "expiry_date": data.expiry_date,
        "notes": sanitized_notes,
        "created_at": now,
        "created_by": user["id"]
    }
    
    await db.document_expiries.insert_one(doc)
    return DocumentExpiryResponse(**{k: v for k, v in doc.items() if k != "_id"})

@router.get("/expiry", response_model=List[DocumentExpiryResponse], responses={500: HTTP_500_RESPONSE})
async def get_document_expiries(
    process_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Obter registos de validade."""
    query = {}
    if process_id:
        query["process_id"] = process_id
    elif user["role"] == UserRole.CONSULTOR:
        processes = await db.processes.find({"assigned_consultor_id": user["id"]}, {"id": 1}).to_list(1000)
        query["process_id"] = {"$in": [p["id"] for p in processes]}
    elif user["role"] == UserRole.INTERMEDIARIO:
        processes = await db.processes.find({"assigned_mediador_id": user["id"]}, {"id": 1}).to_list(1000)
        query["process_id"] = {"$in": [p["id"] for p in processes]}
    
    docs = await db.document_expiries.find(query, {"_id": 0}).to_list(1000)
    return [DocumentExpiryResponse(**d) for d in docs]

@router.get("/expiry/upcoming", responses={500: HTTP_500_RESPONSE})
async def get_upcoming_expiries(
    days: int = EXPIRY_WARNING_DAYS,
    user: dict = Depends(get_current_user)
):
    """Alertas de documentos a expirar."""
    today = datetime.now(timezone.utc).date()
    future_date = today + timedelta(days=days)
    excluded_statuses = ["concluido", "desistencia", "desistência"]
    
    query = {
        "expiry_date": {
            "$gte": today.isoformat(),
            "$lte": future_date.isoformat()
        }
    }
    
    # Filtros de role (simplificado para brevidade, mantém a lógica original)
    if user["role"] == UserRole.CONSULTOR:
        procs = await db.processes.find({"$or": [{"assigned_consultor_id": user["id"]}, {"consultor_id": user["id"]}]}, {"id": 1}).to_list(1000)
        query["process_id"] = {"$in": [p["id"] for p in procs]} if procs else {"$in": []}
    
    docs = await db.document_expiries.find(query, {"_id": 0}).sort("expiry_date", 1).to_list(1000)
    
    result = []
    for doc in docs:
        process = await db.processes.find_one({"id": doc["process_id"]}, {"_id": 0})
        if process and process.get("status", "").lower() not in excluded_statuses:
            expiry = datetime.strptime(doc["expiry_date"], "%Y-%m-%d").date()
            days_until = (expiry - today).days
            result.append({
                **doc,
                "client_name": process.get("client_name"),
                "days_until_expiry": days_until,
                "urgency": "critical" if days_until <= 7 else "warning" if days_until <= 30 else "normal"
            })
    return result

@router.get("/expiry/calendar", responses={500: HTTP_500_RESPONSE})
async def get_expiry_calendar_events(user: dict = Depends(get_current_user)):
    """Eventos para calendário."""
    upcoming = await get_upcoming_expiries(days=EXPIRY_WARNING_DAYS, user=user)
    events = []
    for doc in upcoming:
        color = "#EF4444" if doc["urgency"] == "critical" else "#F59E0B" if doc["urgency"] == "warning" else "#3B82F6"
        events.append({
            "id": f"doc-expiry-{doc['id']}",
            "title": f"📄 {doc['document_name']} - {doc['client_name']}",
            "date": doc["expiry_date"],
            "color": color
        })
    return events

@router.delete("/expiry/{doc_id}", responses={404: HTTP_404_RESPONSE})
async def delete_document_expiry(doc_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.INDEXACAO]))):
    """Remove uma regra de validade de documento.

    Porquê um endpoint dedicado: permite ao admin ou consultor remover
    regras de validade incorretamente configuradas (ex: data de validade
    errada ou documento que já não é necessário).

    Args:
        doc_id: ID da regra de validade a eliminar.
        user: Utilizador autenticado com role permitido (injetado).

    Returns:
        dict: ``{"message": "Eliminado"}``.

    Raises:
        HTTPException(404): Se registo de validade não encontrado.
    """
    delete_result = await db.document_expiries.delete_one({"id": doc_id})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=ERROR_RECORD_NOT_FOUND)
    return {"message": "Eliminado"}

# Tipos de documentos (mantido)
DOCUMENT_TYPES = [
    {"type": "cc", "name": "Cartão de Cidadão", "validity_years": 5},
    {"type": "irs", "name": "Declaração de IRS", "validity_years": 1},
    {"type": "recibo", "name": "Recibo Vencimento", "validity_months": 3},
    {"type": "outro", "name": "Outro", "validity_years": None},
]

@router.get("/types", responses={500: HTTP_500_RESPONSE})
async def get_document_types(user: dict = Depends(get_current_user)):
    """Retorna a lista de tipos de documentos suportados com prazos de validade.

    Os tipos incluem informação sobre o tempo de validade padrão
    (ex: CC = 5 anos, IRS = 1 ano, Recibo = 3 meses). Esta informação
    é usada para calcular automaticamente a data de alerta de validade
    quando um documento é categorizado.

    Args:
        user: Utilizador autenticado (injetado).

    Returns:
        list[dict]: Lista de tipos com type, name, validity_years e
            validity_months.
    """
    return DOCUMENT_TYPES


# ====================================================================
# PARTE 3: CATEGORIZAÇÃO E PESQUISA COM IA (NOVO)
# ====================================================================

from services.document_categorization import (
    extract_text_from_pdf,
    categorize_document_with_ai,
    search_documents_by_content
)
from models.document import (
    DocumentSearchRequest
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
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    now = datetime.now(timezone.utc).isoformat()
    
    # Verificar se já existe metadados para este ficheiro
    existing = await db.document_metadata.find_one({"s3_path": s3_path}, {"_id": 0})
    
    # Obter o ficheiro do S3
    try:
        file_content = s3_service.get_file_content(s3_path)
        if not file_content:
            raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)
    except (IOError, OSError, ValueError, KeyError, TypeError) as e:
        logger.error(f"Erro ao obter ficheiro do S3: {e}")
        raise HTTPException(status_code=500, detail=ERROR_S3_ACCESS)
    
    # Extrair texto do documento
    extracted_text = ""
    if filename.lower().endswith('.pdf'):
        extracted_text = extract_text_from_pdf(file_content)
    
    # Se não conseguir extrair texto, usar apenas o nome do ficheiro
    text_for_analysis = extracted_text if extracted_text else f"{DEFAULT_FILE_PREFIX}{filename}"
    
    # Obter categorias existentes para consistência
    existing_categories = await db.document_metadata.distinct("ai_category")
    
    # Categorizar com IA
    result = await categorize_document_with_ai(
        text_content=text_for_analysis,
        filename=filename,
        existing_categories=existing_categories
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=500, 
            detail=result.get("error", ERROR_CATEGORIZE_DOC)
        )
    
    # Criar ou actualizar metadados
    doc_id = existing.get("id") if existing else str(uuid.uuid4())
    
    metadata = {
        "id": doc_id,
        "process_id": process_id,
        "client_name": client_name,
        "s3_path": s3_path,
        "filename": filename,
        "ai_category": result.get("category"),
        "ai_subcategory": result.get("subcategory"),
        "ai_confidence": result.get("confidence"),
        "ai_tags": result.get("tags", []),
        "ai_summary": result.get("summary"),
        "expiry_date": result.get("expiry_date"),  # Nova: data de validade
        "expiry_alert_sent": False,  # Nova: flag de alerta
        "extracted_text": extracted_text[:5000] if extracted_text else None,  # Limitar tamanho
        "file_size": len(file_content),
        "mime_type": MIME_TYPE_PDF if filename.lower().endswith('.pdf') else None,
        "is_categorized": True,
        "categorized_at": now,
        "updated_at": now
    }
    
    if existing:
        await db.document_metadata.update_one(
            {"id": doc_id},
            {"$set": metadata}
        )
    else:
        metadata["created_at"] = now
        await db.document_metadata.insert_one(metadata)
    
    return {
        "success": True,
        "id": doc_id,
        "category": result.get("category"),
        "subcategory": result.get("subcategory"),
        "confidence": result.get("confidence"),
        "tags": result.get("tags", []),
        "summary": result.get("summary"),
        "expiry_date": result.get("expiry_date")
    }


@router.post("/categorize-all/{process_id}", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def categorize_all_documents(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Categorizar TODOS os documentos de um cliente/processo.
    Processa documentos que ainda não foram categorizados.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    # Obter segundo titular se existir (com verificação de None)
    titular2_cat = process.get("titular2_data") or {}
    second_client_name = process.get("second_client_name") or titular2_cat.get("nome") or titular2_cat.get("name")
    
    # Executar operação síncrona do S3 em thread separada para não bloquear o event loop
    loop = asyncio.get_event_loop()
    files_data = await loop.run_in_executor(
        None,
        lambda: s3_service.list_files(process_id, client_name, second_client_name)
    )
    files = files_data.get("files", {})
    
    results = {
        "total": 0,
        "categorized": 0,
        "skipped": 0,
        "errors": 0,
        "documents": []
    }
    
    # Obter categorias existentes
    existing_categories = await db.document_metadata.distinct("ai_category")
    now = datetime.now(timezone.utc).isoformat()
    
    # Processar cada categoria de ficheiros
    for category, file_list in files.items():
        for file_info in file_list:
            results["total"] += 1
            
            s3_path = file_info.get("path")
            filename = file_info.get("name")
            
            if not s3_path or not filename:
                continue
            
            # Verificar se já foi categorizado
            existing = await db.document_metadata.find_one(
                {"s3_path": s3_path, "is_categorized": True},
                {"_id": 0}
            )
            
            if existing:
                results["skipped"] += 1
                results["documents"].append({
                    "filename": filename,
                    "status": "skipped",
                    "category": existing.get("ai_category")
                })
                continue
            
            try:
                # Obter ficheiro do S3
                file_content = s3_service.get_file_content(s3_path)
                if not file_content:
                    results["errors"] += 1
                    continue
                
                # Extrair texto
                extracted_text = ""
                if filename.lower().endswith('.pdf'):
                    extracted_text = extract_text_from_pdf(file_content)
                
                text_for_analysis = extracted_text if extracted_text else f"{DEFAULT_FILE_PREFIX}{filename}"
                
                # Categorizar
                result = await categorize_document_with_ai(
                    text_content=text_for_analysis,
                    filename=filename,
                    existing_categories=existing_categories
                )
                
                if result.get("success"):
                    # Guardar metadados
                    doc_id = str(uuid.uuid4())
                    metadata = {
                        "id": doc_id,
                        "process_id": process_id,
                        "client_name": client_name,
                        "s3_path": s3_path,
                        "filename": filename,
                        "ai_category": result.get("category"),
                        "ai_subcategory": result.get("subcategory"),
                        "ai_confidence": result.get("confidence"),
                        "ai_tags": result.get("tags", []),
                        "ai_summary": result.get("summary"),
                        "expiry_date": result.get("expiry_date"),  # Nova: data de validade
                        "expiry_alert_sent": False,  # Nova: flag de alerta
                        "extracted_text": extracted_text[:5000] if extracted_text else None,
                        "file_size": len(file_content),
                        "is_categorized": True,
                        "categorized_at": now,
                        "created_at": now,
                        "updated_at": now
                    }
                    
                    await db.document_metadata.insert_one(metadata)
                    
                    # Actualizar lista de categorias
                    if result.get("category") and result["category"] not in existing_categories:
                        existing_categories.append(result["category"])
                    
                    results["categorized"] += 1
                    results["documents"].append({
                        "filename": filename,
                        "status": "categorized",
                        "category": result.get("category"),
                        "subcategory": result.get("subcategory"),
                        "expiry_date": result.get("expiry_date")
                    })
                else:
                    results["errors"] += 1
                    results["documents"].append({
                        "filename": filename,
                        "status": "error",
                        "error": result.get("error")
                    })
                    
            except (IOError, OSError, ValueError, KeyError, TypeError) as e:
                logger.error(f"Erro ao categorizar documento")
                results["errors"] += 1
                results["documents"].append({
                    "filename": filename,
                    "status": "error",
                    "error": str(e)
                })
    
    return results


@router.get("/process/{process_id}", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def get_process_documents(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter lista simples de documentos de um processo.
    Usado pelo modal de envio de documentação para balcões.
    
    Retorna documentos da coleção document_metadata.
    Se não houver metadados, faz fallback para listar ficheiros do S3.
    
    Retorna:
    - id: ID do documento
    - filename: Nome do ficheiro
    - original_name: Nome original
    - category: Categoria (se disponível)
    - s3_path: Caminho no S3
    - file_size: Tamanho do ficheiro
    - upload_date: Data de upload
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    # Obter metadados dos documentos
    metadata_docs = await db.document_metadata.find(
        {"process_id": process_id},
        {"_id": 0}
    ).to_list(1000)
    
    # Converter para formato simples
    documents = []
    # Conjunto de s3_paths já adicionados via metadados (para evitar duplicados)
    existing_s3_paths = set()
    for doc in metadata_docs:
        s3_path = doc.get("s3_path", "")
        if s3_path:
            existing_s3_paths.add(s3_path)
        documents.append({
            "id": doc.get("id") or str(uuid.uuid4()),
            "filename": doc.get("filename"),
            "original_name": doc.get("filename"),
            "category": doc.get("ai_category"),
            "subcategory": doc.get("ai_subcategory"),
            "s3_path": s3_path,
            "file_size": doc.get("file_size"),
            "upload_date": doc.get("created_at") or doc.get("categorized_at"),
            "mime_type": doc.get("mime_type")
        })
    
    # Complementar com ficheiros do S3 que não estão nos metadados
    if s3_service.is_configured():
        try:
            client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
            titular2 = process.get("titular2_data") or {}
            second_client_name = process.get("second_client_name") or titular2.get("nome") or titular2.get("name")
            s3_folder = process.get("s3_folder")
            
            loop = asyncio.get_event_loop()
            files_result = await loop.run_in_executor(
                None,
                lambda: s3_service.list_files(process_id, client_name, second_client_name, s3_folder)
            )
            
            if isinstance(files_result, dict) and files_result.get("error"):
                logger.warning(f"[DOCS-PROCESS] S3 error: {files_result['error']}")
            elif isinstance(files_result, dict) and files_result.get("files"):
                # list_files retorna: {"files": {"Financeiros": [...], "Pessoais": [...], ...}, ...}
                s3_files_map = files_result["files"]
                for category, files in s3_files_map.items():
                    if isinstance(files, list):
                        for f in files:
                            s3_path = f.get("path") or f.get("key") or ""
                            filename = f.get("name") or f.get("filename") or ""
                            # Só adicionar se não existe nos metadados
                            if s3_path and s3_path not in existing_s3_paths:
                                existing_s3_paths.add(s3_path)
                                documents.append({
                                    "id": str(uuid.uuid4()),
                                    "filename": filename,
                                    "original_name": filename,
                                    "category": category if category != "Outros" else None,
                                    "s3_path": s3_path,
                                    "file_size": f.get("size"),
                                    "upload_date": f.get("last_modified"),
                                    "mime_type": None
                                })
        except Exception as e:
            logger.warning(f"[DOCS-PROCESS] Fallback S3 falhou: {e}")
    
    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "documents": documents,
        "total": len(documents)
    }


@router.get("/metadata/{process_id}", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def get_document_metadata(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter metadados de todos os documentos de um processo.
    Inclui categorização IA se disponível.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    # Obter metadados existentes
    metadata_list = await db.document_metadata.find(
        {"process_id": process_id},
        {"_id": 0, "extracted_text": 0}  # Não retornar texto completo
    ).to_list(1000)
    
    # Adicionar temporary_url a cada documento
    for doc in metadata_list:
        s3_path = doc.get("s3_path")
        if s3_path:
            doc["temporary_url"] = s3_service.get_presigned_url(s3_path) or ""
    
    # Obter categorias únicas
    categories = await db.document_metadata.distinct(
        "ai_category",
        {"process_id": process_id, "ai_category": {"$ne": None}}
    )
    
    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "documents": metadata_list,
        "total": len(metadata_list),
        "categorized": sum(1 for d in metadata_list if d.get("is_categorized")),
        "categories": sorted(categories)
    }


@router.post("/search", responses={500: HTTP_500_RESPONSE})
async def search_documents(
    request: DocumentSearchRequest,
    user: dict = Depends(get_current_user)
):
    """
    Pesquisar documentos por conteúdo.
    
    Pesquisa em:
    - Nome do ficheiro
    - Categoria e subcategoria IA
    - Tags
    - Resumo
    - Texto extraído
    """
    query = {"is_categorized": True}
    
    # Filtrar por processo se especificado
    if request.process_id:
        query["process_id"] = request.process_id
    
    # Filtrar por categorias se especificado
    if request.categories:
        query["ai_category"] = {"$in": request.categories}
    
    # Obter documentos
    documents = await db.document_metadata.find(query, {"_id": 0}).to_list(1000)
    
    # Pesquisar
    results = await search_documents_by_content(
        query=request.query,
        process_id=request.process_id,
        documents=documents,
        limit=request.limit
    )
    
    # Adicionar temporary_url aos resultados
    for doc in results:
        s3_path = doc.get("s3_path")
        if s3_path:
            doc["temporary_url"] = s3_service.get_presigned_url(s3_path) or ""
    
    return {
        "query": request.query,
        "total_results": len(results),
        "results": results
    }


@router.get("/categories", responses={500: HTTP_500_RESPONSE})
async def get_all_categories(
    process_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Obter todas as categorias de documentos.
    Opcionalmente filtrar por processo.
    """
    query = {"ai_category": {"$ne": None}}
    
    if process_id:
        query["process_id"] = process_id
    
    # Contar documentos por categoria
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$ai_category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    category_counts = await db.document_metadata.aggregate(pipeline).to_list(100)
    
    return {
        "categories": [
            {
                "name": cat["_id"],
                "count": cat["count"]
            }
            for cat in category_counts if cat["_id"]
        ],
        "total_categories": len(category_counts)
    }



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

@router.post("/ai-analyze/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def ai_analyze_documents(
    request: Request,
    process_id: str,
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user)
):
    """
    Analisa documentos com IA para extração de dados.
    
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
        
    Returns:
        Resultado da análise com comparações e sugestões
    """
    return await run_ai_analyze_documents(process_id, files, user=user)


@router.post("/ai-apply-suggestions/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def apply_ai_suggestions(
    process_id: str,
    suggestions: Dict = Body(default=None),
    user: dict = Depends(get_current_user)
):
    """
    Aplica sugestões da análise IA aos dados do cliente.
    
    Args:
        process_id: ID do processo
        suggestions: Dicionário com campo: valor a aplicar
        
    Returns:
        Resultado da atualização
    """
    if not suggestions:
        raise HTTPException(status_code=400, detail=ERROR_NO_SUGGESTIONS)
    
    # Buscar processo
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    # SECURITY: Verificar permissão de edição antes de aplicar sugestões
    can_edit, reason = can_edit_process_data(user, process)
    if not can_edit:
        logger.warning(f"IDOR attempt: User {user.get('id')} ({user.get('role')}) tried to apply AI suggestions on process {process_id}: {reason}")
        raise HTTPException(status_code=403, detail=f"Não tem permissões para alterar este processo. {reason}")
    
    # Mapeamento de campos frontend para subdocumentos aninhados no backend
    # Cada entrada: (campo_frontend) → (subdocumento.campo_backend)
    personal_fields = {
        "client_name": "client_name",       # top-level
        "nif": "personal_data.nif",
        "documento_id": "personal_data.documento_id",
        "cc_number": "personal_data.documento_id",
        "birth_date": "personal_data.data_nascimento",
        "cc_validity": "personal_data.cc_validity",
        "nationality": "personal_data.nacionalidade",
        "gender": "personal_data.sexo",
        "address": "personal_data.morada",
        "fiscal_address": "personal_data.morada_fiscal",
        "estado_civil": "personal_data.estado_civil",
    }
    financial_fields = {
        "rendimento_mensal": "financial_data.rendimento_mensal",
        "salario_liquido": "financial_data.rendimento_mensal",
        "rendimento_bruto": "financial_data.rendimento_bruto",
        "salario_bruto": "financial_data.rendimento_bruto",
        "empresa": "financial_data.empresa",
        "entidade_empregadora": "financial_data.empresa",
        "tipo_contrato": "financial_data.tipo_contrato",
        "categoria_profissional": "financial_data.categoria_profissional",
        "subsidiario_alimentacao": "financial_data.subsidiario_alimentacao",
    }
    real_estate_fields = {
        "valor_imovel": "real_estate_data.valor_imovel",
        "localizacao": "real_estate_data.localizacao",
        "tipologia": "real_estate_data.tipologia",
        "area": "real_estate_data.area",
        "artigo_matricial": "real_estate_data.artigo_matricial",
    }
    
    all_field_mappings = {**personal_fields, **financial_fields, **real_estate_fields}
    
    # Preparar actualizações por subdocumento
    update_data = {}
    for field, value in suggestions.items():
        if field in all_field_mappings:
            dot_path = all_field_mappings[field]
            update_data[dot_path] = value
    
    if not update_data:
        return {"success": True, "updated_fields": 0, "message": "Nenhum campo válido para atualizar"}
    
    # Construir update com dot notation para subdocumentos
    mongo_update = {}
    for dot_path, value in update_data.items():
        mongo_update[dot_path] = value
    
    mongo_update["updated_at"] = datetime.now(timezone.utc).isoformat()
    mongo_update["updated_by"] = user.get("id")
    
    await db.processes.update_one(
        {"id": process_id},
        {"$set": mongo_update}
    )
    
    logger.info(f"Campos atualizados via IA para processo: {sanitize_for_log(process_id)}")
    
    return {
        "success": True,
        "updated_fields": len(update_data) - 2,  # Excluir updated_at e updated_by
        "fields": list(update_data.keys())
    }


@router.post("/organize-files/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def organize_files_in_folders(
    process_id: str,
    organization: List[Dict] = None,
    user: dict = Depends(get_current_user)
):
    """
    Organiza ficheiros em pastas no S3 baseado na análise IA.
    
    Args:
        process_id: ID do processo
        organization: Lista de {file_name, source_path, target_folder}
        
    Returns:
        Resultado da organização
    """
    if not organization:
        raise HTTPException(status_code=400, detail=ERROR_NO_ORGANIZATION)
    
    # Buscar processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "client_name": 1})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    results = {"moved": [], "errors": []}
    
    for item in organization:
        try:
            source_path = item.get("source_path")
            target_folder = item.get("target_folder")
            file_name = item.get("file_name")
            
            if not all([source_path, target_folder, file_name]):
                results["errors"].append({"file": file_name, "error": "Dados incompletos"})
                continue
            
            # Mover ficheiro no S3 (copiar + apagar original)
            success = s3_service.move_file(source_path, client_name, target_folder, file_name)
            
            if success:
                results["moved"].append({"file": file_name, "to": target_folder})
            else:
                results["errors"].append({"file": file_name, "error": "Falha ao mover"})
                
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            results["errors"].append({"file": item.get("file_name", "?"), "error": str(e)})
    
    return {
        "success": True,
        "moved_count": len(results["moved"]),
        "error_count": len(results["errors"]),
        "results": results
    }


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

@router.post("/rename-smart/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def rename_document_smart(
    process_id: str,
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Renomeia um documento de forma inteligente baseado na análise IA.
    
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
    s3_path = data.get("s3_path")
    apply_ai_name = data.get("apply_ai_name", True)
    novo_nome = data.get("novo_nome")
    
    if not s3_path:
        raise HTTPException(status_code=400, detail=ERROR_S3_PATH_REQUIRED)
    
    # Obter processo e nome do cliente
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    
    # Extrair nome actual do ficheiro
    old_filename = s3_path.rsplit('/', 1)[-1] if '/' in s3_path else s3_path
    
    # Extrair extensão original
    if '.' in old_filename:
        original_ext = old_filename.rsplit('.', 1)[-1]
    else:
        original_ext = "pdf"
    
    # Obter metadados do documento (categorização IA)
    metadata = await db.document_metadata.find_one({"s3_path": s3_path}, {"_id": 0})
    
    if apply_ai_name:
        # Gerar nome baseado na IA
        if not metadata or not metadata.get("is_categorized"):
            raise HTTPException(
                status_code=400, 
                detail=ERROR_DOC_NOT_CATEGORIZED
            )
        
        new_filename = generate_smart_filename(
            category=metadata.get("ai_category", "Documento"),
            subcategory=metadata.get("ai_subcategory", ""),
            client_name=client_name,
            expiry_date=metadata.get("expiry_date"),
            original_extension=original_ext
        )
    else:
        # Usar nome manual fornecido
        if not novo_nome:
            raise HTTPException(status_code=400, detail=ERROR_NEW_NAME_REQUIRED)
        
        # Normalizar e garantir extensão
        if not novo_nome.endswith(f".{original_ext}"):
            new_filename = f"{novo_nome}.{original_ext}"
        else:
            new_filename = novo_nome
    
    # Calcular novo caminho
    if '/' in s3_path:
        folder_path = s3_path.rsplit('/', 1)[0]
        new_path = f"{folder_path}/{new_filename}"
    else:
        new_path = new_filename
    
    # Verificar se o nome mudou
    if new_path == s3_path:
        return {
            "success": True,
            "old_name": old_filename,
            "new_name": new_filename,
            "new_path": new_path,
            "message": "Ficheiro já tem o nome correcto"
        }
    
    try:
        # Executar renomeação no S3 (copy + delete)
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None,
            lambda: s3_service.rename_file(s3_path, new_path)
        )
        
        if not success:
            raise HTTPException(status_code=500, detail=ERROR_RENAME_FAILED)
        
        # Actualizar metadados
        if metadata:
            await db.document_metadata.update_one(
                {"s3_path": s3_path},
                {"$set": {
                    "s3_path": new_path,
                    "filename": new_filename,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        
        logger.info(f"Documento renomeado")
        
        return {
            "success": True,
            "old_name": old_filename,
            "new_name": new_filename,
            "new_path": new_path,
            "message": "Documento renomeado com sucesso"
        }
        
    except (IOError, OSError, ValueError, KeyError, TypeError) as e:
        logger.error(f"Erro ao renomear documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rename-all-smart/{process_id}", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def rename_all_documents_smart(
    process_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Renomeia TODOS os documentos de um processo usando nomes inteligentes IA.
    Apenas documentos já categorizados são renomeados.
    
    Returns:
    - total: Total de documentos
    - renamed: Número renomeados com sucesso
    - skipped: Número ignorados (não categorizados)
    - errors: Número de erros
    - details: Lista de operações
    """
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    
    # Buscar todos os metadados categorizados deste processo
    cursor = db.document_metadata.find(
        {"process_id": process_id, "is_categorized": True},
        {"_id": 0}
    )
    documents = await cursor.to_list(500)
    
    results = {
        "total": len(documents),
        "renamed": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }
    
    for doc in documents:
        s3_path = doc.get("s3_path")
        if not s3_path:
            results["skipped"] += 1
            continue
        
        old_filename = doc.get("filename", s3_path.rsplit('/', 1)[-1])
        
        # Extrair extensão
        if '.' in old_filename:
            original_ext = old_filename.rsplit('.', 1)[-1]
        else:
            original_ext = "pdf"
        
        # Gerar nome inteligente
        new_filename = generate_smart_filename(
            category=doc.get("ai_category", "Documento"),
            subcategory=doc.get("ai_subcategory", ""),
            client_name=client_name,
            expiry_date=doc.get("expiry_date"),
            original_extension=original_ext
        )
        
        # Calcular novo caminho
        if '/' in s3_path:
            folder_path = s3_path.rsplit('/', 1)[0]
            new_path = f"{folder_path}/{new_filename}"
        else:
            new_path = new_filename
        
        # Verificar se precisa renomear
        if new_path == s3_path:
            results["skipped"] += 1
            results["details"].append({
                "file": old_filename,
                "status": "skipped",
                "reason": "Nome já correcto"
            })
            continue
        
        try:
            # Renomear no S3
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda s=s3_path, n=new_path: s3_service.rename_file(s, n)
            )
            
            if success:
                # Actualizar metadados
                await db.document_metadata.update_one(
                    {"s3_path": s3_path},
                    {"$set": {
                        "s3_path": new_path,
                        "filename": new_filename,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                results["renamed"] += 1
                results["details"].append({
                    "file": old_filename,
                    "new_name": new_filename,
                    "status": "renamed"
                })
            else:
                results["errors"] += 1
                results["details"].append({
                    "file": old_filename,
                    "status": "error",
                    "reason": "Falha no S3"
                })
                
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            results["errors"] += 1
            results["details"].append({
                "file": old_filename,
                "status": "error",
                "reason": str(e)
            })
    
    return results



# ====================================================================
# VERIFICAÇÃO DE NIF DE EMPRESA
# ====================================================================

@router.get("/check-employer-nif/{nif}")
async def check_employer_nif(
    nif: str,
    user: dict = Depends(get_current_user)
):
    """
    Verifica se um NIF de empresa já existe na base de dados.
    
    Retorna:
    - exists: True se o NIF já foi usado
    - processes: Lista de processos onde este NIF foi usado
    - total_count: Número total de processos com este NIF
    
    Útil para utilizadores "indexacao" verificarem se a empresa
    do cliente já enviou documentos para outros balcões.
    """
    import re
    
    # Validar formato do NIF
    if not re.match(r'^\d{9}$', nif):
        raise HTTPException(
            status_code=400,
            detail="NIF inválido. Deve conter exatamente 9 dígitos."
        )
    
    # Buscar processos com este NIF de empregador
    # O NIF pode estar em personal_data.employer_nif ou personal_data.nif (se for empresa)
    processes = await db.processes.find(
        {
            "$or": [
                {"personal_data.employer_nif": nif},
                {"personal_data.nif": nif, "personal_data.nif": {"$regex": "^5"}},  # NIFs de empresa começam por 5
            ]
        },
        {"_id": 0, "id": 1, "client_name": 1, "status": 1, "created_at": 1, 
         "personal_data.employer_name": 1, "personal_data.employer_nif": 1,
         "consultor_name": 1, "mediador_name": 1}
    ).to_list(100)
    
    # Buscar nomes dos status
    workflow_statuses = await db.workflow_statuses.find({}, {"_id": 0, "name": 1, "label": 1, "color": 1}).to_list(100)
    status_map = {s["name"]: s for s in workflow_statuses}
    
    # Formatar resultados
    results = []
    for proc in processes:
        status_info = status_map.get(proc.get("status"), {})
        results.append({
            "id": proc.get("id"),
            "client_name": proc.get("client_name"),
            "employer_name": proc.get("personal_data", {}).get("employer_name"),
            "status": proc.get("status"),
            "status_label": status_info.get("label", proc.get("status")),
            "status_color": status_info.get("color", "#6B7280"),
            "consultor_name": proc.get("consultor_name"),
            "mediador_name": proc.get("mediador_name"),
            "created_at": proc.get("created_at")
        })
    
    return {
        "nif": nif,
        "exists": len(results) > 0,
        "total_count": len(results),
        "processes": results
    }


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
    import zipfile
    from fastapi.responses import StreamingResponse
    from botocore.exceptions import ClientError, BotoCoreError
    import asyncio
    
    document_ids = data.get("document_ids", [])
    process_id = data.get("process_id")
    
    if not document_ids or len(document_ids) == 0:
        raise HTTPException(status_code=400, detail="Lista de documentos vazia")
    
    if len(document_ids) > 50:
        raise HTTPException(status_code=400, detail="Máximo de 50 documentos por download")
    
    # Verificar permissões se process_id foi fornecido
    if process_id:
        process = await db.processes.find_one({"id": process_id})
        if not process:
            raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    if not s3_service.is_configured():
        raise HTTPException(status_code=500, detail=ERROR_S3_NOT_CONFIGURED)
    
    # Função para obter ficheiro do S3
    def get_s3_file_content(key):
        """Obtém o conteúdo de um ficheiro do S3."""
        try:
            response = s3_service.s3_client.get_object(
                Bucket=s3_service.bucket_name,
                Key=key
            )
            return response['Body'].read(), response.get('ContentType', 'application/octet-stream')
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchKey':
                logger.warning(f"[BULK-DOWNLOAD] Ficheiro não encontrado: {key}")
                return None, None
            raise
        except Exception as e:
            logger.error(f"[BULK-DOWNLOAD] Erro ao obter ficheiro {key}: {e}")
            return None, None
    
    # Criar ZIP em memória
    zip_buffer = BytesIO()
    files_added = []
    errors = []
    
    loop = asyncio.get_event_loop()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for doc_path in document_ids:
            try:
                # Tentar variações de path (underscore <-> espaço)
                path_variations = [doc_path]
                if '_' in doc_path:
                    path_variations.append(doc_path.replace('_', ' '))
                if ' ' in doc_path:
                    path_variations.append(doc_path.replace(' ', '_'))
                
                content = None
                used_path = None
                
                for try_path in path_variations:
                    result = await loop.run_in_executor(
                        None, 
                        lambda p=try_path: get_s3_file_content(p)
                    )
                    if result[0] is not None:
                        content, content_type = result
                        used_path = try_path
                        break
                
                if content is None:
                    errors.append({"path": doc_path, "error": "Ficheiro não encontrado"})
                    continue
                
                # Extrair nome do ficheiro do path
                filename = used_path.split('/')[-1] if '/' in used_path else used_path
                
                # Evitar nomes duplicados no ZIP
                if filename in [f[0] for f in files_added]:
                    base_name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
                    counter = 2
                    while f"{base_name}_{counter}.{ext}" in [f[0] for f in files_added]:
                        counter += 1
                    filename = f"{base_name}_{counter}.{ext}"
                
                # Adicionar ao ZIP
                zip_file.writestr(filename, content)
                files_added.append((filename, used_path))
                logger.info(f"[BULK-DOWNLOAD] Adicionado ao ZIP: {filename}")
                
            except Exception as e:
                logger.error(f"[BULK-DOWNLOAD] Erro ao processar {doc_path}: {e}")
                errors.append({"path": doc_path, "error": str(e)})
    
    if not files_added:
        raise HTTPException(status_code=404, detail="Nenhum documento encontrado para download")
    
    # Preparar resposta
    zip_buffer.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_filename = f"documentos_{timestamp}.zip"
    
    # Registar no histórico se process_id foi fornecido
    if process_id:
        try:
            await log_history(
                process_id=process_id,
                user=user,
                action="Download em massa",
                field="documentos",
                new_value=f"{len(files_added)} documentos"
            )
        except Exception as e:
            logger.warning(f"[BULK-DOWNLOAD] Erro ao registar histórico: {e}")
    
    logger.info(f"[BULK-DOWNLOAD] ZIP criado com {len(files_added)} ficheiros")
    
    # Criar generator para streaming
    def iter_zip():
        """Generator que produz o conteúdo do ficheiro ZIP em memória.

        Porquê um generator: permite ao StreamingResponse enviar o ficheiro
        em chunks sem carregar todo o ZIP na memória do request.

        Yields:
            bytes: Conteúdo completo do ficheiro ZIP.
        """
        yield zip_buffer.getvalue()
    
    from urllib.parse import quote
    encoded_filename = quote(zip_filename, safe='')
    
    headers = {
        'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}",
        'Content-Type': 'application/zip',
    }
    
    return StreamingResponse(
        iter_zip(),
        media_type='application/zip',
        headers=headers
    )


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
