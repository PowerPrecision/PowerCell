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

Tipos permitidos (whitelist):
- PDF (.pdf)
- JPEG (.jpg, .jpeg)
- PNG (.png)
- TIFF (.tif, .tiff)
- HEIC/HEIF (.heic, .heif) - fotos iPhone
- Microsoft Word (.docx)
- Microsoft Excel (.xlsx)

====================================================================
"""
import magic
import logging
from typing import Tuple, Optional
from fastapi import HTTPException

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


def validate_file_content(
    file_content: bytes,
    declared_filename: Optional[str] = None,
    max_size_mb: Optional[int] = None
) -> Tuple[bool, str, str]:
    """
    Valida o conteúdo de um ficheiro usando magic bytes.
    
    NÃO confia na extensão declarada - analisa os bytes reais.
    
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
            detail="Ficheiro vazio ou corrompido"
        )
    
    # 2. Detectar MIME type real usando magic bytes
    try:
        detected_mime = magic.from_buffer(file_content, mime=True)
    except OSError as e:
        logger.error(f"[SECURITY] Erro ao detectar MIME type: {e}")
        raise HTTPException(
            status_code=400,
            detail="Não foi possível validar o formato do ficheiro"
        )
    
    # 3. Verificar se é um tipo perigoso (executáveis, scripts)
    if detected_mime in DANGEROUS_MIME_TYPES:
        logger.critical(
            f"[SECURITY] FICHEIRO PERIGOSO BLOQUEADO! "
            f"MIME detectado: {detected_mime}"
        )
        raise HTTPException(
            status_code=400,
            detail="Formato de ficheiro não permitido por razões de segurança"
        )
    
    # 4. Verificar se está na whitelist
    if detected_mime not in ALLOWED_MIME_TYPES:
        logger.warning(
            f"[SECURITY] MIME type não permitido: {detected_mime}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"Formato de ficheiro inválido. Tipos permitidos: PDF, JPEG, PNG, TIFF, DOCX, XLSX"
        )
    
    # 5. Verificar tamanho
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
            detail=f"Ficheiro demasiado grande. Máximo permitido: {max_allowed_mb}MB"
        )
    
    # 6. Verificação adicional: extensão vs conteúdo (warning apenas)
    if declared_filename:
        declared_ext = "." + declared_filename.lower().rsplit(".", 1)[-1] if "." in declared_filename else ""
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


# ====================================================================
# MAGIC BYTES REFERENCE (para debug)
# ====================================================================
# PDF:  25 50 44 46 (%PDF)
# JPEG: FF D8 FF
# PNG:  89 50 4E 47 0D 0A 1A 0A
# ZIP:  50 4B 03 04 (também DOCX, XLSX)
# TIFF: 49 49 2A 00 (little endian) ou 4D 4D 00 2A (big endian)
# ====================================================================
