"""
====================================================================
DOCUMENT PROCESSOR SERVICE
====================================================================
Serviço para processamento de documentos:
- Conversão automática de imagens para PDF
- Validação de data de emissão (regra dos 6 meses)
- Extração de metadados

Dependências:
- img2pdf: Conversão de imagens para PDF
- Pillow: Manipulação de imagens
====================================================================
"""
import os
import io
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Tentar importar img2pdf (pode não estar instalado)
try:
    import img2pdf
    IMG2PDF_AVAILABLE = True
except ImportError:
    IMG2PDF_AVAILABLE = False
    logger.warning("img2pdf não instalado - conversão de imagens para PDF desativada")

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow não instalado - manipulação de imagens limitada")


# ====================================================================
# CONSTANTES
# ====================================================================
DOCUMENT_VALIDITY_DAYS = 180  # 6 meses em dias

# Tipos de documento que têm validade
DOCUMENTS_WITH_EXPIRY = [
    "irs",
    "recibo_vencimento",
    "extrato_bancario",
    "declaracao_rendimentos",
    "comprovativo_morada",
    "certidao_predial",
    "certidao_comercial",
    "certidao_nascimento",
    "certidao_casamento",
]

# Tipos de documento que NÃO expiram
DOCUMENTS_WITHOUT_EXPIRY = [
    "cc",  # Cartão de Cidadão tem validade própria
    "passaporte",
    "escritura",
    "contrato",
    "cpcv",
    "procuracao",
]


# ====================================================================
# CONVERSÃO DE IMAGENS PARA PDF
# ====================================================================

async def convert_image_to_pdf(
    image_data: bytes,
    filename: str
) -> Tuple[bytes, str]:
    """
    Converte uma imagem (JPEG, PNG) para PDF.
    
    Args:
        image_data: Bytes da imagem original
        filename: Nome do ficheiro original
        
    Returns:
        Tuple (pdf_bytes, new_filename)
    """
    if not IMG2PDF_AVAILABLE:
        logger.warning("img2pdf não disponível, retornando imagem original")
        return image_data, filename
    
    try:
        # Verificar se é uma imagem suportada
        extension = Path(filename).suffix.lower()
        if extension not in ['.jpg', '.jpeg', '.png', '.tiff', '.tif']:
            logger.info(f"Ficheiro {filename} não é imagem suportada para conversão")
            return image_data, filename
        
        # Converter para PDF
        pdf_bytes = img2pdf.convert(image_data)
        
        # Novo nome do ficheiro
        new_filename = Path(filename).stem + ".pdf"
        
        logger.info(f"Convertido {filename} para {new_filename} ({len(pdf_bytes)} bytes)")
        
        return pdf_bytes, new_filename
        
    except Exception as e:
        logger.error(f"Erro ao converter {filename} para PDF: {e}")
        # Retornar original em caso de erro
        return image_data, filename


async def convert_images_to_single_pdf(
    images: List[Tuple[bytes, str]]
) -> Tuple[bytes, str]:
    """
    Converte múltiplas imagens num único PDF.
    
    Args:
        images: Lista de tuplos (image_bytes, filename)
        
    Returns:
        Tuple (pdf_bytes, combined_filename)
    """
    if not IMG2PDF_AVAILABLE:
        raise ValueError("img2pdf não disponível")
    
    if not images:
        raise ValueError("Lista de imagens vazia")
    
    try:
        # Converter todas as imagens
        image_bytes_list = [img[0] for img in images]
        
        # Criar PDF combinado
        pdf_bytes = img2pdf.convert(image_bytes_list)
        
        # Nome baseado na primeira imagem
        base_name = Path(images[0][1]).stem
        combined_filename = f"{base_name}_combined.pdf"
        
        logger.info(f"Combinadas {len(images)} imagens em {combined_filename}")
        
        return pdf_bytes, combined_filename
        
    except Exception as e:
        logger.error(f"Erro ao combinar imagens em PDF: {e}")
        raise


# ====================================================================
# VALIDAÇÃO DE DATA DE EMISSÃO (REGRA DOS 6 MESES)
# ====================================================================

def check_document_validity(
    document_type: str,
    data_emissao: Optional[datetime] = None,
    validity_days: int = DOCUMENT_VALIDITY_DAYS
) -> Dict[str, Any]:
    """
    Verifica se um documento ainda está válido baseado na data de emissão.
    
    Args:
        document_type: Tipo de documento (ex: 'irs', 'recibo_vencimento')
        data_emissao: Data de emissão do documento
        validity_days: Dias de validade (default: 180 = 6 meses)
        
    Returns:
        Dict com status de validade e informações
    """
    result = {
        "document_type": document_type,
        "has_expiry": document_type.lower() in DOCUMENTS_WITH_EXPIRY,
        "is_valid": True,
        "warning": None,
        "error": None,
        "days_remaining": None,
        "expiry_date": None
    }
    
    # Documentos sem expiração
    if document_type.lower() in DOCUMENTS_WITHOUT_EXPIRY:
        result["has_expiry"] = False
        return result
    
    # Se não tem data de emissão, não podemos validar
    if not data_emissao:
        result["warning"] = "Data de emissão não fornecida - não é possível validar validade"
        return result
    
    # Calcular data de expiração
    now = datetime.now(timezone.utc)
    
    # Garantir que data_emissao tem timezone
    if data_emissao.tzinfo is None:
        data_emissao = data_emissao.replace(tzinfo=timezone.utc)
    
    expiry_date = data_emissao + timedelta(days=validity_days)
    days_remaining = (expiry_date - now).days
    
    result["expiry_date"] = expiry_date.isoformat()
    result["days_remaining"] = days_remaining
    
    # Verificar se expirou
    if days_remaining < 0:
        result["is_valid"] = False
        result["error"] = f"Documento expirado há {abs(days_remaining)} dias"
    elif days_remaining <= 30:
        result["warning"] = f"Documento expira em {days_remaining} dias"
    elif days_remaining <= 60:
        result["warning"] = f"Documento expira em {days_remaining} dias - considere renovar"
    
    return result


