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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request, Response

from database import db
from models.auth import UserRole
from models.document import DocumentExpiryCreate, DocumentExpiryResponse
from services.auth import get_current_user, require_roles
from middleware.rate_limit import limiter

# Importar o novo serviço S3
from services.s3_storage import s3_service, sanitize_folder_name

# Importar serviço de processamento de documentos (conversão imagem → PDF)
from services.document_processor import convert_image_to_pdf, IMG2PDF_AVAILABLE

# Importar serviço de validação de ficheiros (MIME type validation)
from services.file_validation import validate_file_content, validate_and_extract_file
from services.history import log_history

router = APIRouter(prefix="/documents", tags=["Document Management"])
logger = logging.getLogger(__name__)


# ====================================================================
# CONSTANTES PARA MENSAGENS DE ERRO (SonarQube - DRY)
# ====================================================================
ERROR_CLIENT_NOT_FOUND = "Cliente não encontrado"
ERROR_PROCESS_NOT_FOUND = "Processo não encontrado"
ERROR_S3_NOT_CONFIGURED = "S3 não configurado"
ERROR_FILE_ACCESS_DENIED = "Acesso não autorizado a este ficheiro"
ERROR_S3_UPLOAD_FAILED = "Erro ao enviar ficheiro para o armazenamento S3"
ERROR_DOWNLOAD_URL = "Erro ao gerar link de download"
ERROR_PRESIGNED_URL = "Erro ao gerar URL"
ERROR_DELETE_FILE = "Erro ao eliminar ficheiro"
ERROR_RECORD_NOT_FOUND = "Registo não encontrado"
ERROR_S3_FILE_NOT_FOUND = "Ficheiro não encontrado no S3"
ERROR_S3_ACCESS = "Erro ao aceder ao ficheiro"
ERROR_CATEGORIZE_DOC = "Erro ao categorizar documento"
ERROR_NO_VALID_FILES = "Nenhum ficheiro válido enviado"
ERROR_NO_SUGGESTIONS = "Nenhuma sugestão enviada"
ERROR_NO_ORGANIZATION = "Nenhuma organização especificada"
ERROR_S3_PATH_REQUIRED = "s3_path é obrigatório"
ERROR_DOC_NOT_CATEGORIZED = "Documento não foi categorizado pela IA. Execute a categorização primeiro."
ERROR_NEW_NAME_REQUIRED = "novo_nome é obrigatório quando apply_ai_name=False"
ERROR_RENAME_FAILED = "Falha ao renomear ficheiro no S3"

# ====================================================================
# CONSTANTES PARA VALORES DEFAULT (SonarQube - DRY)
# ====================================================================
DEFAULT_CLIENT_NAME = "Cliente"
DEFAULT_CONSULTOR_NAME = "N/D"
DEFAULT_FILE_PREFIX = "Ficheiro: "
MIME_TYPE_PDF = "application/pdf"

# ====================================================================
# CONSTANTES PARA RESPOSTAS HTTP (SonarQube - Documentation)
# ====================================================================
HTTP_400_RESPONSE = {"description": "Bad Request - Parâmetros inválidos"}
HTTP_403_RESPONSE = {"description": "Forbidden - Acesso não autorizado"}
HTTP_404_RESPONSE = {"description": "Not Found - Recurso não encontrado"}
HTTP_500_RESPONSE = {"description": "Internal Server Error - Erro interno do servidor"}


# ====================================================================
# FUNÇÃO DE SANITIZAÇÃO PARA LOGS (Segurança)
# ====================================================================
def sanitize_for_log(value: str, max_length: int = 50) -> str:
    """
    Sanitiza dados controlados pelo utilizador antes de logar.
    Remove carateres potencialmente perigosos e limita o tamanho.
    """
    if not value:
        return "[empty]"
    sanitized = str(value)[:max_length].replace('\n', ' ').replace('\r', '')
    return sanitized if sanitized else "[sanitized]"


# ====================================================================
# FUNÇÃO DE CATEGORIZAÇÃO AUTOMÁTICA EM BACKGROUND
# ====================================================================

async def auto_categorize_document_background(
    process_id: str,
    client_name: str,
    s3_path: str,
    filename: str,
    file_content: bytes
):
    """
    Categoriza um documento automaticamente em background após upload.
    Esta função é chamada de forma assíncrona para não bloquear o upload.
    """
    from services.document_categorization import extract_text_from_pdf, categorize_document_with_ai
    
    try:
        logger.info(f"[AUTO-CAT] Iniciando categorização automática")
        
        # Verificar se já existe metadados para este ficheiro
        existing = await db.document_metadata.find_one({"s3_path": s3_path}, {"_id": 0})
        
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
            logger.warning(f"[AUTO-CAT] Falha ao categorizar documento")
            return
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Criar ou actualizar metadados - CORRIGIDO: verificar se existing é None
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
            "extracted_text": extracted_text[:5000] if extracted_text else None,
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
            logger.info(f"[AUTO-CAT] Metadados actualizados")
        else:
            metadata["created_at"] = now
            await db.document_metadata.insert_one(metadata)
            logger.info(f"[AUTO-CAT] Metadados criados")
        
        logger.info(f"[AUTO-CAT] Categorização concluída")
        
    except Exception as e:
        # Capturar TODOS os erros para não crashar a tarefa de background
        logger.error(f"[AUTO-CAT] Erro ao categorizar documento: {type(e).__name__}: {e}")


# ====================================================================
# FUNÇÕES DE NORMALIZAÇÃO DE NOMES DE FICHEIROS
# ====================================================================

