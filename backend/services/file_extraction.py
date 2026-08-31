"""
====================================================================
FILE EXTRACTION SERVICE - WRAPPER DETECTION & EXTRACTION
====================================================================
Detecta e extrai ficheiros válidos "embrulhados" em formatos de wrapper.

Wrappers suportados:
- Java Serialization: Ficheiros PDF/imagens serializados em Java
- Base64 encoded: Conteúdo binário em base64
- Multipart: Ficheiros com headers extras

Isto resolve casos onde:
1. Aplicações Java serializam ficheiros antes de enviar
2. Ficheiros são transferidos através de sistemas que acrescentam wrappers
3. Downloads corrompidos que acrescentam bytes extras

====================================================================
"""
import logging
import re
import base64
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


# Assinaturas mágicas conhecidas (magic bytes)
MAGIC_SIGNATURES = {
    # Documents
    b'%PDF': {
        'mime_type': 'application/pdf',
        'extension': '.pdf',
        'description': 'PDF Document'
    },
    b'PK\x03\x04': {
        'mime_type': 'application/zip',
        'extension': '.zip',
        'description': 'ZIP Archive / Office Document',
        'can_be_docx': True
    },
    
    # Images
    b'\xff\xd8\xff': {
        'mime_type': 'image/jpeg',
        'extension': '.jpg',
        'description': 'JPEG Image'
    },
    b'\x89PNG\r\n\x1a\n': {
        'mime_type': 'image/png',
        'extension': '.png',
        'description': 'PNG Image'
    },
    b'GIF87a': {
        'mime_type': 'image/gif',
        'extension': '.gif',
        'description': 'GIF Image'
    },
    b'GIF89a': {
        'mime_type': 'image/gif',
        'extension': '.gif',
        'description': 'GIF Image'
    },
    b'BM': {
        'mime_type': 'image/bmp',
        'extension': '.bmp',
        'description': 'BMP Image'
    },
    b'II*\x00': {
        'mime_type': 'image/tiff',
        'extension': '.tif',
        'description': 'TIFF Image (little endian)'
    },
    b'MM\x00*': {
        'mime_type': 'image/tiff',
        'extension': '.tif',
        'description': 'TIFF Image (big endian)'
    },
    
    # HEIC/HEIF (iPhone photos)
    b'\x00\x00\x00\x20\x66\x74\x79\x70\x68\x65\x69\x63': {
        'mime_type': 'image/heic',
        'extension': '.heic',
        'description': 'HEIC Image (iPhone)'
    },
    b'\x00\x00\x00\x18\x66\x74\x79\x70\x68\x65\x69\x63': {
        'mime_type': 'image/heic',
        'extension': '.heic',
        'description': 'HEIC Image (iPhone)'
    },
}

# Java serialization header
JAVA_SER_HEADER = b'\xac\xed\x00\x05'

# Tamanho máximo para procurar magic bytes (1MB)
MAX_SEARCH_SIZE = 1024 * 1024


def detect_java_serialization(content: bytes) -> bool:
    """
    Verificar se o conteúdo está embrulhado em Java serialization.
    
    Java serialization começa com: AC ED 00 05
    """
    return content[:4] == JAVA_SER_HEADER


def find_magic_bytes(content: bytes, max_offset: int = MAX_SEARCH_SIZE) -> Tuple[Optional[int], Optional[dict]]:
    """
    Procurar magic bytes válidos no conteúdo.
    
    Args:
        content: Conteúdo binário do ficheiro
        max_offset: Offset máximo para procurar (default: 1MB)
    
    Returns:
        Tuple (offset, info) ou (None, None) se não encontrado
    """
    search_area = content[:max_offset]
    
    for magic, info in MAGIC_SIGNATURES.items():
        offset = search_area.find(magic)
        if offset >= 0:
            return offset, info
    
    return None, None


def extract_from_java_serialization(content: bytes) -> Tuple[Optional[bytes], Optional[dict]]:
    """
    Extrair conteúdo de Java serialization wrapper.
    
    Java serialization de arrays de bytes seguem o padrão:
    AC ED 00 05 - header
    75 72 00 02 5B 42 - array de bytes (byte[])
    [hash] - hash da classe
    [data] - dados do array (o PDF/imagem real)
    
    Args:
        content: Conteúdo binário
    
    Returns:
        Tuple (extracted_content, info) ou (None, None) se falhar
    """
    if not detect_java_serialization(content):
        return None, None
    
    # Procurar magic bytes dentro do conteúdo serializado
    offset, info = find_magic_bytes(content)
    
    if offset is not None and offset > 0:
        logger.info(f"[EXTRACT] Found {info['description']} at offset {offset} in Java serialization")
        
        # Extrair do offset até ao fim ou até encontrar o fim do documento
        extracted = content[offset:]
        
        # Para PDFs, encontrar o fim do documento
        if info['mime_type'] == 'application/pdf':
            eof_marker = extracted.rfind(b'%%EOF')
            if eof_marker > 0:
                extracted = extracted[:eof_marker + 5]
                logger.info(f"[EXTRACT] PDF extracted: {len(extracted)} bytes")
        
        return extracted, info
    
    return None, None


