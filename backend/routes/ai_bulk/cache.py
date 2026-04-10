"""
Cache de sessão NIF e documento hash cache.
Extraído de ai_bulk.py para melhor organização (SonarQube).

Este módulo gere:
- Mapeamento pasta → cliente via NIF extraído
- Cache de hashes de documentos para detecção de duplicados
"""
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Tuple, Set, Optional, Any

from database import db

logger = logging.getLogger(__name__)

# ====================================================================
# CACHE DE SESSÃO NIF - Mapeamento Pasta → Cliente
# ====================================================================
# Quando um CC é analisado e o NIF extraído, guarda o mapeamento
# pasta → cliente para documentos subsequentes da mesma pasta.
# PERSISTÊNCIA: Os mapeamentos são guardados na coleção 'nif_mappings' da DB
# para sobreviver a reinícios do servidor.

# Estrutura em memória: {folder_name_normalized: {
#     "nif": "123456789",
#     "process_id": "uuid",
#     "client_name": "Nome Cliente",
#     "matched_at": datetime
# }}
nif_session_cache: Dict[str, Dict[str, Any]] = {}

# Tempo máximo de validade do cache NIF (30 dias para persistência)
NIF_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 dias

# Flag para saber se já carregámos o cache da DB
_nif_cache_loaded = False

# ====================================================================
# CACHE PARA HASHES DE DOCUMENTOS (evitar duplicados)
# ====================================================================
# Cache temporário para CC frente/verso por cliente
# Estrutura: {process_id: {"frente": (bytes, mime), "verso": (bytes, mime)}}
cc_cache: Dict[str, Dict[str, Tuple[bytes, str]]] = {}

# Cache para hashes de documentos já analisados (evitar duplicados)
# Estrutura: {process_id: {document_type: {hash: extracted_data}}}
document_hash_cache: Dict[str, Dict[str, Dict[str, dict]]] = {}


def get_nif_cache_key(folder_name: str) -> str:
    """Gerar chave normalizada para o cache de NIF."""
    from .matching import normalize_text_for_matching
    return normalize_text_for_matching(folder_name)


async def _load_nif_cache_from_db():
    """Carregar mapeamentos NIF da base de dados para memória."""
    global _nif_cache_loaded
    
    if _nif_cache_loaded:
        return
    
    try:
        mappings = await db.nif_mappings.find({}, {"_id": 0}).to_list(1000)
        
        for mapping in mappings:
            cache_key = mapping.get("cache_key")
            if cache_key:
                # Converter string ISO para datetime
                matched_at = mapping.get("matched_at")
                if isinstance(matched_at, str):
                    matched_at = datetime.fromisoformat(matched_at.replace("Z", "+00:00"))
                
                nif_session_cache[cache_key] = {
                    "nif": mapping.get("nif"),
                    "process_id": mapping.get("process_id"),
                    "client_name": mapping.get("client_name"),
                    "matched_at": matched_at
                }
        
        _nif_cache_loaded = True
        logger.info(f"[NIF CACHE] {len(mappings)} mapeamentos carregados da base de dados")
    except (IOError, OSError, ValueError, KeyError, TypeError, ConnectionError, TimeoutError) as e:
        logger.error(f"[NIF CACHE] Erro ao carregar da DB: {e}")


async def cache_nif_mapping(folder_name: str, nif: str, process_id: str, client_name: str):
    """
    Guardar mapeamento NIF → Cliente no cache de sessão E na base de dados.
    
    Args:
        folder_name: Nome da pasta do documento
        nif: NIF extraído do CC
        process_id: ID do processo/cliente na DB
        client_name: Nome do cliente
    """
    from .utils import sanitize_for_log
    
    cache_key = get_nif_cache_key(folder_name)
    now = datetime.now(timezone.utc)
    
    # Guardar em memória
    nif_session_cache[cache_key] = {
        "nif": nif,
        "process_id": process_id,
        "client_name": client_name,
        "matched_at": now
    }
    
    # Persistir na base de dados (upsert)
    try:
        await db.nif_mappings.update_one(
            {"cache_key": cache_key},
            {"$set": {
                "cache_key": cache_key,
                "folder_name": folder_name,
                "nif": nif,
                "process_id": process_id,
                "client_name": client_name,
                "matched_at": now.isoformat(),
                "updated_at": now.isoformat()
            }},
            upsert=True
        )
        logger.info(f"[NIF CACHE] Mapeamento guardado (memória + DB): '{sanitize_for_log(folder_name)}' -> NIF {sanitize_for_log(nif)} -> '{sanitize_for_log(client_name)}'")
    except (IOError, OSError, ValueError, KeyError, TypeError, ConnectionError, TimeoutError) as e:
        logger.error(f"[NIF CACHE] Erro ao persistir na DB: {e}")


