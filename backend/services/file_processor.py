"""
File Processor Service - Processamento Assíncrono de Ficheiros
==============================================================
Serviço para processar ficheiros Excel e PDF em threads separadas
para não bloquear o event loop do asyncio.

IMPORTANTE: O processamento de Excel/PDF deve ser feito em threads
(def, não async def) porque são operações CPU-bound e I/O-bound que
podem bloquear o event loop.

Usa ThreadPoolExecutor para executar código síncrono de forma assíncrona.
"""
import os
import io
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List, BinaryIO
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ThreadPool para operações de ficheiros
# max_workers=4 é suficiente para a maioria dos casos
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="file_processor_")


def process_excel_sync(
    file_content: bytes,
    filename: str,
    force_client_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Processa ficheiro Excel de forma SÍNCRONA (thread-safe).
    Esta função é chamada dentro de um ThreadPoolExecutor.
    
    Args:
        file_content: Conteúdo do ficheiro em bytes
        filename: Nome do ficheiro
        force_client_id: ID do cliente para associar (opcional)
    
    Returns:
        Dict com resultados do processamento
    """
    import pandas as pd
    
    result = {
        "success": False,
        "filename": filename,
        "rows_processed": 0,
        "rows_imported": 0,
        "errors": [],
        "warnings": [],
        "data": [],
        "force_client_id": force_client_id
    }
    
    try:
        # Ler Excel com pandas
        df = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
        
        result["rows_processed"] = len(df)
        result["columns"] = list(df.columns)
        
        # Converter para lista de dicts
        data = df.fillna('').to_dict(orient='records')
        result["data"] = data
        result["rows_imported"] = len(data)
        result["success"] = True
        
        logger.info(f"Excel processado: {filename} - {len(data)} linhas")
        
    except Exception as e:
        error_msg = f"Erro ao processar Excel {filename}: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
    
    return result


def process_pdf_sync(
    file_content: bytes,
    filename: str,
    force_client_id: Optional[str] = None,
    extract_text: bool = True,
    extract_images: bool = False
) -> Dict[str, Any]:
    """
    Processa ficheiro PDF de forma SÍNCRONA (thread-safe).
    Esta função é chamada dentro de um ThreadPoolExecutor.
    
    Args:
        file_content: Conteúdo do ficheiro em bytes
        filename: Nome do ficheiro
        force_client_id: ID do cliente para associar (opcional)
        extract_text: Se deve extrair texto
        extract_images: Se deve extrair imagens
    
    Returns:
        Dict com resultados do processamento
    """
    result = {
        "success": False,
        "filename": filename,
        "pages": 0,
        "text": "",
        "images": [],
        "errors": [],
        "force_client_id": force_client_id
    }
    
    try:
        # Tentar com PyPDF2 primeiro
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(file_content))
            result["pages"] = len(reader.pages)
            
            if extract_text:
                text_parts = []
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                result["text"] = "\n".join(text_parts)
            
            result["success"] = True
            
        except ImportError:
            # Fallback para pypdf
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_content))
                result["pages"] = len(reader.pages)
                
                if extract_text:
                    text_parts = []
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    result["text"] = "\n".join(text_parts)
                
                result["success"] = True
                
            except ImportError:
                result["errors"].append("Nenhuma biblioteca PDF disponível (PyPDF2 ou pypdf)")
        
        logger.info(f"PDF processado: {filename} - {result['pages']} páginas")
        
    except Exception as e:
        error_msg = f"Erro ao processar PDF {filename}: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
    
    return result


def extract_document_data_sync(
    file_content: bytes,
    filename: str,
    document_type: str,
    force_client_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extrai dados de um documento de forma SÍNCRONA.
    Detecta o tipo de ficheiro e processa adequadamente.
    
    Args:
        file_content: Conteúdo do ficheiro
        filename: Nome do ficheiro
        document_type: Tipo de documento esperado
        force_client_id: ID do cliente para associar forçadamente
    
    Returns:
        Dict com dados extraídos
    """
    ext = os.path.splitext(filename)[1].lower()
    
    if ext in ['.xlsx', '.xls']:
        return process_excel_sync(file_content, filename, force_client_id)
    elif ext == '.pdf':
        return process_pdf_sync(file_content, filename, force_client_id)
    else:
        return {
            "success": False,
            "filename": filename,
            "errors": [f"Tipo de ficheiro não suportado: {ext}"],
            "force_client_id": force_client_id
        }


# =====================================================================
# Funções Async - Interface para o resto da aplicação
# =====================================================================

async def process_excel_async(
    file_content: bytes,
    filename: str,
    force_client_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Processa ficheiro Excel de forma assíncrona usando ThreadPoolExecutor.
    
    Esta função é async e pode ser chamada de código async,
    mas internamente executa o processamento numa thread separada.
    
    Args:
        file_content: Conteúdo do ficheiro em bytes
        filename: Nome do ficheiro
        force_client_id: ID do cliente para associar (opcional)
    
    Returns:
        Dict com resultados do processamento
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        process_excel_sync,
        file_content,
        filename,
        force_client_id
    )


async def process_pdf_async(
    file_content: bytes,
    filename: str,
    force_client_id: Optional[str] = None,
    extract_text: bool = True,
    extract_images: bool = False
) -> Dict[str, Any]:
    """
    Processa ficheiro PDF de forma assíncrona usando ThreadPoolExecutor.
    
    Args:
        file_content: Conteúdo do ficheiro em bytes
        filename: Nome do ficheiro
        force_client_id: ID do cliente para associar (opcional)
        extract_text: Se deve extrair texto
        extract_images: Se deve extrair imagens
    
    Returns:
        Dict com resultados do processamento
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        process_pdf_sync,
        file_content,
        filename,
        force_client_id,
        extract_text,
        extract_images
    )


async def extract_document_data_async(
    file_content: bytes,
    filename: str,
    document_type: str,
    force_client_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extrai dados de um documento de forma assíncrona.
    
    Args:
        file_content: Conteúdo do ficheiro
        filename: Nome do ficheiro
        document_type: Tipo de documento esperado
        force_client_id: ID do cliente para associar forçadamente
    
    Returns:
        Dict com dados extraídos
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        extract_document_data_sync,
        file_content,
        filename,
        document_type,
        force_client_id
    )


def shutdown_executor():
    """
    Desliga o ThreadPoolExecutor de forma limpa.
    Deve ser chamado ao encerrar a aplicação.
    """
    _executor.shutdown(wait=True)
    logger.info("File processor executor encerrado")


# Classe wrapper para uso mais conveniente
class FileProcessor:
    """
    Wrapper para funções de processamento de ficheiros.
    Fornece interface consistente e gestão de recursos.
    """
    
    @staticmethod
    async def process_excel(
        file_content: bytes,
        filename: str,
        force_client_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await process_excel_async(file_content, filename, force_client_id)
    
    @staticmethod
    async def process_pdf(
        file_content: bytes,
        filename: str,
        force_client_id: Optional[str] = None,
        extract_text: bool = True
    ) -> Dict[str, Any]:
        return await process_pdf_async(file_content, filename, force_client_id, extract_text)
    
    @staticmethod
    async def extract_data(
        file_content: bytes,
        filename: str,
        document_type: str,
        force_client_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return await extract_document_data_async(file_content, filename, document_type, force_client_id)


# Instância global
file_processor = FileProcessor()