def extract_from_base64_wrapper(content: bytes) -> Tuple[Optional[bytes], Optional[dict]]:
    """
    Tentar extrair conteúdo de base64 wrapper.
    
    Alguns sistemas enviam ficheiros binários em base64.
    """
    # Verificar se parece ser base64
    try:
        # Remover whitespace
        text = content.decode('utf-8', errors='ignore').strip()
        
        # Verificar se parece base64 (apenas chars válidos, comprimento múltiplo de 4)
        if len(text) % 4 == 0 and re.match(r'^[A-Za-z0-9+/=]+$', text):
            decoded = base64.b64decode(text)
            
            # Verificar se o decoded content tem magic bytes válidos
            offset, info = find_magic_bytes(decoded, max_offset=0)  # Offset 0 = deve começar com magic
            
            if offset == 0:
                logger.info(f"[EXTRACT] Extracted {info['description']} from base64")
                return decoded, info
    except Exception as e:
        logger.debug(f"[EXTRACT] Not base64 wrapper: {e}")
    
    return None, None


def extract_valid_content(content: bytes, filename: str = None) -> Tuple[bytes, str, str, bool]:
    """
    Extrair conteúdo válido de ficheiros embrulhados.
    
    Tenta vários métodos de extração:
    1. Verificar se já é válido (magic bytes no início)
    2. Extrair de Java serialization
    3. Extrair de base64
    4. Procurar magic bytes em offsets
    
    Args:
        content: Conteúdo binário do ficheiro
        filename: Nome original do ficheiro (para logging)
    
    Returns:
        Tuple (content, mime_type, extension, was_extracted)
        - content: Conteúdo extraído ou original
        - mime_type: Tipo MIME detectado
        - extension: Extensão recomendada
        - was_extracted: True se foi necessário extrair
    """
    filename = filename or "unknown"
    
    # 1. Verificar se já é válido
    offset, info = find_magic_bytes(content, max_offset=0)
    if offset == 0:
        logger.info(f"[EXTRACT] File already valid: {info['description']}")
        return content, info['mime_type'], info['extension'], False
    
    # 2. Tentar extrair de Java serialization
    extracted, info = extract_from_java_serialization(content)
    if extracted is not None:
        logger.info(f"[EXTRACT] Extracted from Java serialization: {filename}")
        return extracted, info['mime_type'], info['extension'], True
    
    # 3. Tentar extrair de base64
    extracted, info = extract_from_base64_wrapper(content)
    if extracted is not None:
        logger.info(f"[EXTRACT] Extracted from base64: {filename}")
        return extracted, info['mime_type'], info['extension'], True
    
    # 4. Procurar magic bytes em qualquer offset
    offset, info = find_magic_bytes(content)
    if offset is not None and offset > 0:
        logger.info(f"[EXTRACT] Found valid content at offset {offset}: {filename}")
        extracted = content[offset:]
        
        # Para PDFs, encontrar o fim
        if info['mime_type'] == 'application/pdf':
            eof_marker = extracted.rfind(b'%%EOF')
            if eof_marker > 0:
                extracted = extracted[:eof_marker + 5]
        
        return extracted, info['mime_type'], info['extension'], True
    
    # Não foi possível extrair - retornar original
    logger.warning(f"[EXTRACT] Could not extract valid content from: {filename}")
    return content, "application/octet-stream", "", False


def get_extraction_info(content: bytes, filename: str = None) -> dict:
    """
    Obter informações sobre possível extração.
    
    Útil para feedback ao utilizador sobre o que aconteceu.
    
    Args:
        content: Conteúdo binário
        filename: Nome do ficheiro
    
    Returns:
        Dict com informações de extração
    """
    extracted, mime_type, extension, was_extracted = extract_valid_content(content, filename)
    
    result = {
        "original_size": len(content),
        "extracted_size": len(extracted),
        "was_extracted": was_extracted,
        "detected_mime_type": mime_type,
        "detected_extension": extension,
        "extraction_method": None,
    }
    
    if was_extracted:
        if detect_java_serialization(content):
            result["extraction_method"] = "java_serialization"
            result["wrapper_type"] = "Java Serialization"
        elif content[:4] == JAVA_SER_HEADER:
            result["extraction_method"] = "java_serialization"
            result["wrapper_type"] = "Java Serialization"
        else:
            result["extraction_method"] = "offset_extraction"
            result["wrapper_type"] = "Unknown wrapper"
    
    return result
