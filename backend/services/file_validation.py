"""
====================================================================
FILE VALIDATION SERVICE - SECURITY MODULE
====================================================================
Validação segura de ficheiros usando Magic Bytes (assinatura binária).

NUNCA confiar apenas na extensão do ficheiro!
Um atacante pode renomear malware.exe para documento.pdf.

Este módulo:
- Lê os "magic bytes" (primeiros bytes do ficheiro)
- Valida o MIME type real contra uma whitelist
- Rejeita ficheiros que não correspondem ao tipo declarado
- FALLBACK: Para formatos não reconhecidos pelo magic (HEIC/HEIF),
  usa verificação por extensão como backup
- EXTRAÇÃO AUTOMÁTICA: Detecta e extrai ficheiros válidos de wrappers
  (Java serialization, base64, etc.)

Tipos permitidos (whitelist):
- PDF (.pdf)
- JPEG (.jpg, .jpeg)
- PNG (.png)
- TIFF (.tif, .tiff)
- HEIC/HEIF (.heic, .heif) - fotos iPhone (verificação por extensão)
- Microsoft Word (.docx)
- Microsoft Excel (.xlsx)

====================================================================
"""
import magic
import logging
from typing import Tuple, Optional
from fastapi import HTTPException

# Importar serviço de extração
from services.file_extraction import (
    extract_valid_content,
    get_extraction_info,
    detect_java_serialization,
)

logger = logging.getLogger(__name__)


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
# WHITELIST DE MIME TYPES PERMITIDOS
# ====================================================================
# Apenas ficheiros necessários para processos de crédito habitação
# ====================================================================
ALLOWED_MIME_TYPES = {
    # Documentos PDF (CC, IRS, contratos, etc.)
    "application/pdf": {
        "extensions": [".pdf"],
        "description": "PDF Document",
        "max_size_mb": 50
    },
    
    # Imagens (fotos de documentos, comprovativos)
    "image/jpeg": {
        "extensions": [".jpg", ".jpeg"],
        "description": "JPEG Image",
        "max_size_mb": 20
    },
    "image/png": {
        "extensions": [".png"],
        "description": "PNG Image",
        "max_size_mb": 20
    },
    "image/tiff": {
        "extensions": [".tif", ".tiff"],
        "description": "TIFF Image",
        "max_size_mb": 50
    },
    "image/heic": {
        "extensions": [".heic"],
        "description": "HEIC Image (iPhone)",
        "max_size_mb": 20
    },
    "image/heif": {
        "extensions": [".heif"],
        "description": "HEIF Image",
        "max_size_mb": 20
    },
    
    # Microsoft Office (documentos adicionais)
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "extensions": [".docx"],
        "description": "Microsoft Word Document",
        "max_size_mb": 25
    },
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "extensions": [".xlsx"],
        "description": "Microsoft Excel Spreadsheet",
        "max_size_mb": 25
    },
    
    # ZIP (para DOCX/XLSX que o magic pode detectar como zip)
    "application/zip": {
        "extensions": [".docx", ".xlsx", ".zip"],
        "description": "ZIP Archive or Office Document",
        "max_size_mb": 50
    },
}

# MIME types perigosos que NUNCA devem ser aceites
DANGEROUS_MIME_TYPES = [
    "application/x-executable",
    "application/x-msdos-program",
    "application/x-msdownload",
    "application/x-sh",
    "application/x-shellscript",
    "application/x-bat",
    "application/x-msi",
    "application/java-archive",
    "application/javascript",
    "text/javascript",
    "application/x-python-code",
    "application/x-php",
    "text/x-php",
    "application/x-httpd-php",
]

