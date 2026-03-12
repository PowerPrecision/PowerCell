"""
NIF Cache Module
================
Gestão de cache de NIF e mapeamentos pasta → cliente.
Permite reutilizar mapeamentos conhecidos para acelerar importações.
"""
import re
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from models.auth import UserRole
from services.auth import require_roles

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache em memória para NIF mappings
# Estrutura: {folder_name_normalized: {nif, process_id, client_name, matched_at}}
nif_session_cache: Dict[str, Dict[str, Any]] = {}

# Tempo máximo de validade do cache NIF (30 dias)
NIF_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 dias

# Flag para saber se já carregámos o cache da DB
_nif_cache_loaded = False


def normalize_text_for_matching(text: str) -> str:
    """
    Normaliza texto para comparação de nomes.
    Remove acentos, converte para minúsculas, remove caracteres especiais.
    """
    if not text:
        return ""
    
    # Remover acentos
    text = unicodedata.normalize('NFD', text)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    
    # Converter para minúsculas
    text = text.lower()
    
    # Remover caracteres especiais exceto espaços
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Normalizar espaços
    text = ' '.join(text.split())
    
    return text


def extract_all_names_from_string(text: str) -> Set[str]:
    """
    Extrai todos os nomes possíveis de uma string.
    Suporta formatos: "João e Maria", "João (Maria)", "João / Maria"
    """
    names = set()
    if not text:
        return names
    
    # Extrair nomes de parênteses primeiro
    parens_names = re.findall(r'\(([^)]+)\)', text)
    for name in parens_names:
        names.add(normalize_text_for_matching(name))
    
    # Remover conteúdo dos parênteses para processar o resto
    text_clean = re.sub(r'\([^)]+\)', '', text)
    text_clean = normalize_text_for_matching(text_clean)
    
    # Separar por delimitadores comuns
    separators = [' e ', ' / ', ', ', ' - ']
    parts = [text_clean]
    for sep in separators:
        new_parts = []
        for part in parts:
            new_parts.extend(part.split(sep))
        parts = new_parts
    
    for part in parts:
        part = part.strip()
        if part and len(part) > 2:
            names.add(part)
            # Adicionar também o primeiro nome
            first_name = part.split()[0] if part.split() else ""
            if first_name and len(first_name) > 2:
                names.add(first_name)
    
    return names


def get_nif_cache_key(folder_name: str) -> str:
    """Gerar chave normalizada para o cache de NIF."""
    return normalize_text_for_matching(folder_name)


async def _load_nif_cache_from_db():
    """Carregar mapeamentos NIF da base de dados para memória."""
    global nif_session_cache, _nif_cache_loaded
    
    if _nif_cache_loaded:
        return
    
    try:
        mappings = await db.nif_mappings.find({}, {"_id": 0}).to_list(1000)
        
        for mapping in mappings:
            cache_key = mapping.get("cache_key")
            if cache_key:
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
    except Exception as e:
        logger.error(f"[NIF CACHE] Erro ao carregar da DB: {e}")


async def cache_nif_mapping(folder_name: str, nif: str, process_id: str, client_name: str):
    """
    Guardar mapeamento NIF → Cliente no cache de sessão E na base de dados.
    """
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
        logger.info(f"[NIF CACHE] Mapeamento guardado: '{folder_name}' -> NIF {nif} -> '{client_name}'")
    except Exception as e:
        logger.error(f"[NIF CACHE] Erro ao persistir na DB: {e}")


async def get_cached_nif_mapping(folder_name: str) -> Optional[Dict[str, Any]]:
    """
    Obter mapeamento do cache de sessão NIF.
    Primeiro verifica memória, depois a base de dados.
    """
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
                nif_session_cache[cache_key] = cached
                logger.info(f"[NIF CACHE] Mapeamento carregado da DB: '{folder_name}'")
        except Exception as e:
            logger.error(f"[NIF CACHE] Erro ao buscar da DB: {e}")
            return None
    
    if not cached:
        return None
    
    # Verificar se expirou
    matched_at = cached.get("matched_at")
    if matched_at:
        if isinstance(matched_at, str):
            matched_at = datetime.fromisoformat(matched_at.replace("Z", "+00:00"))
        
        age = (datetime.now(timezone.utc) - matched_at).total_seconds()
        if age > NIF_CACHE_TTL_SECONDS:
            logger.info(f"[NIF CACHE] Mapeamento expirado para '{folder_name}' (idade: {int(age/86400)} dias)")
            del nif_session_cache[cache_key]
            await db.nif_mappings.delete_one({"cache_key": cache_key})
            return None
    
    return cached