def normalize_filename(filename: str, category: str = None) -> str:
    """
    Sanitiza o nome do ficheiro para armazenamento seguro no S3.
    
    NOTA: NÃO altera o nome original - apenas remove caracteres perigosos.
    Mantém o nome original do ficheiro para não confundir o utilizador.
    
    Args:
        filename: Nome original do ficheiro
        category: Categoria do documento (IGNORADO - mantido para compatibilidade)
        
    Returns:
        Nome sanitizado (mantém o original, apenas remove caracteres perigosos)
    """
    if not filename:
        return f"documento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    # Separar nome e extensão
    if '.' in filename:
        name_part, ext = filename.rsplit('.', 1)
        ext = ext.lower()
    else:
        name_part = filename
        ext = 'pdf'
    
    # Sanitizar APENAS caracteres realmente perigosos para S3
    # Manter acentos, espaços e caracteres portugueses
    # Remover apenas: / \ : * ? " < > | (caracteres inválidos em paths)
    name_sanitized = re.sub(r'[/\\:*?"<>|]', '', name_part)
    
    # Remover caracteres de controlo
    name_sanitized = re.sub(r'[\x00-\x1f\x7f]', '', name_sanitized)
    
    # Limitar tamanho mas manter nome reconhecível
    if len(name_sanitized) > 200:
        name_sanitized = name_sanitized[:200]
    
    # Se ficou vazio, usar fallback
    if not name_sanitized.strip():
        name_sanitized = f"documento_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    return f"{name_sanitized}.{ext}"


def is_image_file(filename: str, content_type: str = None) -> bool:
    """Verifica se o ficheiro é uma imagem suportada para conversão."""
    image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif'}
    image_mimes = {'image/jpeg', 'image/png', 'image/tiff'}
    
    if filename:
        ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext in image_extensions:
            return True
    
    if content_type and content_type.lower() in image_mimes:
        return True
    
    return False

# ====================================================================
# PARTE 1: GESTÃO DE FICHEIROS (S3 STORAGE) - NOVO
# ====================================================================