async def get_cached_nif_mapping(folder_name: str) -> Optional[Dict[str, Any]]:
    """
    Obter mapeamento do cache de sessão NIF.
    Primeiro verifica memória, depois a base de dados.
    
    Returns:
        Dict com {nif, process_id, client_name} ou None se não existe/expirou
    """
    from .utils import sanitize_for_log
    
    # Garantir que carregámos o cache da DB
    await _load_nif_cache_from_db()
    
    cache_key = get_nif_cache_key(folder_name)
    cached = nif_session_cache.get(cache_key)
    
    # Se não está em memória, tentar buscar da DB
    if not cached:
        try:
            db_mapping = await db.nif_mappings.find_one({"cache_key": cache_key}, {"_id": 0})
            if db_mapping:
                matched_at = db_mapping.get("matched_at")
                if isinstance(matched_at, str):
                    matched_at = datetime.fromisoformat(matched_at.replace("Z", "+00:00"))
                
                cached = {
                    "nif": db_mapping.get("nif"),
                    "process_id": db_mapping.get("process_id"),
                    "client_name": db_mapping.get("client_name"),
                    "matched_at": matched_at
                }
                # Adicionar ao cache de memória
                nif_session_cache[cache_key] = cached
                logger.info(f"[NIF CACHE] Mapeamento carregado da DB")
        except (IOError, OSError, ValueError, KeyError, TypeError, ConnectionError, TimeoutError) as e:
            logger.error(f"[NIF CACHE] Erro ao buscar da DB: {e}")
            return None
    
    if not cached:
        return None
    
    # Verificar se expirou (30 dias)
    matched_at = cached.get("matched_at")
    if matched_at:
        if isinstance(matched_at, str):
            matched_at = datetime.fromisoformat(matched_at.replace("Z", "+00:00"))
        
        age = (datetime.now(timezone.utc) - matched_at).total_seconds()
        if age > NIF_CACHE_TTL_SECONDS:
            logger.info(f"[NIF CACHE] Mapeamento expirado (idade: {int(age/86400)} dias)")
            # Remover da memória e da DB
            del nif_session_cache[cache_key]
            await db.nif_mappings.delete_one({"cache_key": cache_key})
            return None
    
        logger.info(f"[NIF CACHE] Hit para pasta: NIF encontrado")
    return cached


async def clear_expired_nif_cache():
    """Limpar entradas expiradas do cache NIF (memória e DB)."""
    now = datetime.now(timezone.utc)
    expired_keys = []
    
    for key, cached in nif_session_cache.items():
        matched_at = cached.get("matched_at")
        if matched_at:
            if isinstance(matched_at, str):
                matched_at = datetime.fromisoformat(matched_at.replace("Z", "+00:00"))
            age = (now - matched_at).total_seconds()
            if age > NIF_CACHE_TTL_SECONDS:
                expired_keys.append(key)
    
    for key in expired_keys:
        del nif_session_cache[key]
        # Remover também da DB
        await db.nif_mappings.delete_one({"cache_key": key})
    
    if expired_keys:
        logger.info(f"[NIF CACHE] Limpeza: {len(expired_keys)} entradas expiradas removidas")


# ====================================================================
# FUNÇÕES PARA CACHE DE DOCUMENTOS DUPLICADOS
# ====================================================================

def calculate_document_hash(content: bytes) -> str:
    """Calcular hash MD5 do conteúdo do documento."""
    # CORREÇÃO DE SEGURANÇA: Adicionado usedforsecurity=False
    return hashlib.md5(content, usedforsecurity=False).hexdigest()