def validate_document_for_process(
    documents: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Valida todos os documentos de um processo.
    
    Args:
        documents: Lista de documentos do processo
        
    Returns:
        Dict com validação global e lista de problemas
    """
    result = {
        "all_valid": True,
        "warnings": [],
        "errors": [],
        "expired_documents": [],
        "expiring_soon": []  # Nos próximos 30 dias
    }
    
    for doc in documents:
        doc_type = doc.get("type", doc.get("document_type", "unknown"))
        
        # Tentar obter data de emissão
        data_emissao = None
        if doc.get("data_emissao"):
            try:
                if isinstance(doc["data_emissao"], str):
                    data_emissao = datetime.fromisoformat(doc["data_emissao"].replace("Z", "+00:00"))
                else:
                    data_emissao = doc["data_emissao"]
            except (ValueError, TypeError):
                pass
        
        # Validar
        validation = check_document_validity(doc_type, data_emissao)
        
        if validation.get("error"):
            result["all_valid"] = False
            result["errors"].append({
                "document": doc.get("filename", doc.get("name", "Desconhecido")),
                "type": doc_type,
                "message": validation["error"]
            })
            result["expired_documents"].append(doc_type)
            
        elif validation.get("warning"):
            result["warnings"].append({
                "document": doc.get("filename", doc.get("name", "Desconhecido")),
                "type": doc_type,
                "message": validation["warning"],
                "days_remaining": validation.get("days_remaining")
            })
            
            if validation.get("days_remaining", 999) <= 30:
                result["expiring_soon"].append(doc_type)
    
    return result


# ====================================================================
# PROCESSAMENTO DE UPLOAD
# ====================================================================

async def process_document_upload(
    file_data: bytes,
    filename: str,
    document_type: str,
    data_emissao: Optional[datetime] = None,
    convert_to_pdf: bool = True
) -> Dict[str, Any]:
    """
    Processa um upload de documento:
    1. Converte imagens para PDF (se aplicável)
    2. Valida data de emissão
    3. Retorna dados processados
    
    Args:
        file_data: Bytes do ficheiro
        filename: Nome original do ficheiro
        document_type: Tipo de documento
        data_emissao: Data de emissão (opcional)
        convert_to_pdf: Se deve converter imagens para PDF
        
    Returns:
        Dict com dados processados
    """
    result = {
        "original_filename": filename,
        "processed_filename": filename,
        "file_size": len(file_data),
        "converted_to_pdf": False,
        "validity": None,
        "warnings": [],
        "errors": []
    }
    
    # Verificar se é imagem e deve converter
    extension = Path(filename).suffix.lower()
    is_image = extension in ['.jpg', '.jpeg', '.png', '.tiff', '.tif']
    
    if is_image and convert_to_pdf:
        try:
            processed_data, new_filename = await convert_image_to_pdf(file_data, filename)
            
            if new_filename != filename:
                result["processed_filename"] = new_filename
                result["converted_to_pdf"] = True
                result["file_size"] = len(processed_data)
                file_data = processed_data
                
        except Exception as e:
            result["warnings"].append(f"Não foi possível converter para PDF: {e}")
    
    # Validar data de emissão
    validity = check_document_validity(document_type, data_emissao)
    result["validity"] = validity
    
    if validity.get("error"):
        result["errors"].append(validity["error"])
    elif validity.get("warning"):
        result["warnings"].append(validity["warning"])
    
    # Retornar dados processados
    result["processed_data"] = file_data
    
    return result


# ====================================================================
# INSTÂNCIA GLOBAL
# ====================================================================

class DocumentProcessor:
    """Classe wrapper para as funções de processamento."""
    
    async def convert_to_pdf(self, image_data: bytes, filename: str) -> Tuple[bytes, str]:
        return await convert_image_to_pdf(image_data, filename)
    
    def check_validity(self, doc_type: str, data_emissao: Optional[datetime] = None) -> Dict[str, Any]:
        return check_document_validity(doc_type, data_emissao)
    
    async def process_upload(self, *args, **kwargs) -> Dict[str, Any]:
        return await process_document_upload(*args, **kwargs)
    
    def validate_process_documents(self, documents: List[Dict]) -> Dict[str, Any]:
        return validate_document_for_process(documents)


document_processor = DocumentProcessor()