async def find_client_by_nif(nif: str) -> Optional[dict]:
    """
    Encontrar cliente pelo NIF (busca exacta na DB).
    """
    if not nif:
        return None
    
    # Limpar NIF (apenas dígitos)
    nif_clean = re.sub(r'\D', '', str(nif))
    
    if len(nif_clean) != 9:
        logger.warning(f"[NIF] NIF inválido (não tem 9 dígitos): {nif}")
        return None
    
    # Buscar em personal_data.nif
    process = await db.processes.find_one(
        {"personal_data.nif": nif_clean},
        {"_id": 0}
    )
    
    if process:
        logger.info(f"[NIF] Cliente encontrado por NIF {nif_clean}: '{process.get('client_name')}'")
        return process
    
    # Buscar também no campo client_nif
    process = await db.processes.find_one(
        {"client_nif": nif_clean},
        {"_id": 0}
    )
    
    if process:
        logger.info(f"[NIF] Cliente encontrado por client_nif {nif_clean}: '{process.get('client_name')}'")
        return process
    
    logger.info(f"[NIF] Nenhum cliente encontrado com NIF {nif_clean}")
    return None


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
        await db.nif_mappings.delete_one({"cache_key": key})
    
    if expired_keys:
        logger.info(f"[NIF CACHE] Limpeza: {len(expired_keys)} entradas expiradas removidas")


# ====================================================================
# ENDPOINTS DE NIF CACHE
# ====================================================================

@router.get("/nif-cache/stats")
async def get_nif_cache_stats(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Obtém estatísticas do cache de NIF."""
    await _load_nif_cache_from_db()
    
    db_count = await db.nif_mappings.count_documents({})
    memory_count = len(nif_session_cache)
    
    # Amostra de mapeamentos
    sample_mappings = []
    for key, value in list(nif_session_cache.items())[:10]:
        sample_mappings.append({
            "folder": key,
            "nif": value.get("nif"),
            "client": value.get("client_name"),
            "matched_at": value.get("matched_at").isoformat() if isinstance(value.get("matched_at"), datetime) else value.get("matched_at")
        })
    
    return {
        "memory_count": memory_count,
        "db_count": db_count,
        "ttl_days": NIF_CACHE_TTL_SECONDS // 86400,
        "sample_mappings": sample_mappings,
        "cache_loaded": _nif_cache_loaded
    }


@router.post("/nif-cache/clear")
async def clear_nif_cache(
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Limpa todo o cache de NIF."""
    global nif_session_cache, _nif_cache_loaded
    
    memory_cleared = len(nif_session_cache)
    nif_session_cache.clear()
    _nif_cache_loaded = False
    
    result = await db.nif_mappings.delete_many({})
    
    return {
        "memory_cleared": memory_cleared,
        "db_cleared": result.deleted_count
    }


class NIFMappingRequest(BaseModel):
    folder_name: str
    nif: str
    process_id: str
    client_name: str


@router.post("/nif-cache/add-mapping")
async def add_nif_mapping_manual(
    request: NIFMappingRequest,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Adiciona mapeamento NIF manualmente."""
    # Validar NIF
    nif_clean = re.sub(r'\D', '', request.nif)
    if len(nif_clean) != 9:
        raise HTTPException(status_code=400, detail="NIF inválido (deve ter 9 dígitos)")
    
    # Verificar se processo existe
    process = await db.processes.find_one({"id": request.process_id}, {"_id": 0, "id": 1})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    await cache_nif_mapping(
        request.folder_name,
        nif_clean,
        request.process_id,
        request.client_name
    )
    
    return {
        "success": True,
        "message": f"Mapeamento criado: '{request.folder_name}' -> NIF {nif_clean}"
    }