def is_duplicate_document(
    process_id: str, 
    document_type: str, 
    content: bytes
) -> Optional[dict]:
    """
    Verifica se o documento é duplicado de um já analisado (cache em memória).
    
    Returns:
        Dados extraídos anteriormente se for duplicado, None caso contrário
    """
    from .constants import DUPLICATE_PRONE_TYPES
    
    if document_type not in DUPLICATE_PRONE_TYPES:
        return None
    
    doc_hash = calculate_document_hash(content)
    
    if process_id in document_hash_cache:
        if document_type in document_hash_cache[process_id]:
            if doc_hash in document_hash_cache[process_id][document_type]:
                logger.info(f"Documento duplicado detectado (cache): {document_type}")
                return document_hash_cache[process_id][document_type][doc_hash]
    
    return None


async def is_duplicate_document_db(
    process_id: str, 
    document_type: str, 
    doc_hash: str
) -> Optional[dict]:
    """
    Verifica se o documento já foi analisado anteriormente (persistido na DB).
    
    Returns:
        Dados do documento se for duplicado, None caso contrário
    """
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "analyzed_documents": 1}
    )
    
    if not process:
        return None
    
    analyzed_docs = process.get("analyzed_documents", [])
    
    for doc in analyzed_docs:
        if doc.get("hash") == doc_hash:
            logger.info(f"Documento duplicado detectado (DB): hash={doc_hash[:8]}...")
            return doc
    
    return None


async def check_duplicate_comprehensive(
    process_id: str, 
    document_type: str, 
    content: bytes
) -> Optional[dict]:
    """
    Verificação completa de duplicados: cache em memória + base de dados.
    
    Returns:
        Dados do documento se for duplicado, None caso contrário
    """
    from .constants import DUPLICATE_PRONE_TYPES
    
    if document_type not in DUPLICATE_PRONE_TYPES:
        return None
    
    doc_hash = calculate_document_hash(content)
    
    # 1. Verificar cache em memória (rápido)
    cached = is_duplicate_document(process_id, document_type, content)
    if cached:
        return cached
    
    # 2. Verificar base de dados (persistente)
    db_record = await is_duplicate_document_db(process_id, document_type, doc_hash)
    if db_record:
        return db_record
    
    return None


def cache_document_analysis(
    process_id: str, 
    document_type: str, 
    content: bytes, 
    extracted_data: dict
):
    """Guardar resultado da análise em cache de memória para detectar duplicados futuros."""
    from .constants import DUPLICATE_PRONE_TYPES
    
    if document_type not in DUPLICATE_PRONE_TYPES:
        return
    
    doc_hash = calculate_document_hash(content)
    
    if process_id not in document_hash_cache:
        document_hash_cache[process_id] = {}
    if document_type not in document_hash_cache[process_id]:
        document_hash_cache[process_id][document_type] = {}
    
    document_hash_cache[process_id][document_type][doc_hash] = extracted_data


async def persist_document_analysis(
    process_id: str, 
    document_type: str, 
    content: bytes, 
    extracted_data: dict, 
    filename: str = ""
):
    """
    Persistir registo de documento analisado na base de dados.
    Evita re-análise mesmo após reinício do servidor.
    """
    doc_hash = calculate_document_hash(content)
    
    # Extrair mês de referência se disponível (para recibos/extratos)
    mes_referencia = extracted_data.get("mes_referencia") or extracted_data.get("periodo") or ""
    
    doc_record = {
        "hash": doc_hash,
        "document_type": document_type,
        "filename": filename,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "mes_referencia": mes_referencia,
        "fields_extracted": list(extracted_data.keys()) if extracted_data else []
    }
    
    # Adicionar ao array analyzed_documents do processo
    await db.processes.update_one(
        {"id": process_id},
        {
            "$push": {"analyzed_documents": doc_record},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    logger.info(f"Documento persistido: {document_type} (hash={doc_hash[:8]}...)")


def clear_duplicate_cache() -> int:
    """Limpar cache de documentos duplicados. Retorna contagem de documentos removidos."""
    global document_hash_cache
    count = sum(
        sum(len(hashes) for hashes in types.values())
        for types in document_hash_cache.values()
    )
    document_hash_cache = {}
    return count


def clear_nif_cache() -> Tuple[int, int]:
    """Limpar todo o cache de sessão NIF. Retorna (memória, db) counts."""
    global nif_session_cache, _nif_cache_loaded
    
    memory_count = len(nif_session_cache)
    nif_session_cache = {}
    _nif_cache_loaded = False
    
    return memory_count, memory_count  # DB count will be handled by caller