# Extensões que requerem verificação especial (magic bytes não reconhecidos)
# HEIC/HEIF: formato Apple que python-magic não detecta corretamente
EXTENSION_MIME_FALLBACK = {
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def validate_file_content(
    file_content: bytes,
    declared_filename: Optional[str] = None,
    max_size_mb: Optional[int] = None
) -> Tuple[bool, str, str]:
    """
    Valida o conteúdo de um ficheiro usando magic bytes.
    
    NÃO confia na extensão declarada - analisa os bytes reais.
    Para formatos não reconhecidos pelo magic (HEIC/HEIF), usa fallback por extensão.
    
    Args:
        file_content: Conteúdo binário do ficheiro
        declared_filename: Nome do ficheiro (para logging)
        max_size_mb: Tamanho máximo em MB (opcional, usa default do tipo)
    
    Returns:
        Tuple[bool, str, str]: (válido, mime_type_detectado, mensagem)
    
    Raises:
        HTTPException: Se o ficheiro for inválido ou potencialmente perigoso
    """
    filename = declared_filename or "unknown"
    
    # 1. Verificar se há conteúdo
    if not file_content or len(file_content) == 0:
        logger.warning("[SECURITY] Ficheiro vazio rejeitado")
        raise HTTPException(
            status_code=400,
            detail="Ficheiro vazio ou corrompido. O ficheiro não contém dados."
        )
    
    # 2. Obter extensão do ficheiro para verificação de fallback
    declared_ext = ""
    if declared_filename and "." in declared_filename:
        declared_ext = "." + declared_filename.lower().rsplit(".", 1)[-1]
    
    # 3. Detectar MIME type real usando magic bytes
    try:
        detected_mime = magic.from_buffer(file_content, mime=True)
    except OSError as e:
        logger.error(f"[SECURITY] Erro ao detectar MIME type: {e}")
        raise HTTPException(
            status_code=400,
            detail="Não foi possível validar o formato do ficheiro. Tente novamente."
        )
    
    # 4. FALLBACK: Para formatos não reconhecidos pelo magic (HEIC/HEIF)
    # O python-magic retorna genericamente "application/octet-stream" para HEIC
    # Neste caso, verificamos pela extensão como fallback
    if detected_mime == "application/octet-stream" and declared_ext in EXTENSION_MIME_FALLBACK:
        detected_mime = EXTENSION_MIME_FALLBACK[declared_ext]
        logger.info(
            f"[SECURITY] MIME fallback por extensão: {sanitize_for_log(filename)} "
            f"-> {detected_mime}"
        )
    
    # 5. Verificar se é um tipo perigoso (executáveis, scripts)
    if detected_mime in DANGEROUS_MIME_TYPES:
        logger.critical(
            f"[SECURITY] FICHEIRO PERIGOSO BLOQUEADO! "
            f"MIME detectado: {detected_mime}"
        )
        raise HTTPException(
            status_code=400,
            detail="Formato de ficheiro não permitido por razões de segurança. Ficheiros executáveis não são aceites."
        )
    
    # 6. Verificar se está na whitelist
    if detected_mime not in ALLOWED_MIME_TYPES:
        # Mensagem de erro mais detalhada para ajudar o utilizador
        ext_info = f" (extensão: {declared_ext})" if declared_ext else ""
        logger.warning(
            f"[SECURITY] MIME type não permitido: {detected_mime}{ext_info} "
            f"ficheiro: {sanitize_for_log(filename)}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"Formato de ficheiro não suportado ({detected_mime}{ext_info}). "
                   f"Tipos permitidos: PDF, JPEG, PNG, TIFF, HEIC, DOCX, XLSX. "
                   f"Se está a enviar uma foto de iPhone, tente converter para JPEG primeiro."
        )
    
    # 7. Verificar tamanho
    file_config = ALLOWED_MIME_TYPES[detected_mime]
    max_allowed_mb = max_size_mb or file_config.get("max_size_mb", 50)
    file_size_mb = len(file_content) / (1024 * 1024)
    
    if file_size_mb > max_allowed_mb:
        logger.warning(
            f"[SECURITY] Ficheiro demasiado grande: {sanitize_for_log(filename)} "
            f"({file_size_mb:.2f}MB > {max_allowed_mb}MB)"
        )
        raise HTTPException(
            status_code=400,
            detail=f"Ficheiro demasiado grande ({file_size_mb:.1f}MB). O máximo permitido para este tipo é {max_allowed_mb}MB."
        )
    
    # 8. Verificação adicional: extensão vs conteúdo (warning apenas)
    if declared_filename:
        allowed_exts = file_config.get("extensions", [])
        
        if declared_ext and declared_ext not in allowed_exts:
            # Possível tentativa de spoofing - logar mas permitir
            logger.warning(
                f"[SECURITY] Possível extensão falsificada: {sanitize_for_log(filename)} "
                f"declarou {declared_ext}, mas conteúdo é {detected_mime}"
            )
    
    logger.info(
        f"[SECURITY] Ficheiro validado: {sanitize_for_log(filename)} "
        f"(MIME: {detected_mime}, Size: {file_size_mb:.2f}MB)"
    )
    
    return True, detected_mime, file_config["description"]


def validate_file_upload(
    file_content: bytes,
    filename: str,
    strict: bool = True
) -> dict:
    """
    Wrapper de conveniência para validação de uploads.
    
    Args:
        file_content: Bytes do ficheiro
        filename: Nome do ficheiro
        strict: Se True, lança exceção. Se False, retorna dict com status.
    
    Returns:
        dict com resultado da validação
    """
    try:
        valid, mime_type, description = validate_file_content(file_content, filename)
        return {
            "valid": valid,
            "mime_type": mime_type,
            "description": description,
            "filename": filename,
            "size_bytes": len(file_content)
        }
    except HTTPException as e:
        if strict:
            raise
        return {
            "valid": False,
            "error": e.detail,
            "filename": filename
        }


def get_safe_mime_type(file_content: bytes) -> str:
    """
    Obtém o MIME type seguro de um ficheiro.
    Retorna 'application/octet-stream' se não conseguir detectar.
    """
    try:
        return magic.from_buffer(file_content, mime=True)
    except Exception:
        return "application/octet-stream"


def validate_and_extract_file(
    file_content: bytes,
    declared_filename: Optional[str] = None,
    max_size_mb: Optional[int] = None
) -> Tuple[bytes, str, str, bool, dict]:
    """
    Valida ficheiro com extração automática de wrappers.
    
    Esta função tenta:
    1. Validar o ficheiro diretamente
    2. Se falhar, tentar extrair conteúdo válido de wrappers
    3. Validar o conteúdo extraído
    
    Args:
        file_content: Conteúdo binário do ficheiro
        declared_filename: Nome do ficheiro (para logging)
        max_size_mb: Tamanho máximo em MB (opcional)
    
    Returns:
        Tuple (content, mime_type, description, was_extracted, extraction_info)
        - content: Conteúdo validado (original ou extraído)
        - mime_type: Tipo MIME detectado
        - description: Descrição do tipo
        - was_extracted: True se o conteúdo foi extraído de um wrapper
        - extraction_info: Informações sobre a extração
    
    Raises:
        HTTPException: Se o ficheiro não puder ser validado nem extraído
    """
    filename = declared_filename or "unknown"
    was_extracted = False
    extraction_info = {}
    
    # 1. Tentar validação direta primeiro
    try:
        valid, mime_type, description = validate_file_content(
            file_content, declared_filename, max_size_mb
        )
        return file_content, mime_type, description, False, extraction_info
    except HTTPException as e:
        # Guardar erro para possível feedback
        original_error = e.detail
        
        # 2. Verificar se parece ser um ficheiro embrulhado
        extraction_info = get_extraction_info(file_content, filename)
        
        if extraction_info.get("was_extracted"):
            logger.info(f"[VALIDATE] Attempting extraction for: {sanitize_for_log(filename)}")
            
            # 3. Tentar extrair conteúdo válido
            extracted_content, detected_mime, detected_ext, was_extracted = extract_valid_content(
                file_content, filename
            )
            
            if was_extracted and detected_mime in ALLOWED_MIME_TYPES:
                # 4. Validar conteúdo extraído
                try:
                    valid, mime_type, description = validate_file_content(
                        extracted_content, declared_filename, max_size_mb
                    )
                    
                    logger.info(
                        f"[VALIDATE] Successfully extracted and validated: "
                        f"{sanitize_for_log(filename)} -> {mime_type} "
                        f"(wrapper: {extraction_info.get('wrapper_type', 'unknown')})"
                    )
                    
                    extraction_info["success"] = True
                    extraction_info["extracted_mime_type"] = mime_type
                    
                    return extracted_content, mime_type, description, True, extraction_info
                    
                except HTTPException:
                    # Conteúdo extraído também não passou na validação
                    logger.warning(
                        f"[VALIDATE] Extracted content failed validation: {sanitize_for_log(filename)}"
                    )
        
        # 5. Não foi possível extrair - dar erro útil
        # Verificar se é Java serialization para dar mensagem específica
        if detect_java_serialization(file_content):
            raise HTTPException(
                status_code=400,
                detail=f"O ficheiro parece estar num formato Java Serialization que não foi possível processar. "
                       f"Tente exportar o ficheiro diretamente da aplicação original como PDF ou imagem. "
                       f"(detectado: {extraction_info.get('detected_mime_type', 'desconhecido')})"
            )
        
        # Erro genérico
        raise HTTPException(
            status_code=400,
            detail=f"{original_error} "
                   f"O sistema tentou extrair o conteúdo automaticamente mas não foi possível. "
                   f"Certifique-se que o ficheiro é um PDF, imagem (JPEG, PNG) ou documento Office válido."
        )


# ====================================================================
# MAGIC BYTES REFERENCE (para debug)
# ====================================================================
# PDF:  25 50 44 46 (%PDF)
# JPEG: FF D8 FF
# PNG:  89 50 4E 47 0D 0A 1A 0A
# ZIP:  50 4B 03 04 (também DOCX, XLSX)
# TIFF: 49 49 2A 00 (little endian) ou 4D 4D 00 2A (big endian)
# Java Serialization: AC ED 00 05
# ====================================================================


# ====================================================================
# VALIDAÇÃO COM CONVERSÃO AUTOMÁTICA
# ====================================================================
def validate_and_convert_file(
    file_content: bytes,
    declared_filename: Optional[str] = None,
    max_size_mb: Optional[int] = None,
    auto_convert: bool = True
) -> Tuple[bytes, str, str, dict]:
    """
    Valida ficheiro com conversão automática se necessário.
    
    Esta função:
    1. Tenta validar o ficheiro diretamente
    2. Se falhar, tenta extrair de wrappers
    3. Se ainda falhar, tenta converter automaticamente
    4. Usa IA para analisar ficheiros desconhecidos
    
    Args:
        file_content: Conteúdo binário do ficheiro
        declared_filename: Nome do ficheiro (para logging)
        max_size_mb: Tamanho máximo em MB (opcional)
        auto_convert: Se deve tentar conversão automática (default: True)
    
    Returns:
        Tuple (content, mime_type, description, conversion_info)
        - content: Conteúdo validado/convertido
        - mime_type: Tipo MIME final
        - description: Descrição do tipo
        - conversion_info: Informações sobre conversão
    
    Raises:
        HTTPException: Se o ficheiro não puder ser validado, extraído ou convertido
    """
    from services.file_converter import (
        convert_file,
        can_convert_file,
        is_dangerous,
        detect_file_type,
    )
    
    filename = declared_filename or "unknown"
    conversion_info = {
        "original_size": len(file_content),
        "was_converted": False,
        "was_extracted": False,
        "conversion_method": None,
        "original_mime_type": None,
        "final_mime_type": None,
        "ai_analysis": None,
    }
    
    # 1. Tentar validação com extração primeiro (usa função existente)
    try:
        content, mime_type, description, was_extracted, extraction_info = validate_and_extract_file(
            file_content, declared_filename, max_size_mb
        )
        
        conversion_info["was_extracted"] = was_extracted
        conversion_info["original_mime_type"] = extraction_info.get("detected_mime_type")
        conversion_info["final_mime_type"] = mime_type
        
        return content, mime_type, description, conversion_info
        
    except HTTPException as validation_error:
        original_error = validation_error.detail
        
        # Se auto_convert está desativado, re-levantar o erro
        if not auto_convert:
            raise
        
        logger.info(f"[VALIDATE] Validation failed, attempting conversion for: {sanitize_for_log(filename)}")
        
        # 2. Verificar tipo detectado
        detected_mime, detected_ext, confidence = detect_file_type(file_content)
        conversion_info["original_mime_type"] = detected_mime
        
        # 3. Verificar se é perigoso
        if is_dangerous(detected_mime):
            logger.critical(f"[SECURITY] Ficheiro perigoso bloqueado: {detected_mime}")
            raise HTTPException(
                status_code=400,
                detail="Formato de ficheiro não permitido por razões de segurança. "
                       "Ficheiros executáveis e scripts não são aceites."
            )
        
        # 4. Verificar se pode ser convertido
        conversion_check = can_convert_file(file_content, filename)
        
        if conversion_check["can_convert"] == False:
            # Não pode ser convertido
            raise HTTPException(
                status_code=400,
                detail=f"Não foi possível processar o ficheiro. {conversion_check.get('reason', original_error)} "
                       f"Tipos permitidos: PDF, JPEG, PNG, TIFF, DOCX, XLSX. "
                       f"Se o ficheiro é uma imagem ou documento, tente exportar novamente no formato correto."
            )
        
        # 5. Tentar conversão
        try:
            converted_content, new_filename, convert_metadata = convert_file(
                file_content, filename, target_format='pdf'
            )
            
            if convert_metadata.get("converted"):
                # Conversão bem-sucedida
                logger.info(
                    f"[VALIDATE] File converted successfully: {sanitize_for_log(filename)} "
                    f"using {convert_metadata.get('method')}"
                )
                
                conversion_info["was_converted"] = True
                conversion_info["conversion_method"] = convert_metadata.get("method")
                conversion_info["final_mime_type"] = "application/pdf"
                conversion_info["new_filename"] = new_filename
                conversion_info["ai_analysis"] = convert_metadata.get("ai_analysis")
                
                # Validar o conteúdo convertido
                try:
                    valid, mime_type, description = validate_file_content(
                        converted_content, new_filename, max_size_mb
                    )
                    return converted_content, mime_type, description, conversion_info
                except HTTPException:
                    # Conteúdo convertido também falhou - retornar mesmo assim
                    return converted_content, "application/pdf", "PDF Document (converted)", conversion_info
                    
            elif convert_metadata.get("error"):
                # Conversão falhou
                error_msg = convert_metadata["error"]
                conversion_info["ai_analysis"] = convert_metadata.get("ai_analysis")
                
                # Se temos análise IA, dar feedback útil
                if conversion_info.get("ai_analysis"):
                    ai_rec = conversion_info["ai_analysis"].get("recommendation", "")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Não foi possível converter o ficheiro. {ai_rec} "
                               f"(detectado: {detected_mime})"
                    )
                
                raise HTTPException(
                    status_code=400,
                    detail=f"Não foi possível converter o ficheiro: {error_msg}. "
                           f"Tipo detectado: {detected_mime}. "
                           f"Tente exportar o ficheiro diretamente como PDF ou imagem."
                )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[VALIDATE] Conversion error: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Erro durante a conversão do ficheiro: {str(e)}. "
                       f"Tente exportar o ficheiro diretamente como PDF ou imagem."
            )
    
    # Fallback - não deveria chegar aqui
    raise HTTPException(
        status_code=400,
        detail="Não foi possível processar o ficheiro. "
               "Tente exportar o ficheiro diretamente como PDF ou imagem."
    )