@router.get("/client/{client_id}/files", responses={404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def list_client_files(
    client_id: str, 
    user: dict = Depends(get_current_user)
):
    """Lista todos os ficheiros do cliente no S3 organizados por pastas."""
    process = await db.processes.find_one({"id": client_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_CLIENT_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    # Obter segundo titular se existir (com verificação de None)
    titular2 = process.get("titular2_data") or {}
    second_client_name = process.get("second_client_name") or titular2.get("nome") or titular2.get("name")
    
    # Obter mapeamento S3 configurado (prioridade máxima)
    s3_folder = process.get("s3_folder")
    
    # Executar operação síncrona do S3 em thread separada para não bloquear o event loop
    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(
        None,  # Usar executor default (ThreadPool)
        lambda: s3_service.list_files(client_id, client_name, second_client_name, s3_folder)
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
    user: dict = Depends(get_current_user)
):
    """
    Faz upload de um ficheiro físico para o S3.
    
    Funcionalidades automáticas:
    - Normalização do nome do ficheiro
    - Conversão de imagens (JPG, PNG) para PDF
    - Categorização automática com IA (em background)
    
    Nota para utilizadores "indexacao":
    - O campo empresa_nif é OBRIGATÓRIO
    - Deve conter o NIF da empresa onde o cliente trabalha
    """
    try:
        # Verificar se S3 está configurado
        if not s3_service.is_configured():
            raise HTTPException(
                status_code=503, 
                detail="Serviço de armazenamento S3 não configurado. Contacte o administrador para configurar as credenciais AWS."
            )
        
        # Verificar se utilizador "indexacao" forneceu o NIF da empresa
        if user.get("role") == "indexacao":
            if not empresa_nif:
                raise HTTPException(
                    status_code=400, 
                    detail="O NIF da empresa é obrigatório para utilizadores de indexação. Por favor, insira o NIF da entidade empregadora do cliente."
                )
            # Validar formato do NIF (9 dígitos)
            import re
            if not re.match(r'^\d{9}$', empresa_nif):
                raise HTTPException(
                    status_code=400,
                    detail="NIF da empresa inválido. Deve conter exatamente 9 dígitos."
                )
        
        process = await db.processes.find_one({"id": client_id})
        if not process:
            raise HTTPException(status_code=404, detail=ERROR_CLIENT_NOT_FOUND)
        
        # Se empresa_nif foi fornecido, guardar no processo
        if empresa_nif:
            personal_data = process.get("personal_data", {})
            personal_data["employer_nif"] = empresa_nif
            await db.processes.update_one(
                {"id": client_id},
                {"$set": {"personal_data": personal_data}}
            )
        
        client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
        # Obter segundo titular se existir (com verificação de None)
        titular2_upload = process.get("titular2_data") or {}
        second_client_name = process.get("second_client_name") or titular2_upload.get("nome") or titular2_upload.get("name")
        
        # Obter mapeamento S3 configurado (prioridade máxima)
        s3_folder = process.get("s3_folder")
        
        # Ler o conteúdo do ficheiro
        file_content = await file.read()
        original_filename = file.filename or f"documento_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        content_type = file.content_type or "application/octet-stream"
        
        # ====================================================================
        # Inicializar todas as variáveis de controlo
        # ====================================================================
        was_extracted = False
        was_converted = False
        converted_to_pdf = False
        conversion_info = {}
        
        # ====================================================================
        # SEGURANÇA: Validar MIME type usando magic bytes (não apenas extensão)
        # Isto previne uploads de executáveis disfarçados como documentos
        # TAMBÉM: Tenta extrair conteúdo de wrappers (Java serialization, base64)
        # E: Converte automaticamente ficheiros para PDF quando possível
        # ====================================================================
        from services.file_validation import validate_and_convert_file
        
        try:
            # Usar validate_and_convert_file para validação, extração e conversão
            validated_content, detected_mime, mime_description, conversion_info = validate_and_convert_file(
                file_content, original_filename, auto_convert=True
            )
            
            # Processar informações de conversão
            was_extracted = conversion_info.get("was_extracted", False)
            was_converted = conversion_info.get("was_converted", False)
            
            if was_extracted or was_converted:
                logger.info(
                    f"[UPLOAD] Ficheiro processado: {sanitize_for_log(original_filename)} "
                    f"(extraído: {was_extracted}, convertido: {was_converted}, "
                    f"método: {conversion_info.get('conversion_method') or conversion_info.get('extraction_method')})"
                )
                file_content = validated_content
                content_type = detected_mime
                
                # Atualizar nome do ficheiro se foi convertido para PDF
                if detected_mime == MIME_TYPE_PDF and not original_filename.lower().endswith('.pdf'):
                    original_filename = original_filename.rsplit('.', 1)[0] + '.pdf' if '.' in original_filename else original_filename + '.pdf'
                    
        except HTTPException as e:
            logger.warning(f"[UPLOAD] Ficheiro rejeitado: {sanitize_for_log(original_filename)} - {e.detail}")
            raise
        except Exception as e:
            # Se houver erro na validação, continuar com o ficheiro original
            logger.warning(f"[UPLOAD] Erro na validação/conversão, usando ficheiro original: {e}")
            # conversion_info já está inicializado como {} acima
        
        # Verificar se é uma imagem e converter para PDF (fallback para imagens puras)
        # Nota: was_converted já pode ter sido definido acima se a conversão automática funcionou
        converted_to_pdf = was_converted  # Inicializar com valor de conversão automática
        if not was_converted and is_image_file(original_filename, content_type) and IMG2PDF_AVAILABLE:
            try:
                logger.info(f"[UPLOAD] A converter imagem para PDF: {sanitize_for_log(original_filename)}")
                pdf_bytes, new_filename = await convert_image_to_pdf(file_content, original_filename)
                
                if new_filename != original_filename:
                    file_content = pdf_bytes
                    original_filename = new_filename
                    content_type = MIME_TYPE_PDF
                    converted_to_pdf = True
                    logger.info(f"[UPLOAD] Conversão concluída: {sanitize_for_log(new_filename)}")
            except (IOError, OSError, ValueError, KeyError, TypeError) as e:
                logger.warning(f"[UPLOAD] Não foi possível converter imagem para PDF: {e}")
                # Continua com o ficheiro original
        
        # Verificar se é HEIC/HEIF (formato iPhone) - não suportado para conversão
        ext_lower = original_filename.lower().rsplit('.', 1)[-1] if '.' in original_filename else ''
        if ext_lower in ['heic', 'heif'] and not converted_to_pdf:
            logger.info(f"[UPLOAD] Ficheiro HEIC/HEIF aceite: {sanitize_for_log(original_filename)}")
            # HEIC/HEIF são aceites mas não convertidos automaticamente
            # O utilizador deve converter para JPEG antes do upload idealmente
        
        # Normalizar nome do ficheiro
        normalized_filename = normalize_filename(original_filename, category)
        logger.info(f"Nome normalizado")
        
        # Criar BytesIO para o upload
        file_buffer = BytesIO(file_content)
        
        # Upload para o S3
        s3_path = s3_service.upload_file(
            file_buffer,
            client_id,
            client_name,
            category,
            normalized_filename,
            content_type,
            second_client_name=second_client_name,
            s3_folder=s3_folder
        )
        
        if not s3_path:
            raise HTTPException(status_code=500, detail=ERROR_S3_UPLOAD_FAILED)
        
        # Gerar link temporário para acesso imediato (não falha se houver erro)
        try:
            temporary_url = s3_service.get_presigned_url(s3_path) or ""
        except Exception as e:
            logger.warning(f"[UPLOAD] Erro ao gerar URL temporário: {e}")
            temporary_url = ""
        
        # Agendar categorização automática em background (não bloqueia o response)
        try:
            background_tasks.add_task(
                auto_categorize_document_background,
                process_id=client_id,
                client_name=client_name,
                s3_path=s3_path,
                filename=normalized_filename,
                file_content=file_content
            )
        except Exception as e:
            logger.warning(f"[UPLOAD] Erro ao agendar categorização: {e}")
        
        # Registar no histórico (não falha o upload se houver erro)
        try:
            await log_history(
                process_id=client_id,
                user=user,
                action="Carregou documento",
                field="documento",
                new_value=f"{normalized_filename} ({category})"
            )
        except Exception as e:
            logger.warning(f"[UPLOAD] Erro ao registar histórico: {e}")
        
        return {
            "success": True, 
            "path": s3_path, 
            "message": "Ficheiro guardado com sucesso",
            "original_filename": file.filename,
            "normalized_filename": normalized_filename,
            "converted_to_pdf": converted_to_pdf,
            "was_extracted": was_extracted,
            "was_converted": was_converted,
            "conversion_method": conversion_info.get("conversion_method"),
            "auto_categorization": "iniciada",  # Indica que categorização foi agendada
            "temporary_url": temporary_url  # URL para acesso imediato (válido 1 hora)
        }
    
    except HTTPException:
        # Re-raise HTTPExceptions para manter o status code correto
        raise
    except Exception as e:
        # Log do erro completo para debugging
        logger.error(f"[UPLOAD] Erro inesperado: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Erro interno ao processar upload. Por favor tente novamente ou contacte o suporte se o problema persistir."
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
    process = await db.processes.find_one({"id": client_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_CLIENT_NOT_FOUND)
    
    # Verificar se já existe mapeamento S3 - NÃO criar duplicados
    existing_s3_folder = process.get("s3_folder")
    if existing_s3_folder:
        # Verificar se a pasta ainda existe no S3
        if s3_service._folder_exists(existing_s3_folder):
            logger.info(f"Pasta S3 já existe para cliente {client_id}: {existing_s3_folder}")
            return {"success": True, "s3_folder": existing_s3_folder, "already_exists": True}
        # Se não existe, continuar para criar nova
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    # Obter segundo titular se existir (com verificação de None)
    titular2_init = process.get("titular2_data") or {}
    second_client_name = process.get("second_client_name") or titular2_init.get("nome") or titular2_init.get("name")
    
    success, s3_folder_path = s3_service.initialize_client_folders(
        client_id, 
        client_name,
        second_client_name=second_client_name
    )
    
    # Se criou as pastas, guardar mapeamento no processo
    if success and s3_folder_path:
        await db.processes.update_one(
            {"id": client_id},
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
    process = await db.processes.find_one({"id": client_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_CLIENT_NOT_FOUND)
    
    # Verificar se o ficheiro pertence ao cliente (segurança)
    client_name = process.get("client_name", "")
    safe_name = sanitize_folder_name(client_name) if client_name else ""
    clean_name = client_name.strip() if client_name else ""
    
    valid_prefixes = [
        f"Documentação Clientes/{clean_name}",  # Com espaços
        f"Documentação Clientes/{safe_name}",   # Com underscores
    ]
    
    if not any(file_path.startswith(prefix) for prefix in valid_prefixes):
        raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)
    
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
    Gera URL temporário para download/preview de ficheiro por path S3.
    Tenta variações de path (underscore <-> espaço) se o original falhar.
    
    Args:
        file_path: Path completo do ficheiro no S3 (URL encoded)
        
    Returns:
        URL presigned para acesso temporário
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
    """Elimina um ficheiro do S3."""
    process = await db.processes.find_one({"id": client_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_CLIENT_NOT_FOUND)
    
    # Verificar se o ficheiro pertence ao cliente (segurança)
    client_name = process.get("client_name", "")
    safe_name = sanitize_folder_name(client_name) if client_name else ""
    clean_name = client_name.strip() if client_name else ""
    
    valid_prefixes = [
        f"Documentação Clientes/{clean_name}",  # Com espaços
        f"Documentação Clientes/{safe_name}",   # Com underscores
    ]
    
    if not any(file_path.startswith(prefix) for prefix in valid_prefixes):
        raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)
    
    # Guardar nome do ficheiro antes de eliminar
    filename = file_path.split('/')[-1] if '/' in file_path else file_path
    
    success = s3_service.delete_file(file_path)
    if not success:
        raise HTTPException(status_code=500, detail=ERROR_DELETE_FILE)
    
    # Registar no histórico
    await log_history(
        process_id=client_id,
        user=user,
        action="Eliminou documento",
        field="documento",
        old_value=filename
    )
    
    return {"success": True, "message": "Ficheiro eliminado"}


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
    process_id = data.get("process_id")
    source_path = data.get("source_path")
    target_category = data.get("target_category")
    target_filename = data.get("target_filename")
    
    if not process_id or not source_path:
        raise HTTPException(status_code=400, detail="process_id e source_path são obrigatórios")
    
    # Buscar processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = process.get("second_client_name") or process.get("titular2", {}).get("nome")
    s3_folder = process.get("s3_folder")
    
    # Determinar o caminho base
    if s3_folder:
        base_path = s3_folder.rstrip('/')
    else:
        base_path = s3_service._get_client_base_path_for_upload(
            process_id, 
            client_name, 
            second_client_name
        )
    
    # Extrair nome e categoria atuais
    current_filename = source_path.split('/')[-1] if '/' in source_path else source_path
    current_category_part = source_path.split('/')[-2] if '/' in source_path else ""
    
    # Determinar categoria destino
    if target_category:
        safe_category = sanitize_folder_name(target_category)
    elif current_category_part:
        safe_category = current_category_part
    else:
        safe_category = "Outros"
    
    # Determinar nome do ficheiro destino
    final_filename = target_filename if target_filename else current_filename
    
    # Construir caminho destino
    target_path = f"{base_path}/{safe_category}/{final_filename}"
    
    # Verificar se é o mesmo caminho (sem conflito)
    if target_path == source_path:
        return {
            "has_conflict": False,
            "target_path": target_path,
            "message": "O ficheiro já está no destino pretendido"
        }
    
    # Verificar se existe ficheiro no destino
    conflict_exists = s3_service.file_exists(target_path)
    
    # Gerar nomes alternativos se houver conflito
    suggested_names = []
    if conflict_exists:
        name_part, ext = final_filename.rsplit('.', 1) if '.' in final_filename else (final_filename, 'pdf')
        
        # Gerar 3 nomes alternativos
        for i in range(1, 4):
            new_name = f"{name_part}_{i+1}.{ext}"
            new_path = f"{base_path}/{safe_category}/{new_name}"
            if not s3_service.file_exists(new_path):
                suggested_names.append({
                    "filename": new_name,
                    "path": new_path
                })
        
        return {
            "has_conflict": True,
            "source_path": source_path,
            "conflict_path": target_path,
            "conflict_filename": final_filename,
            "suggested_names": suggested_names,
            "message": f"Já existe um ficheiro chamado '{final_filename}' no destino"
        }
    
    return {
        "has_conflict": False,
        "target_path": target_path,
        "message": "Nenhum conflito detectado"
    }


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
    source_path = data.get("source_path")
    target_category = data.get("target_category")
    target_filename = data.get("target_filename")
    overwrite = data.get("overwrite", False)
    auto_rename = data.get("auto_rename", False)
    
    if not source_path or not target_category:
        raise HTTPException(status_code=400, detail="source_path e target_category são obrigatórios")
    
    # Buscar processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = process.get("second_client_name") or process.get("titular2", {}).get("nome")
    s3_folder = process.get("s3_folder")  # Pasta S3 configurada manualmente
    
    # Extrair nome do ficheiro
    current_filename = source_path.split('/')[-1] if '/' in source_path else source_path
    final_filename = target_filename if target_filename else current_filename
    
    # Determinar o caminho base CORRETO para o cliente
    # Prioridade: s3_folder configurado > encontrar pasta existente > criar nova
    if s3_folder:
        base_path = s3_folder.rstrip('/')
    else:
        # Usar a função do S3 que respeita pastas existentes
        base_path = s3_service._get_client_base_path_for_upload(
            process_id, 
            client_name, 
            second_client_name
        )
    
    # Construir novo caminho
    safe_category = sanitize_folder_name(target_category)
    new_path = f"{base_path}/{safe_category}/{final_filename}"
    
    # Verificar se o caminho mudou
    if new_path == source_path:
        return {
            "success": True,
            "message": "Ficheiro já está na categoria correta",
            "new_path": new_path,
            "was_renamed": False
        }
    
    # Verificar se existe conflito
    conflict_exists = s3_service.file_exists(new_path)
    was_renamed = False
    
    if conflict_exists and not overwrite:
        if auto_rename:
            # Gerar nome automático
            name_part, ext = final_filename.rsplit('.', 1) if '.' in final_filename else (final_filename, 'pdf')
            counter = 2
            while s3_service.file_exists(f"{base_path}/{safe_category}/{name_part}_{counter}.{ext}"):
                counter += 1
                if counter > 100:  # Limite de segurança
                    raise HTTPException(status_code=409, detail="Não foi possível gerar um nome único para o ficheiro")
            
            final_filename = f"{name_part}_{counter}.{ext}"
            new_path = f"{base_path}/{safe_category}/{final_filename}"
            was_renamed = True
            logger.info(f"Ficheiro renomeado automaticamente para evitar conflito: {final_filename}")
        else:
            # Retornar erro com informações do conflito
            # Gerar sugestões de nomes alternativos
            suggested_names = []
            name_part, ext = final_filename.rsplit('.', 1) if '.' in final_filename else (final_filename, 'pdf')
            for i in range(1, 4):
                new_name = f"{name_part}_{i+1}.{ext}"
                suggested_path = f"{base_path}/{safe_category}/{new_name}"
                if not s3_service.file_exists(suggested_path):
                    suggested_names.append(new_name)
            
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "FILE_EXISTS",
                    "message": f"Já existe um ficheiro chamado '{final_filename}' no destino",
                    "conflict_path": new_path,
                    "suggested_names": suggested_names
                }
            )
    
    # Mover ficheiro no S3
    success = s3_service.rename_file(source_path, new_path)
    
    if success:
        # Atualizar metadados se existirem
        await db.document_metadata.update_one(
            {"s3_path": source_path},
            {"$set": {
                "s3_path": new_path,
                "ai_category": target_category,
                "filename": final_filename,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Registar no histórico
        action_msg = f"Moveu documento para {target_category}"
        if was_renamed:
            action_msg += f" (renomeado para {final_filename})"
        
        await log_history(
            process_id=process_id,
            user=user,
            action=action_msg,
            field="documento",
            old_value=current_filename,
            new_value=final_filename
        )
        
        logger.info(f"Ficheiro movido: {source_path} -> {new_path}")
        
        return {
            "success": True,
            "message": f"Ficheiro movido para {target_category}",
            "new_path": new_path,
            "old_path": source_path,
            "new_filename": final_filename,
            "was_renamed": was_renamed
        }
    else:
        raise HTTPException(status_code=500, detail="Erro ao mover ficheiro")


# ====================================================================
# PARTE 2: GESTÃO DE VALIDADES (EXISTENTE)
# ====================================================================
EXPIRY_WARNING_DAYS = 60 

@router.post("/expiry", response_model=DocumentExpiryResponse, responses={404: HTTP_404_RESPONSE})
async def create_document_expiry(
    data: DocumentExpiryCreate,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.MEDIADOR, UserRole.GESTOR_DOCUMENTOS]))
):
    """Registar validade de um documento."""
    process = await db.processes.find_one({"id": data.process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    doc = {
        "id": doc_id,
        "process_id": data.process_id,
        "document_type": data.document_type,
        "document_name": data.document_name,
        "expiry_date": data.expiry_date,
        "notes": data.notes,
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
    elif user["role"] == UserRole.MEDIADOR:
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
async def delete_document_expiry(doc_id: str, user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CONSULTOR, UserRole.GESTOR_DOCUMENTOS]))):
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
    """
    Dashboard de documentos a expirar.
    
    Permissões:
    - CEO/Diretor/Admin: Vêem todos os clientes
    - Consultor/Intermediário: Vêem apenas os seus clientes
    
    Args:
        days_ahead: Dias a verificar (default 60)
        urgency: Filtro por urgência (critical=<7, high=7-29, medium=30-60)
        consultor_id: Filtro por consultor (apenas para management)
        search: Pesquisa por nome de cliente
    
    Returns:
        Dashboard com estatísticas e lista de documentos agrupados por cliente
    """
    from datetime import timezone
    
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    
    # Verificar se é management (pode ver tudo)
    is_management = user_role in UserRole.MANAGEMENT_ROLES
    
    today = datetime.now(timezone.utc)
    future_date = today + timedelta(days=days_ahead)
    
    # Query base para documentos com data de expiração
    doc_query = {
        "expiry_date": {
            "$ne": None,
            "$gte": today.strftime("%Y-%m-%d"),
            "$lte": future_date.strftime("%Y-%m-%d")
        }
    }
    
    # Aplicar filtro de urgência
    if urgency:
        if urgency == "critical":
            critical_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
            doc_query["expiry_date"]["$lt"] = critical_date
        elif urgency == "high":
            high_start = (today + timedelta(days=7)).strftime("%Y-%m-%d")
            high_end = (today + timedelta(days=30)).strftime("%Y-%m-%d")
            doc_query["expiry_date"]["$gte"] = high_start
            doc_query["expiry_date"]["$lt"] = high_end
        elif urgency == "medium":
            medium_start = (today + timedelta(days=30)).strftime("%Y-%m-%d")
            doc_query["expiry_date"]["$gte"] = medium_start
    
    # Buscar todos os documentos a expirar
    expiring_docs = await db.document_metadata.find(
        doc_query,
        {"_id": 0, "extracted_text": 0}
    ).to_list(1000)
    
    # Obter process_ids únicos
    process_ids = list(set(doc.get("process_id") for doc in expiring_docs if doc.get("process_id")))
    
    # Buscar processos para obter informações dos clientes e consultores
    processes_query = {"id": {"$in": process_ids}}
    
    # Se não é management, filtrar apenas processos do utilizador
    if not is_management:
        processes_query["$or"] = [
            {"assigned_consultor_id": user_id},
            {"consultor_id": user_id},
            {"assigned_mediador_id": user_id},
            {"mediador_id": user_id}
        ]
    
    # Filtro por consultor específico (apenas para management)
    if is_management and consultor_id:
        processes_query["$or"] = [
            {"assigned_consultor_id": consultor_id},
            {"consultor_id": consultor_id},
            {"assigned_mediador_id": consultor_id},
            {"mediador_id": consultor_id}
        ]
    
    processes = await db.processes.find(
        processes_query,
        {"_id": 0, "id": 1, "client_name": 1, "assigned_consultor_id": 1, 
         "consultor_id": 1, "assigned_mediador_id": 1, "mediador_id": 1}
    ).to_list(500)
    
    # Criar mapa de processos
    process_map = {p["id"]: p for p in processes}
    
    # Filtrar documentos apenas dos processos autorizados
    authorized_process_ids = set(process_map.keys())
    filtered_docs = [d for d in expiring_docs if d.get("process_id") in authorized_process_ids]
    
    # Aplicar filtro de pesquisa
    if search:
        search_lower = search.lower()
        search_process_ids = [
            pid for pid, p in process_map.items() 
            if search_lower in (p.get("client_name") or "").lower()
        ]
        filtered_docs = [d for d in filtered_docs if d.get("process_id") in search_process_ids]
    
    # Obter nomes dos consultores
    consultor_ids = set()
    for p in processes:
        if p.get("assigned_consultor_id"):
            consultor_ids.add(p["assigned_consultor_id"])
        if p.get("consultor_id"):
            consultor_ids.add(p["consultor_id"])
        if p.get("assigned_mediador_id"):
            consultor_ids.add(p["assigned_mediador_id"])
        if p.get("mediador_id"):
            consultor_ids.add(p["mediador_id"])
    
    consultors = await db.users.find(
        {"id": {"$in": list(consultor_ids)}},
        {"_id": 0, "id": 1, "name": 1}
    ).to_list(100)
    consultor_map = {c["id"]: c.get("name", DEFAULT_CONSULTOR_NAME) for c in consultors}
    
    # Calcular estatísticas
    stats = {"critical": 0, "high": 0, "medium": 0, "total": len(filtered_docs)}
    
    for doc in filtered_docs:
        try:
            expiry = datetime.strptime(doc["expiry_date"], "%Y-%m-%d")
            days_until = (expiry - today).days
            if days_until < 7:
                stats["critical"] += 1
            elif days_until < 30:
                stats["high"] += 1
            else:
                stats["medium"] += 1
        except (ValueError, KeyError):
            pass
    
    # Agrupar documentos por cliente
    clients_data = {}
    
    for doc in filtered_docs:
        process_id = doc.get("process_id")
        if not process_id or process_id not in process_map:
            continue
        
        process = process_map[process_id]
        client_name = doc.get("client_name") or process.get("client_name", DEFAULT_CLIENT_NAME)
        
        if process_id not in clients_data:
            # Identificar consultor responsável
            consultor_id = process.get("assigned_consultor_id") or process.get("consultor_id") or \
                          process.get("assigned_mediador_id") or process.get("mediador_id")
            consultor_name = consultor_map.get(consultor_id, DEFAULT_CONSULTOR_NAME)
            
            clients_data[process_id] = {
                "process_id": process_id,
                "client_name": client_name,
                "consultor_id": consultor_id,
                "consultor_name": consultor_name,
                "documents": [],
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0
            }
        
        # Calcular urgência do documento
        try:
            expiry = datetime.strptime(doc["expiry_date"], "%Y-%m-%d")
            days_until = (expiry - today).days
            
            if days_until < 7:
                urgency_level = "critical"
                clients_data[process_id]["critical_count"] += 1
            elif days_until < 30:
                urgency_level = "high"
                clients_data[process_id]["high_count"] += 1
            else:
                urgency_level = "medium"
                clients_data[process_id]["medium_count"] += 1
        except (ValueError, KeyError):
            urgency_level = "unknown"
            days_until = None
        
        clients_data[process_id]["documents"].append({
            "id": doc.get("id"),
            "filename": doc.get("filename"),
            "category": doc.get("ai_category"),
            "subcategory": doc.get("ai_subcategory"),
            "expiry_date": doc.get("expiry_date"),
            "days_until": days_until,
            "urgency": urgency_level,
            "s3_path": doc.get("s3_path")
        })
    
    # Converter para lista e ordenar por urgência (mais críticos primeiro)
    clients_list = list(clients_data.values())
    clients_list.sort(key=lambda x: (-x["critical_count"], -x["high_count"], -x["medium_count"]))
    
    # Obter lista de consultores para filtro (apenas para management)
    consultors_filter = []
    if is_management:
        all_consultors = await db.users.find(
            {"role": {"$in": ["consultor", "intermediario", "mediador"]}},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(100)
        consultors_filter = [{"id": c["id"], "name": c.get("name", DEFAULT_CONSULTOR_NAME)} for c in all_consultors]
    
    return {
        "stats": stats,
        "clients": clients_list,
        "total_clients": len(clients_list),
        "is_management": is_management,
        "consultors_filter": consultors_filter,
        "filters_applied": {
            "days_ahead": days_ahead,
            "urgency": urgency,
            "consultor_id": consultor_id,
            "search": search
        }
    }



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
    import time
    
    start_time = time.time()
    
    try:
        from services.ai_document_analyzer import analyze_multiple_documents
    except ImportError as e:
        logger.error(f"Erro ao importar ai_document_analyzer: {e}")
        raise HTTPException(status_code=500, detail=f"Serviço de análise não disponível: {str(e)}")
    
    try:
        from routes.ai_import_logs import create_ai_import_log, finalize_ai_import_log
    except ImportError as e:
        logger.warning(f"ai_import_logs não disponível: {e}")
        create_ai_import_log = None
        finalize_ai_import_log = None
    
    # Buscar dados do processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    
    # Criar log de importação (se disponível)
    log_id = None
    if create_ai_import_log:
        try:
            log_id = await create_ai_import_log(
                process_id=process_id,
                client_name=client_name,
                created_by=user.get("id"),
                created_by_name=user.get("name")
            )
        except Exception as e:
            logger.warning(f"Erro ao criar log de importação: {e}")
    
    # Preparar documentos para análise
    documents = []
    for file in files:
        try:
            content = await file.read()
            if len(content) == 0:
                continue
                
            documents.append({
                "content": content,
                "name": file.filename,
                "mime_type": file.content_type or "application/octet-stream"
            })
        except Exception as e:
            logger.warning(f"Erro ao ler ficheiro {file.filename}: {e}")
            continue
    
    if not documents:
        # Actualizar log com erro
        if log_id and finalize_ai_import_log:
            try:
                await finalize_ai_import_log(log_id, duration_ms=0)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=ERROR_NO_VALID_FILES)
    
    # Extrair dados existentes do cliente para comparação
    existing_data = {
        "client_name": process.get("client_name"),
        "nif": process.get("client_nif") or process.get("nif"),
        "birth_date": process.get("data_nascimento"),
        "cc_number": process.get("cc_number"),
        "cc_validity": process.get("cc_validity") or process.get("validade_cc"),
        "nationality": process.get("nacionalidade") or process.get("nationality"),
        "gender": process.get("sexo") or process.get("gender"),
        "address": process.get("morada") or process.get("address"),
        "fiscal_address": process.get("morada_fiscal") or process.get("fiscal_address"),
        "phone": process.get("phone") or process.get("telefone"),
        "email": process.get("email") or process.get("client_email"),
    }
    
    # Analisar documentos
    try:
        results = await analyze_multiple_documents(documents, existing_data, log_id=log_id)
    except Exception as e:
        logger.error(f"Erro na análise de documentos: {e}", exc_info=True)
        
        # Finalizar log com erro
        total_duration = int((time.time() - start_time) * 1000)
        if log_id and finalize_ai_import_log:
            try:
                await finalize_ai_import_log(log_id, duration_ms=total_duration)
            except Exception:
                pass
        
        raise HTTPException(status_code=500, detail=f"Erro na análise: {str(e)}")
    
    # Extrair dados e identificar conflitos
    extracted_data = {}
    conflicts = []
    document_types = []
    
    # Processar resultados da análise
    if results and isinstance(results, dict):
        analysis_data = results.get("merged_data", {})
        field_sources = results.get("field_sources", {})
        
        # Mapear campos extraídos
        for field, value in analysis_data.items():
            if value and str(value).strip():
                extracted_data[field] = value
                
                # Verificar se há conflito com dados existentes
                existing_value = existing_data.get(field)
                if existing_value and str(existing_value).strip() and str(existing_value) != str(value):
                    conflicts.append({
                        "field": field,
                        "existing_value": existing_value,
                        "new_value": value,
                        "source": field_sources.get(field, "documento")
                    })
        
        # Extrair tipos de documentos processados
        for doc_result in results.get("documents", []):
            doc_type = doc_result.get("type") or doc_result.get("document_type")
            if doc_type:
                document_types.append({
                    "file_name": doc_result.get("file_name", ""),
                    "type": doc_type,
                    "source_path": doc_result.get("source_path", "")
                })
    
    # Finalizar log
    total_duration = int((time.time() - start_time) * 1000)
    if log_id and finalize_ai_import_log:
        try:
            await finalize_ai_import_log(log_id, duration_ms=total_duration)
        except Exception as e:
            logger.warning(f"Erro ao finalizar log: {e}")
    
    return {
        "success": True,
        "process_id": process_id,
        "client_name": client_name,
        "documents_count": len(documents),
        "log_id": log_id,
        "extracted_data": extracted_data,
        "conflicts": conflicts,
        "documents": document_types,
        "suggestions": list(extracted_data.keys()),
        "analysis": results
    }


@router.post("/ai-apply-suggestions/{process_id}", responses={400: HTTP_400_RESPONSE, 404: HTTP_404_RESPONSE, 500: HTTP_500_RESPONSE})
async def apply_ai_suggestions(
    process_id: str,
    suggestions: Dict = None,
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
    
    # Mapeamento de campos frontend para backend
    field_mapping = {
        "client_name": "client_name",
        "nif": "client_nif",
        "birth_date": "data_nascimento",
        "cc_number": "cc_number",
        "cc_validity": "validade_cc",
        "nationality": "nacionalidade",
        "gender": "sexo",
        "address": "morada",
        "fiscal_address": "morada_fiscal"
    }
    
    # Preparar atualização
    update_data = {}
    for field, value in suggestions.items():
        if field in field_mapping:
            backend_field = field_mapping[field]
            update_data[backend_field] = value
    
    if not update_data:
        return {"success": True, "updated_fields": 0, "message": "Nenhum campo válido para atualizar"}
    
    # Atualizar processo
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["updated_by"] = user.get("id")
    
    await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
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
    documents = body.get("documents", [])
    create_folders = body.get("create_folders", True)
    
    # Buscar processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "client_name": 1})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    
    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    
    # Mapeamento de tipos de documento para pastas
    document_type_folders = {
        "cc": "Identificação",
        "bi": "Identificação",
        "passaporte": "Identificação",
        "cartao_cidadao": "Identificação",
        "recibo_vencimento": "Financeiros/Recibos",
        "irs": "Financeiros/IRS",
        "declaracao_irs": "Financeiros/IRS",
        "nota_liquidacao": "Financeiros/IRS",
        "extrato_bancario": "Financeiros/Extratos",
        "comprovativo_morada": "Morada",
        "caderneta_predial": "Imóvel",
        "certidao_permanente": "Imóvel",
        "cpcv": "CPCV",
        "contrato_promessa": "CPCV",
        "licenca_utilizacao": "Imóvel",
        "planta": "Imóvel/Plantas",
        "ficha_tecnica": "Imóvel",
        "simulacao": "Simulações",
        "proposta": "Propostas",
        "minuta": "Minutas",
        "escritura": "Escritura",
        "certificado_energetico": "Imóvel/Certificados",
        "default": "Outros"
    }
    
    results = {"organized": [], "errors": [], "folders_created": []}
    
    if create_folders and s3_service.is_configured():
        # IMPORTANTE: Obter base_path UMA única vez ANTES do loop
        # Usar _get_client_base_path_for_upload para respeitar pastas existentes
        base_path = s3_service._get_client_base_path_for_upload(process_id, client_name, None)
        logger.info(f"Organizar documentos: usando pasta {base_path} para {client_name}")
        
        # Criar pastas standard se não existirem
        standard_folders = [
            "Identificação",
            "Financeiros",
            "Financeiros/Recibos",
            "Financeiros/IRS",
            "Financeiros/Extratos",
            "Morada",
            "Imóvel",
            "CPCV",
            "Simulações",
            "Propostas",
            "Minutas",
            "Escritura",
            "Outros"
        ]
        
        for folder in standard_folders:
            try:
                folder_key = f"{base_path}/{folder}/.keep"
                
                # Verificar se pasta já existe
                try:
                    s3_service.s3_client.head_object(
                        Bucket=s3_service.bucket_name,
                        Key=folder_key
                    )
                except (KeyError, AttributeError):
                    # Criar pasta
                    s3_service.s3_client.put_object(
                        Bucket=s3_service.bucket_name,
                        Key=folder_key,
                        Body=b''
                    )
                    results["folders_created"].append(folder)
                except Exception as e:
                    # Verificar se é um erro do S3 (NotFound)
                    if "NotFound" in str(type(e).__name__) or "404" in str(e):
                        # Criar pasta
                        s3_service.s3_client.put_object(
                            Bucket=s3_service.bucket_name,
                            Key=folder_key,
                            Body=b''
                        )
                        results["folders_created"].append(folder)
                    else:
                        raise
            except (IOError, OSError, ValueError, KeyError, TypeError) as e:
                logger.warning(f"Erro ao criar pasta {folder}: {e}")
    
    # Organizar documentos por tipo
    for doc in documents:
        try:
            doc_type = doc.get("type", "").lower()
            file_name = doc.get("file_name", "")
            
            if not file_name:
                continue
            
            # Determinar pasta destino
            target_folder = document_type_folders.get(doc_type, document_type_folders["default"])
            
            results["organized"].append({
                "file": file_name,
                "type": doc_type,
                "folder": target_folder
            })
            
        except (IOError, OSError, ValueError, KeyError, TypeError) as e:
            results["errors"].append({"file": doc.get("file_name", "?"), "error": str(e)})
    
    return {
        "success": True,
        "organized_count": len(results["organized"]),
        "folders_created_count": len(results["folders_created"]),
        "results": results
    }


# ====================================================================
# RENOMEAÇÃO INTELIGENTE DE DOCUMENTOS COM IA
# ====================================================================

def generate_smart_filename(
    category: str,
    subcategory: str,
    client_name: str,
    expiry_date: str = None,
    original_extension: str = "pdf"
) -> str:
    """
    Gera um nome de ficheiro inteligente baseado na categorização IA.
    
    Formato: {Categoria}_{Subcategoria}_{Cliente}_{Validade}.{ext}
    Exemplo: Identificacao_CC_JoaoSilva_2028-03-15.pdf
    
    Args:
        category: Categoria do documento
        subcategory: Subcategoria/tipo específico
        client_name: Nome do cliente
        expiry_date: Data de validade (opcional, formato YYYY-MM-DD)
        original_extension: Extensão original do ficheiro
        
    Returns:
        Nome normalizado e inteligente
    """
    import unicodedata
    import re
    
    def normalize_text(text: str, max_len: int = 20) -> str:
        """Remove acentos e caracteres especiais."""
        if not text:
            return ""
        normalized = unicodedata.normalize('NFKD', text)
        normalized = normalized.encode('ASCII', 'ignore').decode('ASCII')
        normalized = re.sub(r'[^\w]', '', normalized)
        return normalized[:max_len]
    
    # Normalizar componentes
    cat_norm = normalize_text(category, 15) or "Doc"
    subcat_norm = normalize_text(subcategory, 15) or "Geral"
    client_norm = normalize_text(client_name, 20) or DEFAULT_CLIENT_NAME
    
    # Construir nome
    parts = [cat_norm, subcat_norm, client_norm]
    
    # Adicionar data de validade se existir
    if expiry_date:
        parts.append(expiry_date)
    
    # Juntar partes
    smart_name = "_".join(parts)
    
    # Garantir extensão
    ext = original_extension.lower().lstrip('.')
    
    return f"{smart_name}.{ext}"


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
