"""
Funções de matching de clientes.
Extraído de ai_bulk.py para melhor organização (SonarQube).

Este módulo contém funções para:
- Normalização de texto para matching
- Matching de clientes por nome (fuzzy)
- Matching de clientes por NIF (exacto)
"""
import re
import logging
import unicodedata
from typing import Optional, Dict, Set, List, Any

from database import db
from .utils import sanitize_for_log

logger = logging.getLogger(__name__)


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
    Suporta formatos: "João e Maria", "João (Maria)", "João / Maria", "João, Maria"
    """
    names = set()
    if not text:
        return names
    
    # Extrair nomes de parênteses primeiro (ex: "Claúdia Batista (Edson)")
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


async def find_client_by_nif(nif: str) -> Optional[dict]:
    """
    Encontrar cliente pelo NIF (busca exacta na DB).
    
    O NIF é o método mais fiável para ligar documentos a clientes,
    pois é único e imutável.
    
    Args:
        nif: Número de Identificação Fiscal (9 dígitos)
        
    Returns:
        Processo/cliente completo ou None
    """
    if not nif:
        return None
    
    # Limpar NIF (apenas dígitos)
    nif_clean = re.sub(r'\D', '', str(nif))
    
    if len(nif_clean) != 9:
        logger.warning("[NIF] NIF inválido (não tem 9 dígitos)")
        return None
    
    # Buscar em personal_data.nif
    process = await db.processes.find_one(
        {"personal_data.nif": nif_clean},
        {"_id": 0}
    )
    
    if process:
        logger.info(f"[NIF] Cliente encontrado por NIF")
        return process
    
    # Buscar também no campo client_nif (se existir)
    process = await db.processes.find_one(
        {"client_nif": nif_clean},
        {"_id": 0}
    )
    
    if process:
        logger.info(f"[NIF] Cliente encontrado por client_nif")
        return process
    
    logger.info(f"[NIF] Nenhum cliente encontrado com o NIF fornecido")
    return None


async def find_client_by_name(client_name: str) -> Optional[dict]:
    """
    Encontrar cliente pelo nome (busca flexível com FuzzyWuzzy).
    
    Melhorias:
    - Usa fuzzywuzzy token_set_ratio para comparação fonética
    - Matching de primeiro nome com peso extra (+20)
    - Suporte melhorado para parênteses e nomes compostos
    - Score mínimo de 70 para aceitar match
    
    Suporta:
    - Nomes com/sem acentos: "Cláudia" encontra "Claudia"
    - Nomes compostos: "João e Maria", "João (Maria)", "João / Maria"
    - Nomes parciais: pasta "João" encontra cliente "João e Maria"
    - Nomes entre parênteses: "Claúdia Batista (Edson)" é encontrado por "Edson"
    """
    if not client_name:
        return None
    
    # Importar fuzzywuzzy para matching fonético
    try:
        from fuzzywuzzy import fuzz
        HAS_FUZZY = True
    except ImportError:
        logger.warning("fuzzywuzzy não instalado - usando matching básico")
        HAS_FUZZY = False
    
    client_name = client_name.strip()
    client_name_normalized = normalize_text_for_matching(client_name)
    client_names = extract_all_names_from_string(client_name)
    
    # Extrair primeiro nome para matching com peso extra
    client_first_name = client_name_normalized.split()[0] if client_name_normalized.split() else ""
    
    logger.info(f"Procurando cliente: normalizado='{sanitize_for_log(client_name_normalized)}' | primeiro nome='{sanitize_for_log(client_first_name)}' | nomes extraídos={len(client_names)}")
    
    # 1. Busca exacta (com acentos)
    process = await db.processes.find_one(
        {"client_name": client_name},
        {"_id": 0}
    )
    if process:
        logger.info(f"Cliente encontrado (exacto)")
        return process
    
    # 2. Busca case-insensitive exacta
    process = await db.processes.find_one(
        {"client_name": {"$regex": f"^{re.escape(client_name)}$", "$options": "i"}},
        {"_id": 0}
    )
    if process:
        logger.info(f"Cliente encontrado (case-insensitive)")
        return process
    
    # 3. Buscar todos os processos e fazer matching flexível
    all_processes = await db.processes.find(
        {},
        {"_id": 0, "id": 1, "client_name": 1, "personal_data.nif": 1}
    ).to_list(length=None)
    
    best_match = None
    best_score = 0
    
    for proc in all_processes:
        proc_name = proc.get("client_name", "")
        proc_name_normalized = normalize_text_for_matching(proc_name)
        proc_names = extract_all_names_from_string(proc_name)
        
        # Extrair primeiro nome do cliente DB
        proc_first_name = proc_name_normalized.split()[0] if proc_name_normalized.split() else ""
        
        score = 0
        match_reason = ""
        
        # === Match exacto normalizado (sem acentos) ===
        if client_name_normalized == proc_name_normalized:
            score = 100
            match_reason = "exacto_normalizado"
        
        # === Match parcial - nome da pasta contido no nome do cliente ===
        elif client_name_normalized in proc_name_normalized:
            score = 85
            match_reason = "contido_no_cliente"
        
        # === Match parcial inverso - nome do cliente contido no nome da pasta ===
        elif proc_name_normalized in client_name_normalized:
            score = 80
            match_reason = "cliente_contido"
        
        # === FuzzyWuzzy token_set_ratio ===
        elif HAS_FUZZY:
            # token_set_ratio é bom para nomes em ordens diferentes
            fuzzy_score = fuzz.token_set_ratio(client_name_normalized, proc_name_normalized)
            
            # Bónus para primeiro nome igual (+20)
            first_name_bonus = 0
            if client_first_name and proc_first_name:
                if client_first_name == proc_first_name:
                    first_name_bonus = 20
                    logger.debug(f"Primeiro nome match: '{client_first_name}' -> '{proc_name}'")
                elif fuzz.ratio(client_first_name, proc_first_name) > 85:
                    first_name_bonus = 15
            
            score = min(fuzzy_score + first_name_bonus, 95)  # Cap em 95 para não ultrapassar match exacto
            match_reason = f"fuzzy_{fuzzy_score}+bonus_{first_name_bonus}"
        
        # === Match de nomes individuais (fallback) ===
        else:
            # Verificar se algum nome da pasta está no cliente
            common_names = client_names & proc_names
            if common_names:
                # Quanto mais nomes em comum, maior o score
                score = 55 + (len(common_names) * 10)
                match_reason = f"nomes_comuns_{len(common_names)}"
            else:
                # Verificar substrings (primeiro nome)
                for cn in client_names:
                    for pn in proc_names:
                        if cn and pn and len(cn) > 2 and len(pn) > 2:
                            if cn in pn or pn in cn:
                                score = max(score, 45)
                                match_reason = f"substring_{cn}_{pn}"
        
        if score > best_score:
            best_score = score
            best_match = proc
            logger.debug(f"Novo melhor match: '{proc_name}' com score {score} ({match_reason})")
    
    # Score mínimo de 70 (aumentado de 40 para reduzir falsos positivos)
    MIN_SCORE = 70
    
    if best_match and best_score >= MIN_SCORE:
        # Buscar documento completo
        full_process = await db.processes.find_one(
            {"id": best_match["id"]},
            {"_id": 0}
        )
        if full_process:
            logger.info(f"Cliente encontrado (fuzzy, score={best_score})")
            return full_process
    
    logger.warning(f"Cliente não encontrado (melhor score: {best_score}, min: {MIN_SCORE})")
    return None


async def suggest_similar_clients(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Retornar clientes similares para selecção manual.
    Usado quando o matching automático falha.
    
    Args:
        query: Nome/termo a pesquisar
        limit: Número máximo de sugestões (default 5, max 10)
        
    Returns:
        Lista de sugestões com nome, id, score e contagem de documentos
    """
    if not query or len(query) < 2:
        return []
    
    # Limitar resultados
    limit = min(limit, 10)
    
    # Importar fuzzywuzzy
    try:
        from fuzzywuzzy import fuzz
        HAS_FUZZY = True
    except ImportError:
        HAS_FUZZY = False
    
    # Normalizar query
    query_normalized = normalize_text_for_matching(query)
    query_names = extract_all_names_from_string(query)
    
    # Buscar todos os clientes
    all_processes = await db.processes.find(
        {},
        {"_id": 0, "id": 1, "client_name": 1, "process_number": 1, "analyzed_documents": 1}
    ).to_list(length=None)
    
    # Calcular scores
    scored_results = []
    
    for proc in all_processes:
        proc_name = proc.get("client_name", "")
        if not proc_name:
            continue
        
        proc_name_normalized = normalize_text_for_matching(proc_name)
        
        # Calcular score
        if HAS_FUZZY:
            # Usar token_set_ratio para melhor matching de nomes
            score = fuzz.token_set_ratio(query_normalized, proc_name_normalized)
        else:
            # Fallback: matching simples
            if query_normalized in proc_name_normalized:
                score = 80
            elif proc_name_normalized in query_normalized:
                score = 70
            else:
                # Calcular overlap de palavras
                proc_names = extract_all_names_from_string(proc_name)
                common = query_names & proc_names
                score = len(common) * 25 if common else 0
        
        # Só incluir se score > 30
        if score > 30:
            docs_count = len(proc.get("analyzed_documents", []))
            scored_results.append({
                "name": proc_name,
                "id": proc.get("id"),
                "process_number": proc.get("process_number"),
                "score": score,
                "docs": docs_count
            })
    
    # Ordenar por score (maior primeiro) e limitar
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results[:limit]
